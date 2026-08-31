from __future__ import annotations

from typing import Any

from core.database import madden_database


class VendorRepository:
    """Read-only MaddenCo (DTA273) evidence for vendor intelligence.

    Every method issues a parameterized SELECT against MaddenCo through the
    shared read-only `madden_database` gateway. This repository never writes
    to the ERP.
    """

    def search_vendors(
        self,
        *,
        search: str = "",
        active_only: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        parameters: list[Any] = []

        search_value = search.strip()
        if search_value:
            wildcard = f"%{search_value}%"
            conditions.append(
                """
                (
                    CAST(PVNUMVEN AS CHAR) LIKE %s
                    OR TRIM(PVNAMVEN) LIKE %s
                    OR TRIM(PVNAMCNT) LIKE %s
                    OR TRIM(PVEMAIL) LIKE %s
                    OR TRIM(PVZIP) LIKE %s
                    OR CAST(PVPHONE AS CHAR) LIKE %s
                )
                """
            )
            parameters.extend([wildcard] * 6)

        if active_only:
            conditions.append(
                "COALESCE(NULLIF(TRIM(PVCODDEL), ''), 'A') = 'A'"
            )

        where_clause = (
            "WHERE " + " AND ".join(conditions) if conditions else ""
        )

        sql = f"""
        SELECT
            PVNUMVEN,
            TRIM(PVNAMVEN) AS PVNAMVEN,
            TRIM(PVNAMCNT) AS PVNAMCNT,
            PVPHONE,
            TRIM(PVEMAIL) AS PVEMAIL,
            TRIM(PVZIP) AS PVZIP,
            TRIM(PVCODDEL) AS PVCODDEL,
            TRIM(PVPOREQ) AS PVPOREQ
        FROM PMVEND
        {where_clause}
        ORDER BY TRIM(PVNAMVEN), PVNUMVEN
        LIMIT %s OFFSET %s
        """
        parameters.extend([limit, offset])
        return madden_database.fetch_all(sql, parameters)

    def get_vendor(self, vendor_number: int) -> dict[str, Any] | None:
        return madden_database.fetch_one(
            """
            SELECT
                PVNUMVEN,
                TRIM(PVNAMVEN) AS PVNAMVEN,
                TRIM(PVNAMSRT) AS PVNAMSRT,
                TRIM(PVNAMCNT) AS PVNAMCNT,
                TRIM(PVADDR1) AS PVADDR1,
                TRIM(PVADDR2) AS PVADDR2,
                TRIM(PVADDR3) AS PVADDR3,
                TRIM(PVADDR4) AS PVADDR4,
                TRIM(PVZIP) AS PVZIP,
                TRIM(PVCOUNTRY) AS PVCOUNTRY,
                PVPHONE,
                PVNBFAX,
                TRIM(PVEMAIL) AS PVEMAIL,
                TRIM(PVCODDEL) AS PVCODDEL,
                TRIM(PVTYPVEN) AS PVTYPVEN,
                PVSTOREN,
                TRIM(PVCODTREM) AS PVCODTREM,
                TRIM(PVPOREQ) AS PVPOREQ,
                TRIM(PVFLGNORCV) AS PVFLGNORCV,
                TRIM(PV1099OP) AS PV1099OP,
                TRIM(PVCOD1099) AS PVCOD1099,
                PVAMT1099,
                TRIM(PVIDFED) AS PVIDFED,
                TRIM(PVTYPPMT) AS PVTYPPMT,
                TRIM(PVTYPBNK) AS PVTYPBNK,
                TRIM(PVACCBNK) AS PVACCBNK,
                PVROUBNK,
                PVPURMTD,
                PVPURYTD,
                PVPURLSTYR,
                PVDISCMTD,
                PVDISCYTD,
                PVDISCLMTD,
                PVDISCLYTD,
                PVAMTLPD,
                TRIM(PVDTELPD) AS PVDTELPD,
                PVCHKLPD
            FROM PMVEND
            WHERE PVNUMVEN = %s
            LIMIT 1
            """,
            (vendor_number,),
        )

    def get_open_purchase_orders(
        self,
        vendor_number: int,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return madden_database.fetch_all(
            """
            SELECT
                header.TPHNB,
                header.TPHDTE,
                header.TPHDTEREQ,
                TRIM(header.TPHCDSTS) AS TPHCDSTS,
                TRIM(header.TPHFLGCMP) AS TPHFLGCMP,
                header.TPHTOTCST,
                TRIM(header.TPHVIA) AS TPHVIA,
                header.TPHBUYNUM,
                COALESCE(ln.total_ordered, 0) AS TOTAL_ORDERED,
                COALESCE(ln.total_received, 0) AS TOTAL_RECEIVED,
                COALESCE(ln.total_backorder, 0) AS TOTAL_BACKORDER,
                COALESCE(ln.line_count, 0) AS LINE_COUNT
            FROM TMPOHD AS header
            LEFT JOIN (
                SELECT
                    TPHNB,
                    SUM(TPDQTYORD) AS total_ordered,
                    SUM(TPDQTYRCV) AS total_received,
                    SUM(TPDQTYBO) AS total_backorder,
                    COUNT(*) AS line_count
                FROM TMPODT
                GROUP BY TPHNB
            ) AS ln ON ln.TPHNB = header.TPHNB
            WHERE header.TPHNBVND = %s
              AND COALESCE(NULLIF(TRIM(header.TPHFLGCMP), ''), 'N') <> 'Y'
            ORDER BY header.TPHDTE DESC, header.TPHNB DESC
            LIMIT %s
            """,
            (vendor_number, limit),
        )

    PO_FILL_RATE_TIMEOUT_MS = 8000

    def get_po_fill_rate_summary(
        self,
        vendor_number: int,
        *,
        window_days: int = 365,
    ) -> dict[str, Any] | None:
        """Aggregates this vendor's TMPOHD/TMPODT purchase-order lines
        created within the trailing window into ordered/received/backorder
        totals - the same join already used by get_open_purchase_orders,
        widened from "open POs only" to a real historical window and
        aggregated to one summary instead of per-PO detail.

        Confirmed live this join is inherently expensive for the handful
        of highest-volume vendors (tens of thousands of POs) - timing
        ranged from ~1s to ~40s for the same query on the same vendor,
        occasionally exceeding the shared 60s statement timeout. A
        per-query MAX_EXECUTION_TIME hint bounds the worst case to a fast,
        predictable failure well under that shared ceiling; the caller
        treats a timeout the same as "no data" rather than crashing the
        rest of this vendor's evidence."""

        return madden_database.fetch_one(
            f"""
            SELECT /*+ MAX_EXECUTION_TIME({self.PO_FILL_RATE_TIMEOUT_MS}) */
                COUNT(DISTINCT header.TPHNB) AS po_count,
                COALESCE(SUM(line.TPDQTYORD), 0) AS quantity_ordered,
                COALESCE(SUM(line.TPDQTYRCV), 0) AS quantity_received,
                COALESCE(SUM(line.TPDQTYBO), 0) AS quantity_backorder
            FROM TMPOHD AS header
            INNER JOIN TMPODT AS line
                ON line.TPHNB = header.TPHNB
            WHERE header.TPHNBVND = %s
              AND header.TPHDTECRT >= DATE_FORMAT(
                  CURDATE() - INTERVAL %s DAY, '%%Y%%m%%d'
              )
            """,
            (vendor_number, window_days),
        )

    def get_receiving_history(
        self,
        vendor_number: int,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return madden_database.fetch_all(
            """
            SELECT
                receipt.TRCDNUMPO,
                TRIM(receipt.TRCDNUMPRD) AS TRCDNUMPRD,
                TRIM(receipt.TRCDPRDDSC) AS TRCDPRDDSC,
                receipt.TRCDQTY,
                receipt.TRCDCOS,
                receipt.TRCDCOSPO,
                receipt.TRCDCOSDIF,
                TRIM(receipt.TRCDDOT) AS TRCDDOT,
                receipt.TRCDDOTDTE,
                receipt.TRCDDTECRT
            FROM TTRCVD AS receipt
            INNER JOIN TMPOHD AS header
                ON header.TPHNB = receipt.TRCDNUMPO
            WHERE header.TPHNBVND = %s
            ORDER BY receipt.TRCDDTECRT DESC
            LIMIT %s
            """,
            (vendor_number, limit),
        )

    def get_open_payable_invoices(
        self,
        vendor_number: int,
        *,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        # PMHD retains full AP history, not just open items - PMHNBCHK
        # (check number) is populated once an invoice has been paid.
        # Confirmed live this session (accounts_payable's own open-ledger
        # cache work): without this filter, "open payables" silently
        # included already-paid invoices, e.g. showing a vendor's most
        # recent 100 PMHD rows regardless of payment status rather than
        # its genuinely open ones.
        #
        # PMHNBCHK = 0 alone is still not sufficient: a voided entry never
        # gets a check number either, so it stays "unpaid" forever.
        # PMHCODSEL = 'V' marks these - confirmed live that 12,166 of
        # 12,289 such rows carry a non-zero PMHGLREFVD (void GL reference)
        # versus zero of the genuinely open rows, and the 'V' rows carry
        # nonsense dates (1950-2034) versus the real open rows' 2024-2026
        # range.
        return madden_database.fetch_all(
            """
            SELECT
                TRIM(PMHNBINV) AS PMHNBINV,
                PMHAMTINV,
                PMHAMTDIS,
                PMHDTEINV,
                PMHDTEDUE,
                TRIM(PMHFLGHLD) AS PMHFLGHLD,
                PMHPR,
                PMHYR
            FROM PMHD
            WHERE PMHNBVND = %s
                AND (PMHNBCHK = 0 OR PMHNBCHK IS NULL)
                AND (PMHCODSEL IS NULL OR TRIM(PMHCODSEL) != 'V')
            ORDER BY PMHDTEINV DESC
            LIMIT %s
            """,
            (vendor_number, limit),
        )

    def get_paid_payable_invoices(
        self,
        vendor_number: int,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return madden_database.fetch_all(
            """
            SELECT
                TRIM(history.PTHNBINV) AS PTHNBINV,
                history.PTHAMTINV,
                history.PTHDTEINV,
                history.PTHDTEDUE,
                TRIM(history.PTHSTAT) AS PTHSTAT,
                payment.PTYAMT,
                payment.PTYAMTDIS
            FROM PTHD AS history
            LEFT JOIN PTPY AS payment
                ON payment.PTHNBVND = history.PTHNBVND
               AND payment.PTHNBINV = history.PTHNBINV
            WHERE history.PTHNBVND = %s
            ORDER BY history.PTHDTEINV DESC
            LIMIT %s
            """,
            (vendor_number, limit),
        )


vendor_repository = VendorRepository()
