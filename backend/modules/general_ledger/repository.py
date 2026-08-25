from __future__ import annotations

from typing import Any

from core.database import madden_database


class GeneralLedgerRepository:
    """Read-only MaddenCo (DTA273) evidence for the General Ledger module.

    Every method issues a parameterized SELECT against MaddenCo through the
    shared read-only `madden_database` gateway. This repository never writes
    to the ERP.
    """

    # ------------------------------------------------------------------
    # GMGM — chart of accounts
    # ------------------------------------------------------------------

    def search_accounts(
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
                    CAST(GMNB AS CHAR) LIKE %s
                    OR TRIM(GMDCRACT) LIKE %s
                    OR TRIM(GMDCRACTSH) LIKE %s
                )
                """
            )
            parameters.extend([wildcard] * 3)

        if active_only:
            conditions.append("TRIM(GMYNACTIVE) = 'Y'")

        where_clause = (
            "WHERE " + " AND ".join(conditions) if conditions else ""
        )

        sql = f"""
        SELECT
            GMNB,
            GMNBDIV,
            GMNBDPT,
            TRIM(GMDCRACT) AS GMDCRACT,
            TRIM(GMDCRACTSH) AS GMDCRACTSH,
            TRIM(GMCDDBCR) AS GMCDDBCR,
            TRIM(GMTYPACT) AS GMTYPACT,
            TRIM(GMYNACTIVE) AS GMYNACTIVE
        FROM GMGM
        {where_clause}
        ORDER BY GMNB, GMNBDIV, GMNBDPT
        LIMIT %s OFFSET %s
        """
        parameters.extend([limit, offset])
        return madden_database.fetch_all(sql, parameters)

    def get_account(
        self,
        account_number: int,
        division: int,
        department: int,
    ) -> dict[str, Any] | None:
        return madden_database.fetch_one(
            """
            SELECT
                GMNB,
                GMNBCO,
                GMNBDIV,
                GMNBDPT,
                TRIM(GMDCRACT) AS GMDCRACT,
                TRIM(GMDCRACTSH) AS GMDCRACTSH,
                TRIM(GMCDDBCR) AS GMCDDBCR,
                TRIM(GMTYPACT) AS GMTYPACT,
                TRIM(GMYNACTIVE) AS GMYNACTIVE,
                TRIM(GMYNCST) AS GMYNCST,
                TRIM(GMYNEMP) AS GMYNEMP,
                TRIM(GMYNJOB) AS GMYNJOB,
                TRIM(GMYNPO) AS GMYNPO,
                GMDTECRT,
                GMDTECHG,
                TRIM(GMUSRCRT) AS GMUSRCRT,
                TRIM(GMUSRCHG) AS GMUSRCHG
            FROM GMGM
            WHERE GMNB = %s AND GMNBDIV = %s AND GMNBDPT = %s
            LIMIT 1
            """,
            (account_number, division, department),
        )

    # ------------------------------------------------------------------
    # GMBL — balances by period/year
    # ------------------------------------------------------------------

    def get_balances(
        self,
        account_number: int,
        division: int,
        department: int,
        *,
        year_from: int,
        period_from: int,
        year_to: int,
        period_to: int,
    ) -> list[dict[str, Any]]:
        return madden_database.fetch_all(
            """
            SELECT GBYR, GBPR, GBAMT
            FROM GMBL
            WHERE GMNB = %s AND GMNBDIV = %s AND GMNBDPT = %s
              AND (GBYR > %s OR (GBYR = %s AND GBPR >= %s))
              AND (GBYR < %s OR (GBYR = %s AND GBPR <= %s))
            ORDER BY GBYR, GBPR
            """,
            (
                account_number,
                division,
                department,
                year_from,
                year_from,
                period_from,
                year_to,
                year_to,
                period_to,
            ),
        )

    def get_balance_for_period(
        self,
        account_number: int,
        division: int,
        department: int,
        year: int,
        period: int,
    ) -> dict[str, Any] | None:
        return madden_database.fetch_one(
            """
            SELECT GBAMT
            FROM GMBL
            WHERE GMNB = %s AND GMNBDIV = %s AND GMNBDPT = %s
              AND GBYR = %s AND GBPR = %s
            LIMIT 1
            """,
            (account_number, division, department, year, period),
        )

    # ------------------------------------------------------------------
    # GMAD — posted audit/transaction detail, left joined to GTJT
    # ------------------------------------------------------------------

    def get_posted_transactions(
        self,
        account_number: int,
        division: int,
        department: int,
        *,
        year: int,
        period: int,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        return madden_database.fetch_all(
            """
            SELECT
                audit.GASEQ,
                audit.GAYR,
                audit.GAPR,
                audit.GAAMT,
                TRIM(audit.GACDDBCR) AS GACDDBCR,
                TRIM(audit.GADSR) AS GADSR,
                TRIM(audit.GACDSYS) AS GACDSYS,
                audit.GADTCRT,
                audit.GADTPST,
                audit.GAJEDTECRT,
                audit.GAJETIMCRT,
                TRIM(audit.GAJEUSRCRT) AS GAJEUSRCRT,
                TRIM(audit.GAJEWSCRT) AS GAJEWSCRT,
                audit.GANBCST,
                audit.GANBEMP,
                audit.GANBJOB,
                audit.GANBPO,
                audit.GANBREF,
                audit.GANBREFRC,
                audit.GAMEMOID,
                header.GJHNBREF AS JE_REF,
                header.GJTPR AS JE_PR,
                header.GJTYR AS JE_YR,
                header.GMNBCO AS JE_CO,
                header.GJTTOTDB AS JE_TOTAL_DB,
                header.GJTTOTCR AS JE_TOTAL_CR,
                TRIM(header.GJTFLG) AS JE_FLAG
            FROM GMAD AS audit
            LEFT JOIN GTJT AS header
                ON header.GJHNBREF = audit.GANBREF
               AND header.GJTPR = audit.GAPR
               AND header.GJTYR = audit.GAYR
            WHERE audit.GMNB = %s AND audit.GMNBDIV = %s
              AND audit.GMNBDPT = %s
              AND audit.GAYR = %s AND audit.GAPR = %s
            ORDER BY audit.GASEQ
            LIMIT %s OFFSET %s
            """,
            (account_number, division, department, year, period, limit, offset),
        )

    def get_posted_totals(
        self,
        account_number: int,
        division: int,
        department: int,
        *,
        year: int,
        period: int,
    ) -> list[dict[str, Any]]:
        """Debit/credit totals for the FULL matching set (not paginated),
        used for the reconciliation check regardless of the transaction
        page size shown to the user."""

        return madden_database.fetch_all(
            """
            SELECT
                TRIM(GACDDBCR) AS GACDDBCR,
                SUM(GAAMT) AS TOTAL_AMT,
                COUNT(*) AS LINE_COUNT
            FROM GMAD
            WHERE GMNB = %s AND GMNBDIV = %s AND GMNBDPT = %s
              AND GAYR = %s AND GAPR = %s
            GROUP BY TRIM(GACDDBCR)
            """,
            (account_number, division, department, year, period),
        )

    # ------------------------------------------------------------------
    # GTJD — unposted journal entry detail (in-progress, not historical)
    # ------------------------------------------------------------------

    def get_unposted_journal_entry_lines(
        self,
        account_number: int,
        division: int,
        department: int,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return madden_database.fetch_all(
            """
            SELECT
                GJHNBREF,
                GJDNBSEQ,
                GMNB,
                GMNBDIV,
                GMNBDPT,
                GJDAMTDB,
                GJDAMTCR,
                TRIM(GJDDSC) AS GJDDSC,
                GJDNBCST,
                GJDNBEMP,
                GJDNBJOB,
                GJDNBPO
            FROM GTJD
            WHERE GMNB = %s AND GMNBDIV = %s AND GMNBDPT = %s
            ORDER BY GJHNBREF DESC, GJDNBSEQ
            LIMIT %s
            """,
            (account_number, division, department, limit),
        )

    # ------------------------------------------------------------------
    # GMSH / GMSD — standard (recurring/template) journal entries
    # ------------------------------------------------------------------

    def search_templates(
        self,
        *,
        search: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        parameters: list[Any] = []

        search_value = search.strip()
        if search_value:
            wildcard = f"%{search_value}%"
            conditions.append(
                """
                (
                    TRIM(GSJNAME) LIKE %s
                    OR TRIM(GSJHDSC) LIKE %s
                    OR TRIM(GSJHDSCJE) LIKE %s
                )
                """
            )
            parameters.extend([wildcard] * 3)

        where_clause = (
            "WHERE " + " AND ".join(conditions) if conditions else ""
        )

        sql = f"""
        SELECT
            TRIM(GSJNAME) AS GSJNAME,
            TRIM(GSJHDSC) AS GSJHDSC,
            TRIM(GSJHDSCJE) AS GSJHDSCJE,
            TRIM(GSJHCDSTAT) AS GSJHCDSTAT
        FROM GMSH
        {where_clause}
        ORDER BY GSJNAME
        LIMIT %s
        """
        parameters.append(limit)
        return madden_database.fetch_all(sql, parameters)

    def get_template(self, name: str) -> dict[str, Any] | None:
        return madden_database.fetch_one(
            """
            SELECT
                TRIM(GSJNAME) AS GSJNAME,
                TRIM(GSJHDSC) AS GSJHDSC,
                TRIM(GSJHDSCJE) AS GSJHDSCJE,
                TRIM(GSJHCDSTAT) AS GSJHCDSTAT,
                GSJHNBSEQN,
                TRIM(GSJHUSRCRT) AS GSJHUSRCRT,
                TRIM(GSJHUSRLST) AS GSJHUSRLST
            FROM GMSH
            WHERE TRIM(GSJNAME) = %s
            LIMIT 1
            """,
            (name,),
        )

    def get_template_lines(self, name: str) -> list[dict[str, Any]]:
        return madden_database.fetch_all(
            """
            SELECT
                GSJDNBSEQ,
                GMNB,
                GMNBDIV,
                GMNBDPT,
                GSJDAMTDB,
                GSJDAMTCR,
                TRIM(GSJDDSCJE) AS GSJDDSCJE,
                GSJDNBCST,
                GSJDNBEMP,
                GSJDNBJOB,
                GSJDNBPO
            FROM GMSD
            WHERE TRIM(GSJNAME) = %s
            ORDER BY GSJDNBSEQ
            """,
            (name,),
        )


general_ledger_repository = GeneralLedgerRepository()
