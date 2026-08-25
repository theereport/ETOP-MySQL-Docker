from __future__ import annotations

from typing import Any

from core.database import madden_database
from invoice_number_rules import normalize_erp_invoice


class SalesOrderRepository:
    """Read-only MaddenCo (DTA273) evidence for sales order visibility.

    Every method issues a parameterized SELECT against MaddenCo through the
    shared read-only `madden_database` gateway. This repository never writes
    to the ERP. There is no open/pre-invoice order-entry table in the current
    MaddenCo schema, so every query here reads invoice-history tables
    (`TMIHSH`/`TMIHSI`/`TMIHSL`/`TMIHSM`/`TMIHSA`), the `TMSALE` sales-summary
    fact table, or the `INWHLOAD` delivery manifest.
    """

    def search_invoices(
        self,
        *,
        search: str = "",
        customer_number: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        parameters: list[Any] = []

        if customer_number is not None:
            conditions.append("header.TIHHNUMCST = %s")
            parameters.append(customer_number)

        search_value = search.strip()
        normalized_invoice = normalize_erp_invoice(search_value)
        if search_value:
            wildcard = f"%{search_value}%"
            conditions.append(
                """
                (
                    CAST(header.TIHHNUMINV AS CHAR) LIKE %s
                    OR CAST(header.TIHHNUMCST AS CHAR) LIKE %s
                    OR TRIM(customer.CUNAME) LIKE %s
                    OR TRIM(header.TIHHNUMPO) LIKE %s
                    OR (
                        %s <> ''
                        AND TRIM(
                            LEADING '0' FROM CAST(header.TIHHNUMINV AS CHAR)
                        ) = %s
                    )
                )
                """
            )
            parameters.extend([
                wildcard,
                wildcard,
                wildcard,
                wildcard,
                normalized_invoice,
                normalized_invoice,
            ])

        where_clause = (
            "WHERE " + " AND ".join(conditions) if conditions else ""
        )

        sql = f"""
        SELECT
            header.TIHHNUMINV,
            header.TIHHNUMCST,
            TRIM(customer.CUNAME) AS CUNAME,
            header.TIHHDTEINV,
            TRIM(header.TIHHCODTYP) AS TIHHCODTYP,
            header.TIHHTOTINV,
            TRIM(header.TIHHVOIDYN) AS TIHHVOIDYN,
            TRIM(header.TIHHCDRTE) AS TIHHCDRTE,
            header.TIHHNUMSTR,
            TRIM(header.TIHHNUMPO) AS TIHHNUMPO
        FROM TMIHSH AS header
        LEFT JOIN TMCUST AS customer
            ON customer.CUNUMBER = header.TIHHNUMCST
        {where_clause}
        ORDER BY header.TIHHDTEINV DESC, header.TIHHNUMINV DESC
        LIMIT %s OFFSET %s
        """
        parameters.extend([limit, offset])
        return madden_database.fetch_all(sql, parameters)

    def get_invoice_header(self, invoice_number: int) -> dict[str, Any] | None:
        return madden_database.fetch_one(
            """
            SELECT
                header.TIHHNUMINV,
                header.TIHHNUMCST,
                TRIM(customer.CUNAME) AS CUNAME,
                header.TIHHDTEINV,
                header.TIHHDTEDUE,
                header.TIHHDTECRT,
                header.TIHHDTECHG,
                TRIM(header.TIHHCODTYP) AS TIHHCODTYP,
                TRIM(header.TIHHVOIDYN) AS TIHHVOIDYN,
                TRIM(header.TIHHHLDRSN) AS TIHHHLDRSN,
                TRIM(header.TIHHDIRSHP) AS TIHHDIRSHP,
                TRIM(header.TIHHPICKUP) AS TIHHPICKUP,
                TRIM(header.TIHHCDRTE) AS TIHHCDRTE,
                header.TIHHNUMSTR,
                TRIM(header.TIHHNUMPO) AS TIHHNUMPO,
                TRIM(header.TIHHNUMREF) AS TIHHNUMREF,
                TRIM(header.TIHHCODTRM) AS TIHHCODTRM,
                TRIM(header.TIHHCODEXM) AS TIHHCODEXM,
                TRIM(header.TIHHCLSCST) AS TIHHCLSCST,
                TRIM(header.TIHHCSTTYP) AS TIHHCSTTYP,
                TRIM(header.TIHHTOS) AS TIHHTOS,
                TRIM(header.TIHHSHPTO1) AS TIHHSHPTO1,
                TRIM(header.TIHHSHPTO2) AS TIHHSHPTO2,
                TRIM(header.TIHHSHPTO3) AS TIHHSHPTO3,
                TRIM(header.TIHHSHPTO5) AS TIHHSHPTO5,
                TRIM(header.TIHHSHPTOZ) AS TIHHSHPTOZ,
                TRIM(header.TIHHTRKNUM) AS TIHHTRKNUM,
                header.TIHHTOTINV,
                header.TIHHTOTUNT,
                header.TIHHDISCST,
                header.TIHHNUMLIN,
                header.TIHHINVCNT,
                header.TIHHSLMSEL,
                header.TIHHSLMCST,
                header.TIHHSLMORG,
                header.TIHHSLMCLS,
                TRIM(header.TIHHSTATUS) AS TIHHSTATUS,
                TRIM(header.TIHHSTAT2) AS TIHHSTAT2
            FROM TMIHSH AS header
            LEFT JOIN TMCUST AS customer
                ON customer.CUNUMBER = header.TIHHNUMCST
            WHERE header.TIHHNUMINV = %s
            LIMIT 1
            """,
            (invoice_number,),
        )

    def get_invoice_lines(self, invoice_number: int) -> list[dict[str, Any]]:
        return madden_database.fetch_all(
            """
            SELECT
                TIHLLINENO,
                TRIM(TIHLCODTYP) AS TIHLCODTYP,
                TRIM(TIHLCODDEL) AS TIHLCODDEL,
                TRIM(TIHLPRD) AS TIHLPRD,
                TRIM(TIHLPRDDSC) AS TIHLPRDDSC,
                TRIM(TIHLVNDPRD) AS TIHLVNDPRD,
                TRIM(TIHLBRAND) AS TIHLBRAND,
                TRIM(TIHLCLSPRD) AS TIHLCLSPRD,
                TIHLQTY,
                TIHLQTYORD,
                TIHLQTYBO,
                TIHLPRC,
                TIHLCOSACT,
                TIHLCOSREP,
                TIHLFET,
                TRIM(TIHLDOT) AS TIHLDOT,
                TIHLDOTDTE,
                TRIM(TIHLTIRPOS) AS TIHLTIRPOS
            FROM TMIHSL
            WHERE TIHLNUMINV = %s
            ORDER BY TIHLLINENO
            """,
            (invoice_number,),
        )

    def get_invoice_line_fit_details(
        self,
        invoice_number: int,
    ) -> list[dict[str, Any]]:
        return madden_database.fetch_all(
            """
            SELECT
                TIHILINENO,
                TRIM(TIHICARMAK) AS TIHICARMAK,
                TRIM(TIHICARMOD) AS TIHICARMOD,
                TIHICARYR,
                TIHIMILAGE
            FROM TMIHSI
            WHERE TIHINUMINV = %s
            ORDER BY TIHILINENO
            """,
            (invoice_number,),
        )

    def get_invoice_memos(self, invoice_number: int) -> list[dict[str, Any]]:
        return madden_database.fetch_all(
            """
            SELECT
                TIHMLINENO,
                TRIM(TIHMCODTYP) AS TIHMCODTYP,
                TRIM(TIHMMSG) AS TIHMMSG,
                TIHMDTECRT,
                TRIM(TIHMUSRCRT) AS TIHMUSRCRT,
                TRIM(TIHMPRTINV) AS TIHMPRTINV
            FROM TMIHSM
            WHERE TIHMNUMINV = %s
            ORDER BY TIHMLINENO
            """,
            (invoice_number,),
        )

    def get_invoice_authorizations(
        self,
        invoice_number: int,
    ) -> list[dict[str, Any]]:
        return madden_database.fetch_all(
            """
            SELECT
                TRIM(TIHACD) AS TIHACD,
                TRIM(TIHACODTYP) AS TIHACODTYP,
                TIHAAMTAU,
                TIHADATRQ,
                TIHADATAU,
                TRIM(TIHATIMRQ) AS TIHATIMRQ,
                TRIM(TIHATIMAU) AS TIHATIMAU,
                TIHASLMRQ,
                TIHASLMAU,
                TRIM(TIHAUSRRQ) AS TIHAUSRRQ,
                TRIM(TIHAUSRAU) AS TIHAUSRAU,
                TRIM(TIHATXT) AS TIHATXT
            FROM TMIHSA
            WHERE TIHANUMINV = %s
            ORDER BY TIHADATRQ DESC, TIHATIMRQ DESC
            """,
            (invoice_number,),
        )

    def get_delivery_status(self, invoice_number: int) -> list[dict[str, Any]]:
        return madden_database.fetch_all(
            """
            SELECT
                STORENUM,
                TRIM(ROUTE) AS ROUTE,
                TRIM(STATUS) AS STATUS,
                LINENUM,
                SEQ,
                TRIM(PRODNUM) AS PRODNUM,
                TRIM(`DESC`) AS DESC_,
                WEIGHT,
                QUANTITY,
                CRTSTAMP,
                DLVSTAMP
            FROM KMTDTA.INWHLOAD
            WHERE INVNUM = %s
            ORDER BY LINENUM, SEQ
            """,
            (invoice_number,),
        )

    def get_sales_summary(
        self,
        *,
        customer_number: int | None = None,
        product_number: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        parameters: list[Any] = []

        if customer_number is not None:
            conditions.append("customer_number = %s")
            parameters.append(customer_number)

        if product_number:
            conditions.append("TRIM(product_number) = %s")
            parameters.append(product_number.strip())

        where_clause = (
            "WHERE " + " AND ".join(conditions) if conditions else ""
        )

        sql = f"""
        SELECT
            customer_number,
            TRIM(product_number) AS product_number,
            TRIM(product_class) AS product_class,
            TRIM(product_type) AS product_type,
            TRIM(customer_class) AS customer_class,
            TRIM(customer_type) AS customer_type,
            TRIM(commission_code) AS commission_code,
            TRIM(vendor_number) AS vendor_number,
            store_number,
            year_period,
            sales,
            units,
            actual_cost,
            replacement_cost,
            fet
        FROM TMSALE
        {where_clause}
        ORDER BY sales DESC
        LIMIT %s
        """
        parameters.append(limit)
        return madden_database.fetch_all(sql, parameters)


sales_order_repository = SalesOrderRepository()
