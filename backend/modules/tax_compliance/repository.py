from __future__ import annotations

from typing import Any

from core.database import madden_database


class TaxComplianceRepository:
    """Read-only MaddenCo (DTA273) evidence for tax compliance.

    Every method issues a parameterized SELECT against MaddenCo through the
    shared read-only `madden_database` gateway. This repository never writes
    to the ERP. It reads three tables: TMTAX (tax authority rate master),
    TMTAXE (tax exemption code master), and TMCUST (only the customer's own
    tax-exemption fields — it does not duplicate customer_360's broader
    customer query).
    """

    _AUTHORITY_COLUMNS = """
        TTAXAUTH,
        TTAXCODSTE,
        TRIM(TTAXSTEABR) AS TTAXSTEABR,
        TRIM(TTAXDSC) AS TTAXDSC,
        TRIM(TTAXTYPCD) AS TTAXTYPCD,
        TTAXRATPCT,
        TTAXAMTMAX,
        TRIM(TTAXFETYN) AS TTAXFETYN,
        TRIM(TTAXSLCTFG) AS TTAXSLCTFG,
        TTAXAUTNXT,
        TTAXSTENXT,
        TRIM(TTAXCODDEL) AS TTAXCODDEL,
        TRIM(TTAXDTECRT) AS TTAXDTECRT,
        TRIM(TTAXDTECHG) AS TTAXDTECHG,
        TRIM(TTAXUSRCRT) AS TTAXUSRCRT,
        TRIM(TTAXUSRCHG) AS TTAXUSRCHG
    """

    _EXEMPTION_COLUMNS = """
        TRIM(TTXECODEXE) AS TTXECODEXE,
        TTXECODSTE,
        TRIM(TTXEDSC) AS TTXEDSC,
        TRIM(TTXETYPCD) AS TTXETYPCD,
        TRIM(TTXEOORP) AS TTXEOORP,
        TTXEPCTTAX,
        TTXERATPCT,
        TTXEMAXTAX,
        TRIM(TTXECODDEL) AS TTXECODDEL,
        TRIM(TTXEDTECRT) AS TTXEDTECRT,
        TRIM(TTXEDTECHG) AS TTXEDTECHG,
        TRIM(TTXEUSRCRT) AS TTXEUSRCRT,
        TRIM(TTXEUSRCHG) AS TTXEUSRCHG
    """

    def search_tax_authorities(
        self,
        *,
        state_abbreviation: str = "",
        tax_type_code: str = "",
        active_only: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        parameters: list[Any] = []

        state_value = state_abbreviation.strip()
        if state_value:
            conditions.append("TRIM(TTAXSTEABR) = %s")
            parameters.append(state_value.upper())

        type_value = tax_type_code.strip()
        if type_value:
            conditions.append("TRIM(TTAXTYPCD) = %s")
            parameters.append(type_value.upper())

        if active_only:
            conditions.append(
                "COALESCE(NULLIF(TRIM(TTAXCODDEL), ''), 'A') = 'A'"
            )

        where_clause = (
            "WHERE " + " AND ".join(conditions) if conditions else ""
        )

        sql = f"""
        SELECT {self._AUTHORITY_COLUMNS}
        FROM TMTAX
        {where_clause}
        ORDER BY TRIM(TTAXSTEABR), TTAXCODSTE, TTAXAUTH
        LIMIT %s OFFSET %s
        """
        parameters.extend([limit, offset])
        return madden_database.fetch_all(sql, parameters)

    def get_tax_authority(
        self,
        tax_authority: int,
        state_code: int,
    ) -> dict[str, Any] | None:
        sql = f"""
        SELECT {self._AUTHORITY_COLUMNS}
        FROM TMTAX
        WHERE TTAXAUTH = %s AND TTAXCODSTE = %s
        LIMIT 1
        """
        return madden_database.fetch_one(sql, (tax_authority, state_code))

    def search_exemption_codes(
        self,
        *,
        state_code: int | None = None,
        tax_type_code: str = "",
        active_only: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        parameters: list[Any] = []

        if state_code is not None:
            conditions.append("TTXECODSTE = %s")
            parameters.append(state_code)

        type_value = tax_type_code.strip()
        if type_value:
            conditions.append("TRIM(TTXETYPCD) = %s")
            parameters.append(type_value.upper())

        if active_only:
            conditions.append(
                "COALESCE(NULLIF(TRIM(TTXECODDEL), ''), 'A') = 'A'"
            )

        where_clause = (
            "WHERE " + " AND ".join(conditions) if conditions else ""
        )

        sql = f"""
        SELECT {self._EXEMPTION_COLUMNS}
        FROM TMTAXE
        {where_clause}
        ORDER BY TRIM(TTXECODEXE), TTXECODSTE
        LIMIT %s OFFSET %s
        """
        parameters.extend([limit, offset])
        return madden_database.fetch_all(sql, parameters)

    def get_exemption_codes_by_code(
        self,
        exempt_code: str,
    ) -> list[dict[str, Any]]:
        sql = f"""
        SELECT {self._EXEMPTION_COLUMNS}
        FROM TMTAXE
        WHERE TRIM(TTXECODEXE) = %s
        ORDER BY TTXECODSTE
        """
        return madden_database.fetch_all(sql, (exempt_code,))

    def get_exemption_codes_by_codes(
        self,
        exempt_codes: list[str],
    ) -> list[dict[str, Any]]:
        """Batched sibling of get_exemption_codes_by_code() - one query for
        however many distinct exempt_codes are given, instead of one query
        per customer being checked."""

        if not exempt_codes:
            return []
        placeholders = ", ".join(["%s"] * len(exempt_codes))
        sql = f"""
        SELECT {self._EXEMPTION_COLUMNS}
        FROM TMTAXE
        WHERE TRIM(TTXECODEXE) IN ({placeholders})
        ORDER BY TRIM(TTXECODEXE), TTXECODSTE
        """
        return madden_database.fetch_all(sql, tuple(exempt_codes))

    def get_customer_tax_fields(
        self,
        customer_number: int,
    ) -> dict[str, Any] | None:
        return madden_database.fetch_one(
            """
            SELECT
                CUNUMBER,
                TRIM(CUNAME) AS CUNAME,
                CUSTATE,
                TRIM(CUTAXEXCD) AS CUTAXEXCD,
                TRIM(CUFETEXMPT) AS CUFETEXMPT,
                TRIM(CUDTETXEXP) AS CUDTETXEXP
            FROM TMCUST
            WHERE CUNUMBER = %s
            LIMIT 1
            """,
            (customer_number,),
        )

    def get_customers_tax_fields(
        self,
        customer_numbers: list[int],
    ) -> list[dict[str, Any]]:
        if not customer_numbers:
            return []
        placeholders = ", ".join(["%s"] * len(customer_numbers))
        sql = f"""
        SELECT
            CUNUMBER,
            TRIM(CUNAME) AS CUNAME,
            CUSTATE,
            TRIM(CUTAXEXCD) AS CUTAXEXCD,
            TRIM(CUFETEXMPT) AS CUFETEXMPT,
            TRIM(CUDTETXEXP) AS CUDTETXEXP
        FROM TMCUST
        WHERE CUNUMBER IN ({placeholders})
        """
        return madden_database.fetch_all(sql, list(customer_numbers))


tax_compliance_repository = TaxComplianceRepository()
