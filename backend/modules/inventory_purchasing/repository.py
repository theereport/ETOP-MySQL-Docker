from __future__ import annotations

from typing import Any

from core.database import madden_database


class InventoryPurchasingRepository:
    """Read-only MaddenCo (DTA273) evidence for inventory & purchasing.

    Every method issues a parameterized SELECT against MaddenCo through the
    shared read-only `madden_database` gateway. This repository never writes
    to the ERP. Unlike `vendor_intelligence` (which queries TMPOHD/TMPODT and
    TTRCVD from the vendor angle), every query here is scoped by PRODUCT
    number (`TPDPRD` / `TRCDNUMPRD`), building item-centric evidence across
    every vendor with exposure to that item.
    """

    def search_products(
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
                    CAST(PDNUMBER AS CHAR) LIKE %s
                    OR TRIM(PDSEARCHKY) LIKE %s
                    OR TRIM(PDDESCRIP) LIKE %s
                    OR TRIM(PDBARCODE) LIKE %s
                    OR TRIM(PDMFGPRDNO) LIKE %s
                )
                """
            )
            parameters.extend([wildcard] * 5)

        if active_only:
            conditions.append(
                "COALESCE(NULLIF(TRIM(PDDELETE), ''), 'A') = 'A'"
            )

        where_clause = (
            "WHERE " + " AND ".join(conditions) if conditions else ""
        )

        # TMPROD carries one row per product/store combination (PDSTORE).
        # Search results are collapsed to one row per product number with
        # MAX() — a plain aggregate, not a business calculation — so the
        # same item does not appear once per store.
        sql = f"""
        SELECT
            PDNUMBER,
            MAX(TRIM(PDDESCRIP)) AS PDDESCRIP,
            MAX(TRIM(PDSEARCHKY)) AS PDSEARCHKY,
            MAX(TRIM(PDCLASS)) AS PDCLASS,
            MAX(TRIM(PDTYPE)) AS PDTYPE,
            MAX(TRIM(PDBRAND)) AS PDBRAND,
            MAX(TRIM(PDUNITMEAS)) AS PDUNITMEAS,
            MAX(TRIM(PDVENDOR)) AS PDVENDOR,
            MAX(TRIM(PDDELETE)) AS PDDELETE,
            MAX(TRIM(PDNONINV)) AS PDNONINV
        FROM TMPROD
        {where_clause}
        GROUP BY PDNUMBER
        ORDER BY MAX(TRIM(PDDESCRIP)), PDNUMBER
        LIMIT %s OFFSET %s
        """
        parameters.extend([limit, offset])
        return madden_database.fetch_all(sql, parameters)

    def get_product(self, product_number: str) -> dict[str, Any] | None:
        return madden_database.fetch_one(
            """
            SELECT
                PDNUMBER,
                TRIM(PDSEARCHKY) AS PDSEARCHKY,
                TRIM(PDDESCRIP) AS PDDESCRIP,
                TRIM(PDCLASS) AS PDCLASS,
                TRIM(PDTYPE) AS PDTYPE,
                TRIM(PDBRAND) AS PDBRAND,
                TRIM(PDSIZE) AS PDSIZE,
                TRIM(PDLOADINDX) AS PDLOADINDX,
                TRIM(PDSPEEDRAT) AS PDSPEEDRAT,
                TRIM(PDMFGPRDNO) AS PDMFGPRDNO,
                TRIM(PDBARCODE) AS PDBARCODE,
                TRIM(PDUNITMEAS) AS PDUNITMEAS,
                TRIM(PDVENDOR) AS PDVENDOR,
                PDSTORE,
                TRIM(PDWAREHSE) AS PDWAREHSE,
                TRIM(PDWAREHALT) AS PDWAREHALT,
                TRIM(PDDELETE) AS PDDELETE,
                TRIM(PDNONINV) AS PDNONINV,
                TRIM(PDALLOWPO) AS PDALLOWPO,
                PDDTECRT,
                PDRECVDATE,
                PDSOLDDATE,
                PDVENDCOST,
                PDACTCOST,
                PDREPLCOST,
                PDLYRCOST,
                PDPRICE1,
                PDPRICE2,
                PDPRICE3,
                PDPRICE4,
                PDPRICE5,
                PDPRICE6,
                PDINVENTRY,
                PDONORDER,
                PDALLOCATD,
                PDMIN,
                PDMAX,
                PDINVTURNS,
                PDLEADTIM
            FROM TMPROD
            WHERE PDNUMBER = %s
            ORDER BY PDSTORE
            LIMIT 1
            """,
            (product_number,),
        )

    def get_month_end_inventory(
        self,
        product_number: str,
        *,
        limit: int = 24,
    ) -> list[dict[str, Any]]:
        return madden_database.fetch_all(
            """
            SELECT
                STORENUM,
                MONTH,
                YEAR,
                TRIM(VENDNUM) AS VENDNUM,
                TRIM(CLASSNUM) AS CLASSNUM,
                UNITS,
                TOTALCOST,
                TOTALFET
            FROM KMTDTA.EOMINV
            WHERE PARTNUM = %s
            ORDER BY YEAR DESC, MONTH DESC, STORENUM
            LIMIT %s
            """,
            (product_number, limit),
        )

    def get_open_purchase_orders_for_product(
        self,
        product_number: str,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return madden_database.fetch_all(
            """
            SELECT
                header.TPHNB,
                header.TPHNBVND,
                header.TPHDTE,
                header.TPHDTEREQ,
                TRIM(header.TPHCDSTS) AS TPHCDSTS,
                TRIM(header.TPHFLGCMP) AS TPHFLGCMP,
                TRIM(header.TPHVIA) AS TPHVIA,
                header.TPHBUYNUM,
                ln.total_ordered,
                ln.total_received,
                ln.total_backorder,
                ln.average_unit_cost,
                ln.line_total_cost
            FROM TMPOHD AS header
            INNER JOIN (
                SELECT
                    TPHNB,
                    SUM(TPDQTYORD) AS total_ordered,
                    SUM(TPDQTYRCV) AS total_received,
                    SUM(TPDQTYBO) AS total_backorder,
                    AVG(TPDUNTCST) AS average_unit_cost,
                    SUM(TPDQTYORD * TPDUNTCST) AS line_total_cost
                FROM TMPODT
                WHERE TPDPRD = %s
                GROUP BY TPHNB
            ) AS ln ON ln.TPHNB = header.TPHNB
            WHERE COALESCE(NULLIF(TRIM(header.TPHFLGCMP), ''), 'N') <> 'Y'
            ORDER BY header.TPHDTE DESC, header.TPHNB DESC
            LIMIT %s
            """,
            (product_number, limit),
        )

    def get_receiving_history_for_product(
        self,
        product_number: str,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return madden_database.fetch_all(
            """
            SELECT
                receipt.TRCDNUMPO,
                header.TPHNBVND,
                receipt.TRCDQTY,
                receipt.TRCDCOS,
                receipt.TRCDCOSPO,
                receipt.TRCDCOSDIF,
                TRIM(receipt.TRCDDOT) AS TRCDDOT,
                receipt.TRCDDOTDTE,
                receipt.TRCDDTECRT
            FROM TTRCVD AS receipt
            LEFT JOIN TMPOHD AS header
                ON header.TPHNB = receipt.TRCDNUMPO
            WHERE receipt.TRCDNUMPRD = %s
            ORDER BY receipt.TRCDDTECRT DESC
            LIMIT %s
            """,
            (product_number, limit),
        )


inventory_purchasing_repository = InventoryPurchasingRepository()
