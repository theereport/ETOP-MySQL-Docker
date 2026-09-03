from __future__ import annotations

from typing import Any

from core.database import madden_database
from invoice_number_rules import normalize_erp_invoice


class CustomerRepository:
    def search_customers(
        self,
        *,
        search: str = "",
        route_code: str | None = None,
        store_number: int | None = None,
        active_only: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        parameters: list[Any] = []

        search_value = search.strip()
        search_invoice = normalize_erp_invoice(search_value)

        if search_value:
            wildcard = f"%{search_value}%"
            conditions.append(
                """
                (
                    CAST(CUNUMBER AS CHAR) LIKE %s
                    OR TRIM(CUNAME) LIKE %s
                    OR TRIM(CUADDRESS1) LIKE %s
                    OR TRIM(CUADDRESS2) LIKE %s
                    OR TRIM(CUADDRESS3) LIKE %s
                    OR TRIM(CUADDRESS4) LIKE %s
                    OR CAST(CUSTATE AS CHAR) LIKE %s
                    OR TRIM(CUZIP) LIKE %s
                    OR TRIM(CUROUTECD) LIKE %s
                    OR CAST(CUSTORENUM AS CHAR) LIKE %s
                    OR CAST(CUPHONE AS CHAR) LIKE %s
                    OR TRIM(CUEMAIL) LIKE %s
                    OR TRIM(CUCONTACT) LIKE %s
                    OR (
                        %s <> ''
                        AND EXISTS (
                            SELECT 1
                            FROM TMAROP AS OPEN_AR
                            WHERE OPEN_AR.TARONUMCST = TMCUST.CUNUMBER
                              AND OPEN_AR.TAROAMTOPN <> 0
                              AND TRIM(
                                  LEADING '0' FROM CAST(
                                      OPEN_AR.TARONUMINV AS CHAR
                                  )
                              ) = %s
                        )
                    )
                )
                """
            )
            parameters.extend(
                [
                    wildcard,
                    wildcard,
                    wildcard,
                    wildcard,
                    wildcard,
                    wildcard,
                    wildcard,
                    wildcard,
                    wildcard,
                    wildcard,
                    wildcard,
                    wildcard,
                    wildcard,
                    search_invoice,
                    search_invoice,
                ]
            )

        if route_code:
            conditions.append("TRIM(CUROUTECD) = %s")
            parameters.append(route_code.strip())

        if store_number is not None:
            conditions.append("CUSTORENUM = %s")
            parameters.append(store_number)

        if active_only:
            conditions.append(
                "COALESCE(NULLIF(TRIM(CUDELETECD), ''), 'A') = 'A'"
            )

        where_clause = (
            "WHERE " + " AND ".join(conditions)
            if conditions
            else ""
        )

        sql = f"""
        SELECT
            CUNUMBER,
            TRIM(CUNAME) AS CUNAME,
            TRIM(CUADDRESS4) AS CUADDRESS4,
            TRIM(CUROUTECD) AS CUROUTECD,
            CUSTORENUM,
            CUSALESMAN,
            TRIM(CUTYPE) AS CUTYPE,
            TRIM(CUCLASS) AS CUCLASS,
            TRIM(CUDELETECD) AS CUDELETECD,
            CUPHONE,
            TRIM(CUEMAIL) AS CUEMAIL,
            TRIM(CUADDRESS1) AS CUADDRESS1,
            TRIM(CUADDRESS2) AS CUADDRESS2,
            TRIM(CUADDRESS3) AS CUADDRESS3,
            CAST(CUSTATE AS CHAR) AS CUSTATE,
            TRIM(CUZIP) AS CUZIP,
            CUCRLIMIT,
            CUBALANCE,
            CUONORDER,
            CUONORDAR,
            CURVCPM30,
            CURVCPM60,
            CURVCPM90,
            CURVCPM120
        FROM TMCUST
        {where_clause}
        ORDER BY
            CASE
                WHEN %s <> '' AND EXISTS (
                    SELECT 1
                    FROM TMAROP AS OPEN_AR
                    WHERE OPEN_AR.TARONUMCST = TMCUST.CUNUMBER
                      AND OPEN_AR.TAROAMTOPN <> 0
                      AND TRIM(
                          LEADING '0' FROM CAST(
                              OPEN_AR.TARONUMINV AS CHAR
                          )
                      ) = %s
                ) THEN 0
                WHEN CAST(CUNUMBER AS CHAR) = %s THEN 1
                WHEN TRIM(CUNAME) = %s THEN 2
                WHEN TRIM(CUNAME) LIKE %s THEN 3
                ELSE 4
            END,
            TRIM(CUNAME),
            CUNUMBER
        LIMIT %s OFFSET %s
        """

        exact_search = search_value
        prefix_search = f"{search_value}%"

        parameters.extend(
            [
                search_invoice,
                search_invoice,
                exact_search,
                exact_search,
                prefix_search,
                limit,
                offset,
            ]
        )

        return madden_database.fetch_all(sql, parameters)

    def get_customer(self, customer_number: int) -> dict[str, Any] | None:
        return madden_database.fetch_one(
            """
            SELECT
                CUNUMBER,
                TRIM(CUNAME) AS CUNAME,
                TRIM(CUADDRESS1) AS CUADDRESS1,
                TRIM(CUADDRESS2) AS CUADDRESS2,
                TRIM(CUADDRESS3) AS CUADDRESS3,
                TRIM(CUADDRESS4) AS CUADDRESS4,
                CUSTATE,
                TRIM(CUZIP) AS CUZIP,
                TRIM(CUCOUNTRY) AS CUCOUNTRY,
                CUPHONE,
                CUPHONEXT,
                TRIM(CUNUMFAX) AS CUNUMFAX,
                TRIM(CUEMAIL) AS CUEMAIL,
                TRIM(CUCONTACT) AS CUCONTACT,
                TRIM(CUROUTECD) AS CUROUTECD,
                CUSTORENUM,
                CUSITE,
                CUSALESMAN,
                TRIM(CUTYPE) AS CUTYPE,
                TRIM(CUCLASS) AS CUCLASS,
                TRIM(CUDELETECD) AS CUDELETECD,
                TRIM(CUTERMS) AS CUTERMS,
                TRIM(CUCRGRADE) AS CUCRGRADE,
                TRIM(CUCRCDCOD) AS CUCRCDCOD,
                CUCRLIMIT,
                CUBALANCE,
                CUONORDER,
                CUONORDAR,
                CUHIGHBAL,
                CUMTHHIBAL,
                CURVCBLAVG,
                CURVCPMCUR,
                CURVCPM30,
                CURVCPM60,
                CURVCPM90,
                CURVCPM120,
                CURVCPMFUT,
                CUMTDSALES,
                CUYTDSALES,
                CULYRSALES,
                CUMTDDISC,
                CUYTDDISC,
                CULASPAYAM,
                TRIM(CULASPAYDT) AS CULASPAYDT,
                TRIM(CULASTACT) AS CULASTACT,
                TRIM(CULASTSTMT) AS CULASTSTMT,
                TRIM(CUDTELSTSL) AS CUDTELSTSL,
                TRIM(CUCRDATOPN) AS CUCRDATOPN,
                TRIM(CUDTECLEXP) AS CUDTECLEXP,
                TRIM(CUDTECREXP) AS CUDTECREXP,
                TRIM(CUDTETXEXP) AS CUDTETXEXP,
                TRIM(CUDTECRT) AS CUDTECRT,
                TRIM(CUDTECHG) AS CUDTECHG,
                TRIM(CUUSRCRT) AS CUUSRCRT,
                TRIM(CUUSRCHG) AS CUUSRCHG,
                TRIM(CUBNKRPYYN) AS CUBNKRPYYN,
                TRIM(CUEXFLAG4) AS CUEXFLAG4,
                TRIM(CUFINCHGYN) AS CUFINCHGYN,
                TRIM(CUCHKACCYN) AS CUCHKACCYN,
                TRIM(CUPOREQIRE) AS CUPOREQIRE,
                TRIM(CUTAXEXCD) AS CUTAXEXCD,
                TRIM(CUFETEXMPT) AS CUFETEXMPT,
                TRIM(CUSTMNTHLD) AS CUSTMNTHLD,
                TRIM(CUEXFLAG8) AS CUEXFLAG8,
                TRIM(CUEXFLAG9) AS CUEXFLAG9,
                CUCONTRACT
            FROM TMCUST
            WHERE CUNUMBER = %s
            LIMIT 1
            """,
            (customer_number,),
        )


customer_repository = CustomerRepository()
