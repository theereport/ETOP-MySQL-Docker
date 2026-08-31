from __future__ import annotations

from datetime import date
from typing import Any

from core.database import madden_database


class ERPEvidenceRepository:
    """Bounded ERP queries with no mutation method or write statement."""

    OPEN_AR_MAX_LIMIT = 500
    RELATED_ACCOUNT_LIMIT = 250
    AP_HEADER_LIMIT = 25
    AP_DETAIL_LIMIT = 100
    AP_GL_LIMIT = 100
    AP_PO_MATCH_LIMIT = 50
    AP_INPUT_LIMIT = 100
    AP_SCHEMA_COLUMN_LIMIT = 1000
    AP_VENDOR_SEARCH_LIMIT = 25
    AP_INVOICE_SEARCH_LIMIT = 50
    AP_SPEND_VENDOR_LIMIT = 10
    AP_SPEND_MONTHLY_PERIOD_LIMIT = 12
    AP_SPEND_MONTHLY_LEADER_LIMIT = 10
    AP_SPEND_MONTHLY_VENDOR_IDENTITY_LIMIT = (
        AP_SPEND_MONTHLY_PERIOD_LIMIT * AP_SPEND_MONTHLY_LEADER_LIMIT
    )

    AP_SPEND_MAPPING: dict[str, tuple[str, ...]] = {
        "PMGLDS": (
            "PMGNBVND",
            "PMGNBINV",
            "PMGAMTINV",
            "PMGDTEINV",
            "PMGNBGLDV",
            "PMGNBGL",
            "PMGPR",
            "PMGYR",
        ),
        "PMVEND": (
            "PVNUMVEN",
            "PVNAMVEN",
        ),
    }

    AP_SOURCE_MAPPING: dict[str, dict[str, Any]] = {
        "vendor_master": {
            "table_name": "PMVEND",
            "required_fields": ["PVNUMVEN", "PVNAMVEN"],
            "evidence_columns": [
                "PVNUMVEN", "PVNAMVEN", "PVNAMSRT", "PVTYPVEN",
                "PVCODDEL", "PVCODTREM", "PVPOREQ", "PVFLGNORCV",
                "PVNUMGLDV", "PVNUMGLDP", "PVNUMGL", "PVDTELPD",
                "PVAMTLPD",
            ],
        },
        "posted_invoice_history": {
            "table_name": "PMHD",
            "required_fields": ["PMHNBVND", "PMHNBINV", "PMHAMTINV"],
            "evidence_columns": [
                "PMHNBVND", "PMHNBINV", "PMHNBPMT", "PMHAMTINV",
                "PMHAMTDIS", "PMHDTEINV", "PMHDTEDUE", "PMHNBCHK",
                "PMHDTECHK", "PMHFLGHLD", "PMHCODSEL", "PMHGLREF",
            ],
        },
        "po_receiver_reference": {
            "table_name": "PMDT",
            "required_fields": ["PMDNBVND", "PMDNBINV", "PMDNBPORV"],
            "evidence_columns": [
                "PMDNBVND", "PMDNBINV", "PMDSEQ", "PMDNBPORV",
                "PMDAMT", "PMDQTY", "PMDNBGLDV", "PMDNBGLDP", "PMDNBGL",
            ],
        },
        "gl_distribution": {
            "table_name": "PMGLDS",
            "required_fields": ["PMGNBVND", "PMGNBINV", "PMGNBGL", "PMGAMTINV"],
            "evidence_columns": [
                "PMGNBVND", "PMGNBINV", "PMGNBPMT", "PMGNBSEQ",
                "PMGAMTINV", "PMGDTEINV", "PMGNBGLDV", "PMGNBGLDP", "PMGNBGL",
                "PMGPR", "PMGYR",
            ],
        },
        "input_invoice": {
            "table_name": "PTHD",
            "required_fields": ["PTHNBVND", "PTHNBINV", "PTHAMTINV", "PTHSTAT"],
            "evidence_columns": [
                "PTHNBVND", "PTHNBINV", "PTHAMTINV", "PTHDTEDUE",
                "PTHDTEINV", "PTHSTAT", "PTHNBPY", "PTHPR", "PTHYR",
            ],
        },
        "input_invoice_detail": {
            "table_name": "PTDT",
            "required_fields": ["PTHNBVND", "PTHNBINV", "PTDNBPORV"],
            "evidence_columns": [
                "PTHNBVND", "PTHNBINV", "PTDSEQ", "PTDDSC",
                "PTDAMT", "PTDQTY", "PTDNBGLDV", "PTDNBGLDP",
                "PTDNBGL", "PTDNBPORV", "PTDNBCST", "PTDNBJOB",
            ],
        },
        "input_payment_split": {
            "table_name": "PTPY",
            "required_fields": ["PTHNBVND", "PTHNBINV", "PTYAMT", "PTYDTEDUE"],
            "evidence_columns": [
                "PTHNBVND", "PTHNBINV", "PTYSEQ", "PTYAMT",
                "PTYAMTDIS", "PTYDISCABL", "PTYDISCPRC", "PTYDTEDUE",
            ],
        },
    }

    AP_CATEGORY_REQUIREMENTS: dict[str, tuple[str, ...]] = {
        "vendor_master": ("PVNUMVEN", "PVNAMVEN"),
        "posted_invoice_history": ("PMHNBVND", "PMHNBINV", "PMHAMTINV"),
        "po_receiver_reference": ("PMDNBVND", "PMDNBINV", "PMDNBPORV"),
        "gl_distribution": ("PMGNBVND", "PMGNBINV", "PMGNBGL", "PMGAMTINV"),
        "input_invoice": ("PTHNBVND", "PTHNBINV", "PTHAMTINV", "PTHSTAT"),
        "input_invoice_detail": ("PTHNBVND", "PTHNBINV", "PTDNBPORV"),
        "input_payment_split": ("PTHNBVND", "PTHNBINV", "PTYAMT", "PTYDTEDUE"),
    }

    def __init__(self, database=madden_database) -> None:
        self.database = database

    def get_credit_customer(self, customer_number: int) -> dict[str, Any] | None:
        return self.database.fetch_one(
            """
            SELECT
                CUNUMBER,
                TRIM(CUNAME) AS CUNAME,
                CUNUMENT,
                CUCRLIMIT,
                CUBALANCE,
                CUONORDER,
                CUONORDAR
            FROM TMCUST
            WHERE CUNUMBER = %s
            LIMIT 1
            """,
            (customer_number,),
        )

    def get_open_ar(
        self,
        customer_number: int,
        *,
        limit: int,
    ) -> tuple[list[dict[str, Any]], bool]:
        bounded_limit = max(1, min(limit, self.OPEN_AR_MAX_LIMIT))
        rows = self.database.fetch_all(
            f"""
            SELECT
                TARONUMCST AS customer_number,
                TARONUMINV AS invoice_number,
                TARONUMCNT AS invoice_count,
                TARODTE AS invoice_date,
                TARODTEDUE AS due_date,
                TAROAMTORG AS original_amount,
                TAROAMTOPN AS open_amount,
                TARODBCR AS debit_credit,
                TAROTYPTRN AS transaction_type,
                TARONUMREF AS reference_number,
                TAROSTRSEL AS selling_store
            FROM TMAROP
            WHERE TARONUMCST = %s
              AND TAROAMTOPN <> 0
            ORDER BY
                TARODTEDUE,
                TARODTE,
                TARONUMINV,
                TARONUMCNT
            LIMIT {bounded_limit + 1}
            """,
            (customer_number,),
        )
        return rows[:bounded_limit], len(rows) <= bounded_limit

    def get_related_accounts(
        self,
        customer_number: int,
        enterprise_number: str | None,
    ) -> tuple[list[dict[str, Any]], bool]:
        enterprise = str(enterprise_number or "").strip().removesuffix(".0")
        predicates = ["CUNUMBER = %s"]
        parameters: list[Any] = [customer_number]
        if enterprise and enterprise != "0":
            predicates.extend(["CUNUMBER = %s", "CUNUMENT = %s"])
            parameters.extend([enterprise, enterprise])
        rows = self.database.fetch_all(
            f"""
            SELECT
                CUNUMBER,
                TRIM(CUNAME) AS CUNAME,
                CUNUMENT,
                CUCRLIMIT,
                CUBALANCE,
                CUONORDER,
                CUONORDAR
            FROM TMCUST
            WHERE {" OR ".join(f"({item})" for item in predicates)}
            ORDER BY CUNUMBER
            LIMIT {self.RELATED_ACCOUNT_LIMIT + 1}
            """,
            tuple(parameters),
        )
        return rows[: self.RELATED_ACCOUNT_LIMIT], len(rows) <= self.RELATED_ACCOUNT_LIMIT

    def inspect_confirmed_ap_mapping(
        self,
    ) -> tuple[dict[str, list[dict[str, Any]]], int, bool]:
        table_names = [
            mapping["table_name"] for mapping in self.AP_SOURCE_MAPPING.values()
        ]
        placeholders = ", ".join(["%s"] * len(table_names))
        rows = self.database.fetch_all(
            f"""
            SELECT
                TABLE_NAME AS table_name,
                COLUMN_NAME AS column_name
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME IN ({placeholders})
            ORDER BY TABLE_NAME, ORDINAL_POSITION
            LIMIT {self.AP_SCHEMA_COLUMN_LIMIT + 1}
            """,
            tuple(table_names),
        )
        complete = len(rows) <= self.AP_SCHEMA_COLUMN_LIMIT
        bounded_rows = rows[: self.AP_SCHEMA_COLUMN_LIMIT]
        grouped: dict[str, set[str]] = {}
        for row in bounded_rows:
            table_name = str(row.get("table_name") or "").strip().upper()
            column_name = str(row.get("column_name") or "").strip().upper()
            if table_name and column_name:
                grouped.setdefault(table_name, set()).add(column_name)

        candidates: dict[str, list[dict[str, Any]]] = {}
        for category, mapping in self.AP_SOURCE_MAPPING.items():
            table_name = mapping["table_name"]
            actual_columns = grouped.get(table_name, set())
            required_fields = mapping["required_fields"]
            matched = [field for field in required_fields if field in actual_columns]
            missing = [field for field in required_fields if field not in actual_columns]
            candidates[category] = [{
                "category": category,
                "table_name": table_name,
                "required_fields_matched": matched,
                "missing_fields": missing,
                "matched_columns": {
                    field: [field] for field in matched
                },
                "evidence_columns": mapping["evidence_columns"],
                "selection_state": "confirmed_source_record",
                "source_rows_read": False,
            }]
        return candidates, len(bounded_rows), complete

    def get_ap_vendor(self, vendor_number: int) -> dict[str, Any] | None:
        return self.database.fetch_one(
            """
            SELECT
                PVNUMVEN AS vendor_number,
                TRIM(PVNAMVEN) AS vendor_name,
                TRIM(PVNAMSRT) AS sort_name,
                PVTYPVEN AS vendor_type_code,
                PVCODDEL AS delete_code,
                PVCODTREM AS terms_code,
                PVPOREQ AS po_required_code,
                PVFLGNORCV AS no_ap_from_receipt_code,
                PVNUMGLDV AS default_gl_division,
                PVNUMGLDP AS default_gl_department,
                PVNUMGL AS default_gl_account,
                PVDTELPD AS last_paid_date,
                PVAMTLPD AS last_paid_amount
            FROM PMVEND
            WHERE PVNUMVEN = %s
            LIMIT 1
            """,
            (vendor_number,),
        )

    def search_ap_vendors(
        self,
        query: str,
        *,
        limit: int,
    ) -> tuple[list[dict[str, Any]], bool]:
        bounded_limit = max(1, min(limit, self.AP_VENDOR_SEARCH_LIMIT))
        normalized_query = query.strip()
        if normalized_query.isdigit():
            predicate = "PVNUMVEN = %s"
            parameters: tuple[Any, ...] = (int(normalized_query),)
        else:
            predicate = """
                (
                    LOCATE(%s, UPPER(TRIM(PVNAMVEN))) > 0
                    OR LOCATE(%s, UPPER(TRIM(PVNAMSRT))) > 0
                )
            """
            upper_query = normalized_query.upper()
            parameters = (upper_query, upper_query)

        rows = self.database.fetch_all(
            f"""
            SELECT
                PVNUMVEN AS vendor_number,
                TRIM(PVNAMVEN) AS vendor_name,
                TRIM(PVNAMSRT) AS sort_name
            FROM PMVEND
            WHERE {predicate}
            ORDER BY
                CASE
                    WHEN PVNUMVEN = %s THEN 0
                    WHEN UPPER(TRIM(PVNAMVEN)) = %s THEN 1
                    ELSE 2
                END,
                TRIM(PVNAMVEN),
                PVNUMVEN
            LIMIT {bounded_limit + 1}
            """,
            parameters
            + (
                int(normalized_query) if normalized_query.isdigit() else -1,
                normalized_query.upper(),
            ),
        )
        return rows[:bounded_limit], len(rows) <= bounded_limit

    def search_ap_posted_invoice_identities(
        self,
        *,
        vendor_numbers: list[int] | None,
        invoice_number: str | None,
        limit: int,
    ) -> tuple[list[dict[str, Any]], bool]:
        bounded_limit = max(1, min(limit, self.AP_INVOICE_SEARCH_LIMIT))
        predicates: list[str] = []
        parameters: list[Any] = []
        if vendor_numbers:
            placeholders = ", ".join(["%s"] * len(vendor_numbers))
            predicates.append(f"H.PMHNBVND IN ({placeholders})")
            parameters.extend(vendor_numbers)
        if invoice_number:
            predicates.append("TRIM(H.PMHNBINV) = %s")
            parameters.append(invoice_number.strip())
        if not predicates:
            raise ValueError(
                "A vendor candidate or exact invoice number is required."
            )

        rows = self.database.fetch_all(
            f"""
            SELECT
                H.PMHNBVND AS vendor_number,
                TRIM(V.PVNAMVEN) AS vendor_name,
                TRIM(H.PMHNBINV) AS invoice_number,
                COUNT(*) AS posted_header_row_count,
                MAX(H.PMHDTEINV) AS latest_invoice_date,
                MAX(H.PMHDTEDUE) AS latest_due_date
            FROM PMHD AS H
            LEFT JOIN PMVEND AS V
                ON V.PVNUMVEN = H.PMHNBVND
            WHERE {" AND ".join(f"({item})" for item in predicates)}
            GROUP BY
                H.PMHNBVND,
                TRIM(V.PVNAMVEN),
                TRIM(H.PMHNBINV)
            ORDER BY
                MAX(H.PMHDTEINV) DESC,
                H.PMHNBVND,
                TRIM(H.PMHNBINV)
            LIMIT {bounded_limit + 1}
            """,
            tuple(parameters),
        )
        return rows[:bounded_limit], len(rows) <= bounded_limit

    def get_ap_posted_headers(
        self, vendor_number: int, invoice_number: str
    ) -> tuple[list[dict[str, Any]], bool]:
        rows = self.database.fetch_all(
            f"""
            SELECT
                PMHNBVND AS vendor_number,
                TRIM(PMHNBINV) AS invoice_number,
                PMHNBPMT AS payment_number,
                PMHAMTINV AS invoice_amount,
                PMHAMTDIS AS discount_amount,
                TRIM(PMHDSC) AS invoice_description,
                PMHDTEINV AS invoice_date,
                PMHDTEDUE AS due_date,
                PMHDTECRT AS created_date,
                PMHDTECHG AS changed_date,
                PMHNBCHK AS check_number,
                PMHDTECHK AS check_date,
                PMHFLGHLD AS hold_flag,
                PMHCODSEL AS selection_code,
                PMHCODDIS AS discount_taken_code,
                PMHGLREF AS gl_reference,
                PMHGLREFCK AS check_gl_reference,
                PMHGLREFVD AS void_gl_reference,
                PMHGLREFVC AS void_check_gl_reference,
                PMHPR AS accounting_period,
                PMHYR AS accounting_year
            FROM PMHD
            WHERE PMHNBVND = %s AND PMHNBINV = %s
            ORDER BY PMHNBPMT, PMHYR, PMHPR
            LIMIT {self.AP_HEADER_LIMIT + 1}
            """,
            (vendor_number, invoice_number),
        )
        return rows[: self.AP_HEADER_LIMIT], len(rows) <= self.AP_HEADER_LIMIT

    def get_ap_posted_details(
        self, vendor_number: int, invoice_number: str
    ) -> tuple[list[dict[str, Any]], bool]:
        rows = self.database.fetch_all(
            f"""
            SELECT
                PMDSEQ AS sequence_number,
                TRIM(PMDDSC) AS line_description,
                PMDAMT AS line_amount,
                PMDQTY AS quantity,
                PMDNBGLDV AS gl_division,
                PMDNBGLDP AS gl_department,
                PMDNBGL AS gl_account,
                PMDNBPORV AS po_receiver_reference,
                PMDNBCST AS customer_number,
                PMDNBJOB AS job_number
            FROM PMDT
            WHERE PMDNBVND = %s AND PMDNBINV = %s
            ORDER BY PMDSEQ
            LIMIT {self.AP_DETAIL_LIMIT + 1}
            """,
            (vendor_number, invoice_number),
        )
        return rows[: self.AP_DETAIL_LIMIT], len(rows) <= self.AP_DETAIL_LIMIT

    def get_ap_gl_distributions(
        self, vendor_number: int, invoice_number: str
    ) -> tuple[list[dict[str, Any]], bool]:
        rows = self.database.fetch_all(
            f"""
            SELECT
                PMGNBSEQ AS sequence_number,
                PMGNBPMT AS payment_number,
                PMGAMTINV AS invoice_amount,
                PMGQTY AS quantity,
                TRIM(PMGDSC) AS description,
                PMGDTEINV AS invoice_date,
                PMGNBGLDV AS gl_division,
                PMGNBGLDP AS gl_department,
                PMGNBGL AS gl_account,
                PMGPR AS accounting_period,
                PMGYR AS accounting_year,
                PMGCODPGM AS program_code
            FROM PMGLDS
            WHERE PMGNBVND = %s AND PMGNBINV = %s
            ORDER BY PMGNBPMT, PMGNBSEQ
            LIMIT {self.AP_GL_LIMIT + 1}
            """,
            (vendor_number, invoice_number),
        )
        return rows[: self.AP_GL_LIMIT], len(rows) <= self.AP_GL_LIMIT

    def get_po_receiving_match(
        self, vendor_number: int, invoice_number: str
    ) -> tuple[list[dict[str, Any]], bool]:
        """3-way match evidence: PMDT.PMDNBPORV is a receiving-report
        reference pointing at TTRCVD.TRCHNUMRPT, which in turn carries
        TRCDNUMPO pointing at TMPOHD.TPHNB. TRCHNUMRPT is NOT by itself
        unique - confirmed live that TTRCVD's real primary key is the
        composite (TRCHNUMRPT, TRCDNUMSEQ): a single receiving report
        commonly has dozens of detail lines (one invoice sampled live had
        20). Joining on TRCHNUMRPT alone fans out into every product on
        that receiving report, not the one line this PMDT row actually
        represents.

        PMDT has no product code of its own, but confirmed live across a
        real 20-line invoice that PMDT.PMDSEQ (the AP detail line number,
        1-based) lines up exactly with TTRCVD.TRCDNUMSEQ (0-based) in
        order and quantity for the same receiving report - PMDSEQ = 1
        matches TRCDNUMSEQ = 0, PMDSEQ = 2 matches TRCDNUMSEQ = 1, and so
        on. TRCDNUMSEQ = PMDSEQ - 1 is therefore required in the join, not
        just the receiving-report reference, or the "match" silently
        returns a different product's quantities entirely.

        Confirmed live that only a minority of invoice lines carry a
        nonzero PMDNBPORV at all (most AP activity - rebates, AR-offset,
        differential clearing - has no PO/receiving trail); lines with
        PMDNBPORV = 0 are excluded here, not returned as unmatched rows.
        Confirmed live that TTRCVD.TRCDCOSDIF (the dedicated cost-variance
        column) is 0 across every row ever recorded, and TRCDCOS is
        simply copied from TRCDCOSPO whenever the latter is populated -
        there is no real price-variance signal in receiving data, so this
        method surfaces quantities only, never a cost/price comparison."""

        rows = self.database.fetch_all(
            f"""
            SELECT
                d.PMDSEQ AS sequence_number,
                d.PMDNBPORV AS po_receiver_reference,
                TRIM(r.TRCDNUMPRD) AS product_number,
                r.TRCDNUMPO AS po_number,
                r.TRCDQTY AS quantity_received_this_receipt,
                r.TRCDDTECRT AS receipt_date,
                TRIM(h.TPHFLGCMP) AS po_complete_flag,
                h.TPHDTE AS po_date,
                po_line.TPDQTYORD AS quantity_ordered,
                po_line.TPDQTYRCV AS quantity_received_total,
                po_line.TPDQTYBO AS quantity_backorder,
                d.PMDQTY AS quantity_invoiced,
                d.PMDAMT AS line_amount
            FROM PMDT d
            INNER JOIN TTRCVD r
                ON r.TRCHNUMRPT = d.PMDNBPORV
                AND r.TRCDNUMSEQ = d.PMDSEQ - 1
            LEFT JOIN TMPOHD h
                ON h.TPHNB = r.TRCDNUMPO
            LEFT JOIN TMPODT po_line
                ON po_line.TPHNB = r.TRCDNUMPO
                AND TRIM(po_line.TPDPRD) = TRIM(r.TRCDNUMPRD)
            WHERE d.PMDNBVND = %s
                AND d.PMDNBINV = %s
                AND d.PMDNBPORV != 0
            ORDER BY d.PMDSEQ
            LIMIT {self.AP_PO_MATCH_LIMIT + 1}
            """,
            (vendor_number, invoice_number),
        )
        return rows[: self.AP_PO_MATCH_LIMIT], len(rows) <= self.AP_PO_MATCH_LIMIT

    def get_gl_account_descriptions(
        self, division_and_account: list[tuple[int, int]]
    ) -> dict[tuple[str, str], str]:
        """GMGM (chart of accounts) description for each distinct
        (division, account) pair - confirmed live that GMNBDPT is
        uniformly 0 within a division, so department is not part of the
        match. PMGLDS's own PMGDSC line-memo is usually blank; this is a
        separate, additional field (gl_account_description), not a
        replacement for it."""

        pairs = sorted(set(division_and_account))
        if not pairs:
            return {}
        predicate = " OR ".join(["(GMNBDIV = %s AND GMNB = %s)"] * len(pairs))
        parameters: tuple[Any, ...] = tuple(
            value for pair in pairs for value in pair
        )
        rows = self.database.fetch_all(
            f"""
            SELECT GMNBDIV AS gl_division, GMNB AS gl_account,
                   TRIM(GMDCRACT) AS description
            FROM GMGM
            WHERE {predicate}
            """,
            parameters,
        )
        return {
            (str(row["gl_division"]), str(row["gl_account"])): row["description"]
            for row in rows
            if row.get("description")
        }

    def get_latest_gl_coding_year(self, vendor_number: int) -> int | None:
        """Most recent PMGYR this vendor has any coding activity in -
        confirmed live that ranking a vendor's lifetime PMGLDS history
        (rather than one representative year) dilutes even genuinely
        dominant accounts and makes structural-leg detection unreliable,
        so callers should scope to this single year, matching the
        methodology that was validated live before this was built."""

        row = self.database.fetch_one(
            "SELECT MAX(PMGYR) AS latest_year FROM PMGLDS WHERE PMGNBVND = %s",
            (vendor_number,),
        )
        year = row.get("latest_year") if row else None
        return int(year) if year is not None else None

    def get_vendor_coded_invoice_count(
        self, vendor_number: int, *, year: int
    ) -> int:
        """Total distinct invoices this vendor has any PMGLDS coding for
        within the given accounting year - the denominator for GL-coding
        match percentages."""

        row = self.database.fetch_one(
            """
            SELECT COUNT(DISTINCT PMGNBINV) AS invoice_count
            FROM PMGLDS
            WHERE PMGNBVND = %s AND PMGYR = %s
            """,
            (vendor_number, year),
        )
        return int(row["invoice_count"]) if row else 0

    def get_gl_coding_account_totals(
        self, vendor_number: int, *, year: int
    ) -> list[dict[str, Any]]:
        """Per (division, account) distinct invoice counts for this
        vendor's PMGLDS coding within the given accounting year, most-used
        first. Confirmed live across multiple high-volume vendors that
        this company's fixed double-entry control/clearing legs - GL
        account 1017 (cash) and 2300 (accounts payable control) always
        carry the exact same invoice count as each other, and 1230
        (accounts receivable - vendor / debit-memo clearing) is
        consistently near-universal too - are not a real per-invoice
        coding choice; the caller excludes these specific accounts (see
        `KNOWN_STRUCTURAL_GL_ACCOUNTS`) before treating this as a
        ranking, not merely accounts equal to the vendor's total count,
        since real-world data means even a genuine control leg rarely
        hits exactly 100%."""

        return self.database.fetch_all(
            """
            SELECT
                PMGNBGLDV AS gl_division,
                PMGNBGL AS gl_account,
                COUNT(DISTINCT PMGNBINV) AS invoice_count
            FROM PMGLDS
            WHERE PMGNBVND = %s AND PMGYR = %s
            GROUP BY PMGNBGLDV, PMGNBGL
            ORDER BY invoice_count DESC
            """,
            (vendor_number, year),
        )

    def get_gl_coding_department_breakdown(
        self, vendor_number: int, division_and_account: list[tuple[int, int]]
    ) -> dict[tuple[str, str], str]:
        """Most-common department for each of a short list of (division,
        account) pairs - a real GL account can carry more than one
        department, so this picks the department that actually goes with
        this vendor's historical use of that account, rather than
        assuming department 0."""

        pairs = sorted(set(division_and_account))
        if not pairs:
            return {}
        predicate = " OR ".join(["(PMGNBGLDV = %s AND PMGNBGL = %s)"] * len(pairs))
        parameters: tuple[Any, ...] = (vendor_number, *(
            value for pair in pairs for value in pair
        ))
        rows = self.database.fetch_all(
            f"""
            SELECT PMGNBGLDV AS gl_division, PMGNBGL AS gl_account,
                   PMGNBGLDP AS gl_department, COUNT(*) AS row_count
            FROM PMGLDS
            WHERE PMGNBVND = %s AND ({predicate})
            GROUP BY PMGNBGLDV, PMGNBGL, PMGNBGLDP
            ORDER BY row_count DESC
            """,
            parameters,
        )
        breakdown: dict[tuple[str, str], str] = {}
        for row in rows:
            key = (str(row["gl_division"]), str(row["gl_account"]))
            if key not in breakdown:
                breakdown[key] = str(row["gl_department"])
        return breakdown

    def get_ap_input_headers(
        self, vendor_number: int, invoice_number: str
    ) -> tuple[list[dict[str, Any]], bool]:
        rows = self.database.fetch_all(
            f"""
            SELECT
                PTHNBVND AS vendor_number,
                TRIM(PTHNBINV) AS invoice_number,
                PTHAMTINV AS invoice_amount,
                PTHAMTDIS AS discount_amount,
                PTHDISCABL AS discountable_amount,
                TRIM(PTHDSC) AS invoice_description,
                PTHDTEINV AS invoice_date,
                PTHDTEDUE AS due_date,
                PTHDTECRT AS created_date,
                PTHDTECHG AS changed_date,
                PTHSTAT AS raw_status_code,
                PTHNBPY AS payment_count,
                PTHPR AS accounting_period,
                PTHYR AS accounting_year
            FROM PTHD
            WHERE PTHNBVND = %s AND PTHNBINV = %s
            ORDER BY PTHDTECRT, PTHDTECHG
            LIMIT {self.AP_HEADER_LIMIT + 1}
            """,
            (vendor_number, invoice_number),
        )
        return rows[: self.AP_HEADER_LIMIT], len(rows) <= self.AP_HEADER_LIMIT

    def get_ap_input_details(
        self, vendor_number: int, invoice_number: str
    ) -> tuple[list[dict[str, Any]], bool]:
        rows = self.database.fetch_all(
            f"""
            SELECT
                PTDSEQ AS sequence_number,
                TRIM(PTDDSC) AS line_description,
                PTDAMT AS line_amount,
                PTDQTY AS quantity,
                PTDNBGLDV AS gl_division,
                PTDNBGLDP AS gl_department,
                PTDNBGL AS gl_account,
                PTDNBPORV AS po_receiver_reference,
                PTDNBCST AS customer_number,
                PTDNBJOB AS job_number
            FROM PTDT
            WHERE PTHNBVND = %s AND PTHNBINV = %s
            ORDER BY PTDSEQ
            LIMIT {self.AP_INPUT_LIMIT + 1}
            """,
            (vendor_number, invoice_number),
        )
        return rows[: self.AP_INPUT_LIMIT], len(rows) <= self.AP_INPUT_LIMIT

    def get_ap_input_payment_splits(
        self, vendor_number: int, invoice_number: str
    ) -> tuple[list[dict[str, Any]], bool]:
        rows = self.database.fetch_all(
            f"""
            SELECT
                PTYSEQ AS sequence_number,
                PTYAMT AS payment_amount,
                PTYAMTDIS AS discount_amount,
                PTYDISCABL AS discountable_amount,
                PTYDISCPRC AS discount_percent,
                PTYDTEDUE AS due_date
            FROM PTPY
            WHERE PTHNBVND = %s AND PTHNBINV = %s
            ORDER BY PTYSEQ
            LIMIT {self.AP_HEADER_LIMIT + 1}
            """,
            (vendor_number, invoice_number),
        )
        return rows[: self.AP_HEADER_LIMIT], len(rows) <= self.AP_HEADER_LIMIT

    def inspect_ap_spend_mapping(self) -> dict[str, dict[str, dict[str, Any]]]:
        """Read column metadata only for the fixed AP spend source projection."""

        table_names = tuple(self.AP_SPEND_MAPPING)
        placeholders = ", ".join(["%s"] * len(table_names))
        rows = self.database.fetch_all(
            f"""
            SELECT
                TABLE_NAME AS table_name,
                COLUMN_NAME AS column_name,
                DATA_TYPE AS data_type,
                COLUMN_TYPE AS column_type,
                COLUMN_COMMENT AS column_comment
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME IN ({placeholders})
            ORDER BY TABLE_NAME, ORDINAL_POSITION
            LIMIT {self.AP_SCHEMA_COLUMN_LIMIT + 1}
            """,
            table_names,
        )
        if len(rows) > self.AP_SCHEMA_COLUMN_LIMIT:
            raise RuntimeError(
                "The bounded AP spend schema diagnostic exceeded its column limit."
            )

        mapping: dict[str, dict[str, dict[str, Any]]] = {
            table_name: {} for table_name in table_names
        }
        for row in rows:
            table_name = str(row.get("table_name") or "").strip().upper()
            column_name = str(row.get("column_name") or "").strip().upper()
            if table_name not in mapping or column_name not in self.AP_SPEND_MAPPING[table_name]:
                continue
            mapping[table_name][column_name] = {
                "data_type": str(row.get("data_type") or "").strip().lower(),
                "column_type": str(row.get("column_type") or "").strip(),
                "column_comment": str(row.get("column_comment") or "").strip(),
            }
        return mapping

    @staticmethod
    def _ap_spend_predicates(
        *,
        division: int,
        account: int | None,
        time_basis: str,
        year: int,
        accounting_period: int | None,
        range_start: str | int | None,
        range_end_exclusive: str | int | None,
        calendar_date_encoding: str | None,
    ) -> tuple[list[str], list[Any]]:
        predicates = ["G.PMGNBGLDV = %s"]
        parameters: list[Any] = [division]
        if account is not None:
            predicates.append("G.PMGNBGL = %s")
            parameters.append(account)

        if time_basis == "erp_accounting_year":
            predicates.append("G.PMGYR = %s")
            parameters.append(year)
        elif time_basis == "erp_accounting_period":
            if accounting_period is None:
                raise ValueError("An ERP accounting period is required.")
            predicates.extend(["G.PMGYR = %s", "G.PMGPR = %s"])
            parameters.extend([year, accounting_period])
        elif time_basis == "calendar_invoice_date":
            if range_start is None or range_end_exclusive is None:
                raise ValueError("A bounded calendar invoice-date range is required.")
            if calendar_date_encoding in {"YYYYMMDD", "NATIVE_DATE"}:
                date_expression = "G.PMGDTEINV"
            elif calendar_date_encoding == "MMDDYYYY":
                date_expression = (
                    "STR_TO_DATE(LPAD(CAST(CAST(G.PMGDTEINV AS UNSIGNED) "
                    "AS CHAR), 8, '0'), '%m%d%Y')"
                )
            else:
                raise ValueError(
                    "A governed PMGDTEINV calendar date encoding is required."
                )
            predicates.extend(
                [f"{date_expression} >= %s", f"{date_expression} < %s"]
            )
            parameters.extend([range_start, range_end_exclusive])
        else:
            raise ValueError("Unsupported AP spend time basis.")
        return predicates, parameters

    def get_ap_spend_total(
        self,
        *,
        division: int,
        account: int | None,
        time_basis: str,
        year: int,
        accounting_period: int | None,
        range_start: str | int | None,
        range_end_exclusive: str | int | None,
        calendar_date_encoding: str | None,
    ) -> dict[str, Any]:
        return self._get_ap_spend_total_from(
            self.database,
            division=division,
            account=account,
            time_basis=time_basis,
            year=year,
            accounting_period=accounting_period,
            range_start=range_start,
            range_end_exclusive=range_end_exclusive,
            calendar_date_encoding=calendar_date_encoding,
        )

    def _get_ap_spend_total_from(
        self,
        reader: Any,
        **query_arguments: Any,
    ) -> dict[str, Any]:
        predicates, parameters = self._ap_spend_predicates(**query_arguments)
        return reader.fetch_one(
            f"""
            SELECT
                COUNT(*) AS distribution_row_count,
                COUNT(G.PMGAMTINV) AS amount_available_row_count,
                SUM(CASE WHEN G.PMGAMTINV IS NULL THEN 1 ELSE 0 END)
                    AS missing_amount_row_count,
                COUNT(DISTINCT G.PMGNBVND, G.PMGNBINV)
                    AS invoice_identity_count,
                COUNT(DISTINCT G.PMGNBVND) AS vendor_count,
                COALESCE(SUM(CASE WHEN G.PMGAMTINV > 0
                    THEN G.PMGAMTINV ELSE 0 END), 0)
                    AS positive_distribution_amount,
                COALESCE(SUM(CASE WHEN G.PMGAMTINV < 0
                    THEN G.PMGAMTINV ELSE 0 END), 0)
                    AS negative_distribution_amount,
                COALESCE(SUM(G.PMGAMTINV), 0) AS net_signed_amount
            FROM PMGLDS AS G
            WHERE {" AND ".join(f"({item})" for item in predicates)}
            LIMIT 1
            """,
            tuple(parameters),
        ) or {
            "distribution_row_count": 0,
            "amount_available_row_count": 0,
            "missing_amount_row_count": 0,
            "invoice_identity_count": 0,
            "vendor_count": 0,
            "positive_distribution_amount": 0,
            "negative_distribution_amount": 0,
            "net_signed_amount": 0,
        }

    def get_ap_spend_ranking(
        self,
        *,
        division: int,
        account: int | None,
        time_basis: str,
        year: int,
        accounting_period: int | None,
        range_start: str | int | None,
        range_end_exclusive: str | int | None,
        calendar_date_encoding: str | None,
        limit: int,
    ) -> tuple[list[dict[str, Any]], bool]:
        return self._get_ap_spend_ranking_from(
            self.database,
            division=division,
            account=account,
            time_basis=time_basis,
            year=year,
            accounting_period=accounting_period,
            range_start=range_start,
            range_end_exclusive=range_end_exclusive,
            calendar_date_encoding=calendar_date_encoding,
            limit=limit,
        )

    def _get_ap_spend_ranking_from(
        self,
        reader: Any,
        *,
        limit: int,
        **query_arguments: Any,
    ) -> tuple[list[dict[str, Any]], bool]:
        bounded_limit = max(1, min(limit, self.AP_SPEND_VENDOR_LIMIT))
        predicates, parameters = self._ap_spend_predicates(**query_arguments)
        rows = reader.fetch_all(
            f"""
            SELECT
                G.PMGNBVND AS vendor_number,
                COUNT(*) AS distribution_row_count,
                COUNT(G.PMGAMTINV) AS amount_available_row_count,
                SUM(CASE WHEN G.PMGAMTINV IS NULL THEN 1 ELSE 0 END)
                    AS missing_amount_row_count,
                COUNT(DISTINCT G.PMGNBINV) AS invoice_identity_count,
                COALESCE(SUM(CASE WHEN G.PMGAMTINV > 0
                    THEN G.PMGAMTINV ELSE 0 END), 0)
                    AS positive_distribution_amount,
                COALESCE(SUM(CASE WHEN G.PMGAMTINV < 0
                    THEN G.PMGAMTINV ELSE 0 END), 0)
                    AS negative_distribution_amount,
                COALESCE(SUM(G.PMGAMTINV), 0) AS net_signed_amount
            FROM PMGLDS AS G
            WHERE {" AND ".join(f"({item})" for item in predicates)}
            GROUP BY G.PMGNBVND
            HAVING COUNT(G.PMGAMTINV) > 0
            ORDER BY
                net_signed_amount DESC,
                positive_distribution_amount DESC,
                G.PMGNBVND
            LIMIT {bounded_limit + 1}
            """,
            tuple(parameters),
        )
        return rows[:bounded_limit], len(rows) <= bounded_limit

    def get_ap_vendor_names(self, vendor_numbers: list[int]) -> dict[str, str | None]:
        return self._get_ap_vendor_names_from(self.database, vendor_numbers)

    def _get_ap_vendor_names_from(
        self,
        reader: Any,
        vendor_numbers: list[int],
        *,
        limit: int | None = None,
    ) -> dict[str, str | None]:
        requested_limit = self.AP_SPEND_VENDOR_LIMIT if limit is None else limit
        bounded_limit = max(
            1,
            min(requested_limit, self.AP_SPEND_MONTHLY_VENDOR_IDENTITY_LIMIT),
        )
        bounded = list(dict.fromkeys(vendor_numbers))[:bounded_limit]
        if not bounded:
            return {}
        placeholders = ", ".join(["%s"] * len(bounded))
        rows = reader.fetch_all(
            f"""
            SELECT
                PVNUMVEN AS vendor_number,
                TRIM(PVNAMVEN) AS vendor_name
            FROM PMVEND
            WHERE PVNUMVEN IN ({placeholders})
            ORDER BY PVNUMVEN
            LIMIT {bounded_limit}
            """,
            tuple(bounded),
        )
        return {
            str(row.get("vendor_number") or "").strip().removesuffix(".0"):
                (str(row.get("vendor_name") or "").strip() or None)
            for row in rows
        }

    def get_ap_spend_evidence(
        self,
        *,
        include_ranking: bool,
        include_vendor_names: bool,
        include_monthly: bool = False,
        **query_arguments: Any,
    ) -> dict[str, Any]:
        """Read one AP spend evidence packet in a consistent snapshot."""

        with self.database.read_consistent_snapshot() as snapshot:
            total = self._get_ap_spend_total_from(snapshot, **query_arguments)
            ranking: list[dict[str, Any]] = []
            ranking_complete: bool | None = None
            monthly_rankings: list[dict[str, Any]] = []
            vendor_names: dict[str, str | None] = {}
            vendor_identity_queried = False
            if include_ranking:
                ranking, ranking_complete = self._get_ap_spend_ranking_from(
                    snapshot,
                    **query_arguments,
                    limit=self.AP_SPEND_VENDOR_LIMIT,
                )
            if include_monthly:
                if query_arguments.get("time_basis") != "calendar_invoice_date":
                    raise ValueError(
                        "Monthly vendor leaders require a calendar invoice-date year."
                    )
                year = int(query_arguments.get("year") or 0)
                if year < 2000 or year > 2099:
                    raise ValueError("A bounded four-digit calendar year is required.")
                for month in range(1, self.AP_SPEND_MONTHLY_PERIOD_LIMIT + 1):
                    start = date(year, month, 1)
                    end = (
                        date(year + 1, 1, 1)
                        if month == self.AP_SPEND_MONTHLY_PERIOD_LIMIT
                        else date(year, month + 1, 1)
                    )
                    encoding = query_arguments.get("calendar_date_encoding")
                    if encoding == "YYYYMMDD":
                        range_start: str | int = int(start.strftime("%Y%m%d"))
                        range_end: str | int = int(end.strftime("%Y%m%d"))
                    elif encoding in {"MMDDYYYY", "NATIVE_DATE"}:
                        range_start = start.isoformat()
                        range_end = end.isoformat()
                    else:
                        raise ValueError(
                            "A governed PMGDTEINV calendar date encoding is required."
                        )
                    month_rows, month_complete = self._get_ap_spend_ranking_from(
                        snapshot,
                        division=query_arguments["division"],
                        account=query_arguments.get("account"),
                        time_basis="calendar_invoice_date",
                        year=year,
                        accounting_period=None,
                        range_start=range_start,
                        range_end_exclusive=range_end,
                        calendar_date_encoding=encoding,
                        limit=self.AP_SPEND_MONTHLY_LEADER_LIMIT,
                    )
                    monthly_rankings.append(
                        {
                            "calendar_year": year,
                            "calendar_month": month,
                            "range_start": start.isoformat(),
                            "range_end_exclusive": end.isoformat(),
                            "ranking": month_rows,
                            "ranking_complete": month_complete,
                        }
                    )
            if include_vendor_names:
                vendor_rows = list(ranking)
                for monthly in monthly_rankings:
                    vendor_rows.extend(monthly["ranking"])
                vendor_numbers = [
                    int(str(row.get("vendor_number") or "").strip().removesuffix(".0"))
                    for row in vendor_rows
                    if str(row.get("vendor_number") or "").strip().removesuffix(".0").isdigit()
                ]
                if vendor_numbers:
                    vendor_names = self._get_ap_vendor_names_from(
                        snapshot,
                        vendor_numbers,
                        limit=(
                            self.AP_SPEND_MONTHLY_VENDOR_IDENTITY_LIMIT
                            if include_monthly
                            else self.AP_SPEND_VENDOR_LIMIT
                        ),
                    )
                    vendor_identity_queried = True
            return {
                "total": total,
                "ranking": ranking,
                "ranking_complete": ranking_complete,
                "monthly_rankings": monthly_rankings,
                "vendor_names": vendor_names,
                "vendor_identity_queried": vendor_identity_queried,
                "snapshot_opened_at": snapshot.snapshot_opened_at,
            }


erp_evidence_repository = ERPEvidenceRepository()
