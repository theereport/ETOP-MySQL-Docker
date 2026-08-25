from __future__ import annotations

from typing import Any

from core.database import madden_database


class ARCollectionsRepository:
    """Read-only MaddenCo (DTA273) evidence for AR collections.

    Every method issues a parameterized SELECT against MaddenCo through the
    shared read-only `madden_database` gateway. This repository never writes
    to the ERP.
    """

    _AROP_ITEM_COLUMNS = """
                TARONUMCST,
                TARONUMINV,
                TRIM(TAROTYPTRN) AS TAROTYPTRN,
                TRIM(TAROENTTYP) AS TAROENTTYP,
                TRIM(TARODBCR) AS TARODBCR,
                TAROAMTORG,
                TAROAMTOPN,
                TAROAMTDSC,
                TAROCSHDSC,
                TRIM(TAROCDTERM) AS TAROCDTERM,
                TRIM(TAROADJRSN) AS TAROADJRSN,
                TRIM(TARONUMREF) AS TARONUMREF,
                TARODTE,
                TARODTEDUE,
                TRIM(TAROHISTYN) AS TAROHISTYN
    """

    def get_open_items(
        self,
        customer_number: int,
        *,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        # TMAROP retains every item indefinitely, flagged by TAROHISTYN
        # ('Y' once closed/paid, 'N'/blank while still open) rather than
        # purging closed items to a separate table the way AP's PMHD/PTHD
        # split does. Excluding TAROHISTYN='Y' here keeps this genuinely
        # "currently open" — see get_item_history() for the closed side.
        return madden_database.fetch_all(
            f"""
            SELECT
                {self._AROP_ITEM_COLUMNS}
            FROM TMAROP
            WHERE TARONUMCST = %s
              AND COALESCE(NULLIF(TRIM(TAROHISTYN), ''), 'N') <> 'Y'
            ORDER BY TARODTEDUE ASC, TARONUMINV ASC
            LIMIT %s
            """,
            (customer_number, limit),
        )

    def get_item_history(
        self,
        customer_number: int,
        *,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Closed/paid TMAROP items (TAROHISTYN='Y') for this customer.

        This is the customer's real AR item history — TMAROP keeps it
        directly rather than moving it to a separate table. TTNARH/TTNARD
        (see get_transaction_history) are a narrow, commonly sparse
        adjustment sub-ledger, not the primary history source.
        """

        return madden_database.fetch_all(
            f"""
            SELECT
                {self._AROP_ITEM_COLUMNS}
            FROM TMAROP
            WHERE TARONUMCST = %s
              AND TRIM(TAROHISTYN) = 'Y'
            ORDER BY TARODTE DESC, TARONUMINV DESC
            LIMIT %s
            """,
            (customer_number, limit),
        )

    def get_transaction_history(
        self,
        customer_number: int,
        *,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return madden_database.fetch_all(
            """
            SELECT
                TNARSEQ,
                TNARNUMCUS,
                TNARNUMINV,
                TNARDTE,
                TNARDTEDUE,
                TNARAMTORG,
                TRIM(TNARDBCR) AS TNARDBCR,
                TRIM(TNARENTTYP) AS TNARENTTYP,
                TRIM(TNARTYPTRN) AS TNARTYPTRN,
                TRIM(TNARNUMREF) AS TNARNUMREF,
                TRIM(TNARSTATUS) AS TNARSTATUS,
                TNARPER,
                TNARYEAR,
                TNARCSHDSC
            FROM TTNARH
            WHERE TNARNUMCUS = %s
            ORDER BY TNARDTE DESC, TNARSEQ DESC
            LIMIT %s
            """,
            (customer_number, limit),
        )

    def get_transaction_applications(
        self,
        customer_number: int,
        *,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        return madden_database.fetch_all(
            """
            SELECT
                header.TNARSEQ AS HEADER_TNARSEQ,
                header.TNARNUMINV AS HEADER_TNARNUMINV,
                TRIM(header.TNARNUMREF) AS HEADER_TNARNUMREF,
                header.TNARDTE AS HEADER_TNARDTE,
                detail.TNARDTLSEQ,
                detail.TNARINVAPL,
                detail.TNARAMTAPL,
                detail.TNARDISAPL,
                detail.TNARGLACCT,
                detail.TNARGLDIV,
                detail.TNARGLDPT,
                detail.TNARDTECRT
            FROM TTNARD AS detail
            INNER JOIN TTNARH AS header
                ON header.TNARSEQ = detail.TNARSEQ
            WHERE header.TNARNUMCUS = %s
            ORDER BY detail.TNARDTECRT DESC, detail.TNARDTLSEQ DESC
            LIMIT %s
            """,
            (customer_number, limit),
        )

    def get_gl_distributions(
        self,
        customer_number: int,
        *,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return madden_database.fetch_all(
            """
            SELECT
                TNGLNBCST,
                TNGLNBACCT,
                TNGLNBDV,
                TNGLNBDP,
                TNGLAMTDB,
                TNGLAMTCR,
                TNGLQTY,
                TRIM(TNGLDSC) AS TNGLDSC,
                TNGLDTECRT
            FROM TTNGL
            WHERE TNGLNBCST = %s
            ORDER BY TNGLDTECRT DESC
            LIMIT %s
            """,
            (customer_number, limit),
        )

    def get_erp_collection_notes(
        self,
        customer_number: int,
        *,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return madden_database.fetch_all(
            """
            SELECT
                CUSTNUM,
                NOTES,
                CRTSTAMP,
                TRIM(CRTUSER) AS CRTUSER,
                CHGSTAMP,
                TRIM(CHGUSER) AS CHGUSER
            FROM KMTDTA.CCROLNOTE
            WHERE CUSTNUM = %s
            ORDER BY CRTSTAMP DESC
            LIMIT %s
            """,
            (customer_number, limit),
        )

    def get_credit_management_headers(
        self,
        customer_number: int,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return madden_database.fetch_all(
            """
            SELECT
                TCMOHNBKY,
                CUNUMBER,
                TRIM(TCMOHTXT) AS TCMOHTXT,
                TCMOHDTDO,
                TCMOHDTDN,
                TCMOHDTCRT,
                TRIM(TCMOHUSRCR) AS TCMOHUSRCR,
                TCMOHDTCHG,
                TRIM(TCMOHUSRCH) AS TCMOHUSRCH
            FROM TMCRMH
            WHERE CUNUMBER = %s
            ORDER BY TCMOHDTCRT DESC, TCMOHNBKY DESC
            LIMIT %s
            """,
            (customer_number, limit),
        )

    def get_credit_management_detail(
        self,
        header_key: int,
    ) -> list[dict[str, Any]]:
        return madden_database.fetch_all(
            """
            SELECT
                TCMOHNBKY,
                TCMODNBSEQ,
                TRIM(TCMODTXT) AS TCMODTXT
            FROM TMCRMD
            WHERE TCMOHNBKY = %s
            ORDER BY TCMODNBSEQ ASC
            """,
            (header_key,),
        )

    def get_aging_snapshots(
        self,
        customer_number: int,
        *,
        limit: int = 12,
    ) -> list[dict[str, Any]]:
        return madden_database.fetch_all(
            """
            SELECT
                TCCHNUMCUS,
                TCCHDTE,
                TCCHAGE1,
                TCCHAGE2,
                TCCHAGE3,
                TCCHAGE4,
                TCCHAGE5,
                TCCHAGE6,
                TCCHBAL,
                TCCHBALHI,
                TCCHDISMTD,
                TCCHCRDLMT,
                TCCHDTELPD,
                TCCHDTELST,
                TCCHAMTLPD,
                TCCHNUMSLM,
                TCCHSALMTD
            FROM TMCCH
            WHERE TCCHNUMCUS = %s
            ORDER BY TCCHDTE DESC
            LIMIT %s
            """,
            (customer_number, limit),
        )


ar_collections_repository = ARCollectionsRepository()
