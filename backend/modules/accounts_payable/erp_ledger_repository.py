from __future__ import annotations

import threading
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import case, func, or_, select
from sqlalchemy.engine import Engine

from data.mysql import (
    ap_erp_open_ledger_cache_table,
    ap_erp_vendor_terms_cache_table,
    ap_invoices_table,
    ap_vendor_terms_reference_table,
    ap_warehouse_approval_actions_table,
    get_engine,
    metadata,
)

from .repository import AccountsPayableRepository


_ERP_LEDGER_TABLES = [
    ap_erp_open_ledger_cache_table,
    ap_erp_vendor_terms_cache_table,
    ap_vendor_terms_reference_table,
    ap_warehouse_approval_actions_table,
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_madden_date(value: object) -> date | None:
    """Parse MaddenCo's YYYYMMDD varchar date encoding. Duplicated (not
    imported) from cash_flow_forecasting/computation.py - this module is
    deliberately independent of cash_flow_forecasting, and this is a small,
    generic parsing utility, not shared business logic."""

    text = str(value or "").strip()
    if len(text) != 8 or text == "00000000":
        return None
    try:
        return datetime.strptime(text, "%Y%m%d").date()
    except ValueError:
        return None


class AccountsPayableErpLedgerRepository:
    """Local cache of MaddenCo's open AP ledger (PMHD) and vendor terms
    codes (PMVEND), scanned in full via erp_ledger_scan.py because PMHD has
    5M+ rows with no due-date-usable index (see erp_ledger_scan.py). Not
    append-only - a plain, wholesale-replaced performance cache, same as
    cash_flow_forecasting's cash_flow_ap_due_date_cache, except this one
    retains invoice-level rows instead of pre-aggregated weekly buckets."""

    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_engine()
        self._initialization_lock = threading.Lock()

    def initialize(self) -> None:
        with self._initialization_lock:
            metadata.create_all(
                self._engine, checkfirst=True, tables=_ERP_LEDGER_TABLES
            )

    def replace_open_ledger(self, rows: list[dict[str, Any]]) -> int:
        """Wholesale replace: DELETE + bulk INSERT in one transaction, same
        pattern as cash_flow_forecasting's cache refresh. Rows without a
        usable vendor+invoice identity are skipped (never cached as
        anonymous evidence).

        PMHD's real primary key is (PMHNBVND, PMHNBINV, PMHNBPMT) - an
        invoice can have multiple payment-split rows, which this cache
        intentionally does not select PMHNBPMT for (it needs invoice-level
        totals, not payment-split-level detail). Multiple rows for the same
        vendor+invoice are aggregated here: amounts summed, due date taken
        as the earliest known (a company must plan for the earliest
        installment), on_hold set if any split is on hold - erring toward
        disclosure, not silence."""

        self.initialize()
        refreshed_at = _now()
        aggregated: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            vendor_number = str(row.get("PMHNBVND") or "").strip()
            invoice_number = str(row.get("PMHNBINV") or "").strip()
            if not vendor_number or vendor_number == "0" or not invoice_number:
                continue
            key = (vendor_number, invoice_number)
            invoice_date = parse_madden_date(row.get("PMHDTEINV"))
            due_date = parse_madden_date(row.get("PMHDTEDUE"))
            on_hold = str(row.get("PMHFLGHLD") or "").strip().upper() == "Y"
            amount_invoiced = float(row.get("PMHAMTINV") or 0)
            amount_discount = float(row.get("PMHAMTDIS") or 0)

            existing = aggregated.get(key)
            if existing is None:
                aggregated[key] = {
                    "invoice_date": invoice_date,
                    "due_date": due_date,
                    "amount_invoiced": amount_invoiced,
                    "amount_discount": amount_discount,
                    "on_hold": on_hold,
                }
                continue
            existing["amount_invoiced"] += amount_invoiced
            existing["amount_discount"] += amount_discount
            existing["on_hold"] = existing["on_hold"] or on_hold
            if invoice_date and (
                existing["invoice_date"] is None
                or invoice_date < existing["invoice_date"]
            ):
                existing["invoice_date"] = invoice_date
            if due_date and (
                existing["due_date"] is None or due_date < existing["due_date"]
            ):
                existing["due_date"] = due_date

        prepared = [
            {
                "vendor_number": vendor_number,
                "invoice_number": invoice_number,
                "invoice_date": values["invoice_date"].isoformat()
                if values["invoice_date"]
                else None,
                "due_date": values["due_date"].isoformat()
                if values["due_date"]
                else None,
                "amount_invoiced": values["amount_invoiced"],
                "amount_discount": values["amount_discount"],
                "on_hold": 1 if values["on_hold"] else 0,
                "refreshed_at": refreshed_at,
            }
            for (vendor_number, invoice_number), values in aggregated.items()
        ]

        with self._engine.begin() as connection:
            connection.execute(ap_erp_open_ledger_cache_table.delete())
            for row in prepared:
                connection.execute(
                    ap_erp_open_ledger_cache_table.insert().values(**row)
                )
        return len(prepared)

    def replace_vendor_terms_cache(self, rows: list[dict[str, Any]]) -> int:
        self.initialize()
        refreshed_at = _now()
        prepared = [
            {
                "vendor_number": str(row.get("PVNUMVEN") or "").strip(),
                "terms_code": str(row.get("PVCODTREM") or "").strip() or None,
                "vendor_name": str(row.get("PVNAMVEN") or "").strip() or None,
                "refreshed_at": refreshed_at,
            }
            for row in rows
            if str(row.get("PVNUMVEN") or "").strip()
            and str(row.get("PVNUMVEN") or "").strip() != "0"
        ]
        with self._engine.begin() as connection:
            connection.execute(ap_erp_vendor_terms_cache_table.delete())
            for row in prepared:
                connection.execute(
                    ap_erp_vendor_terms_cache_table.insert().values(**row)
                )
        return len(prepared)

    def open_ledger_refreshed_at(self) -> str | None:
        self.initialize()
        with self._engine.connect() as connection:
            return connection.execute(
                select(func.max(ap_erp_open_ledger_cache_table.c.refreshed_at))
            ).scalar_one_or_none()

    def open_ledger_summary(self, as_of_date: date) -> dict[str, Any]:
        """Aggregates the cached invoice-level open ledger as of a given
        date. On-hold invoices are always broken out separately rather than
        silently folded into or excluded from the other figures, matching
        cash_flow_forecasting's own disclosure precedent for hold status."""

        self.initialize()
        l = ap_erp_open_ledger_cache_table
        as_of = as_of_date.isoformat()
        within_7_days = (as_of_date + timedelta(days=7)).isoformat()
        balance = l.c.amount_invoiced - l.c.amount_discount
        with self._engine.connect() as connection:
            row = connection.execute(
                select(
                    func.count().label("total_count"),
                    func.coalesce(func.sum(balance), 0).label("total_balance"),
                    func.coalesce(
                        func.sum(case((l.c.on_hold == 1, 1), else_=0)), 0
                    ).label("on_hold_count"),
                    func.coalesce(
                        func.sum(case((l.c.on_hold == 1, balance), else_=0)), 0
                    ).label("on_hold_amount"),
                    func.coalesce(
                        func.sum(
                            case(
                                ((l.c.on_hold == 0) & (l.c.due_date == as_of), 1),
                                else_=0,
                            )
                        ),
                        0,
                    ).label("due_today_count"),
                    func.coalesce(
                        func.sum(
                            case(
                                (
                                    (l.c.on_hold == 0) & (l.c.due_date == as_of),
                                    balance,
                                ),
                                else_=0,
                            )
                        ),
                        0,
                    ).label("due_today_amount"),
                    func.coalesce(
                        func.sum(
                            case(
                                (
                                    (l.c.on_hold == 0)
                                    & l.c.due_date.is_not(None)
                                    & (l.c.due_date < as_of),
                                    1,
                                ),
                                else_=0,
                            )
                        ),
                        0,
                    ).label("past_due_count"),
                    func.coalesce(
                        func.sum(
                            case(
                                (
                                    (l.c.on_hold == 0)
                                    & l.c.due_date.is_not(None)
                                    & (l.c.due_date < as_of),
                                    balance,
                                ),
                                else_=0,
                            )
                        ),
                        0,
                    ).label("past_due_amount"),
                    func.coalesce(
                        func.sum(
                            case(
                                (
                                    (l.c.on_hold == 0)
                                    & l.c.due_date.between(as_of, within_7_days),
                                    balance,
                                ),
                                else_=0,
                            )
                        ),
                        0,
                    ).label("due_within_7_days_amount"),
                ).select_from(l)
            ).mappings().first()
            refreshed_at = connection.execute(
                select(func.max(l.c.refreshed_at))
            ).scalar_one_or_none()
        return {**dict(row), "refreshed_at": refreshed_at}

    def list_vendor_terms_reference(self) -> list[dict[str, Any]]:
        self.initialize()
        t = ap_vendor_terms_reference_table
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(t).order_by(t.c.terms_code)
            ).mappings().all()
        return [dict(row) for row in rows]

    def upsert_vendor_terms_reference(
        self,
        *,
        terms_code: str,
        discount_percent: float,
        num_periods: int | None,
        num_months: int | None,
        num_days: int | None,
        second_period: int | None,
        third_period: int | None,
        next_period: int | None,
        day_of_month: int | None,
        cutoff_day: int | None,
        description: str,
    ) -> None:
        self.initialize()
        t = ap_vendor_terms_reference_table
        values = {
            "discount_percent": discount_percent,
            "num_periods": num_periods,
            "num_months": num_months,
            "num_days": num_days,
            "second_period": second_period,
            "third_period": third_period,
            "next_period": next_period,
            "day_of_month": day_of_month,
            "cutoff_day": cutoff_day,
            "description": description,
            "updated_at": _now(),
        }
        with self._engine.begin() as connection:
            existing = connection.execute(
                select(t.c.terms_code).where(t.c.terms_code == terms_code)
            ).first()
            if existing is None:
                connection.execute(
                    t.insert().values(terms_code=terms_code, **values)
                )
            else:
                connection.execute(
                    t.update().where(t.c.terms_code == terms_code).values(**values)
                )

    def discount_eligibility_summary(self, as_of_date: date) -> dict[str, Any]:
        """Only terms codes with a true flat 'N days from invoice date'
        discount rule (discount_percent > 0 and num_days > 0) are computed
        here. A discount-bearing code that instead relies on day_of_month/
        cutoff_day ("proximo") logic is deliberately excluded and listed
        separately - not silently treated as zero.

        The due-by-date filter (invoice_date + num_days >= as_of) is
        computed in Python rather than SQL date arithmetic (SQLite's
        date(x, '+N days') has no direct MySQL equivalent for an arbitrary
        ISO-8601 text column)."""

        self.initialize()
        l = ap_erp_open_ledger_cache_table
        v = ap_erp_vendor_terms_cache_table
        t = ap_vendor_terms_reference_table
        with self._engine.connect() as connection:
            has_reference = connection.execute(
                select(func.count()).select_from(t)
            ).scalar_one()
            candidates = connection.execute(
                select(l.c.amount_invoiced, t.c.discount_percent, l.c.invoice_date, t.c.num_days)
                .select_from(
                    l.join(v, v.c.vendor_number == l.c.vendor_number).join(
                        t, t.c.terms_code == v.c.terms_code
                    )
                )
                .where(
                    l.c.on_hold == 0,
                    t.c.discount_percent > 0,
                    t.c.num_days > 0,
                    l.c.invoice_date.is_not(None),
                )
            ).all()
            excluded = connection.execute(
                select(t.c.terms_code, t.c.description)
                .where(
                    t.c.discount_percent > 0,
                    or_(t.c.num_days.is_(None), t.c.num_days <= 0),
                )
                .order_by(t.c.terms_code)
            ).mappings().all()

        eligible_count = 0
        eligible_amount = 0.0
        for row in candidates:
            invoice_date = date.fromisoformat(row.invoice_date)
            if invoice_date + timedelta(days=row.num_days) >= as_of_date:
                eligible_count += 1
                eligible_amount += row.amount_invoiced * row.discount_percent / 100.0

        return {
            "has_reference_data": bool(has_reference),
            "eligible_count": eligible_count,
            "eligible_amount": eligible_amount,
            "excluded_codes": [dict(row) for row in excluded],
        }

    def update_open_ledger_gl_fields(
        self,
        gl_fields: dict[tuple[str, str], tuple[str | None, str | None, str | None]],
    ) -> int:
        """Populates gl_division/gl_account/gl_department on already-cached
        open-ledger rows, each a (division, account, department) tuple from
        the same winning GL distribution line. Never inserts new rows - an
        invoice must already be in the open-ledger cache (i.e. currently
        unpaid) for its GL detail to matter here."""

        self.initialize()
        if not gl_fields:
            return 0
        l = ap_erp_open_ledger_cache_table
        updated = 0
        with self._engine.begin() as connection:
            for (vendor_number, invoice_number), (
                division,
                account,
                department,
            ) in gl_fields.items():
                result = connection.execute(
                    l.update()
                    .where(
                        l.c.vendor_number == vendor_number,
                        l.c.invoice_number == invoice_number,
                    )
                    .values(
                        gl_division=division,
                        gl_account=account,
                        gl_department=department,
                    )
                )
                updated += result.rowcount
        return updated

    def _latest_warehouse_status(
        self, connection, vendor_number: str, invoice_number: str
    ) -> str:
        a = ap_warehouse_approval_actions_table
        row = connection.execute(
            select(a.c.to_status)
            .where(a.c.vendor_number == vendor_number, a.c.invoice_number == invoice_number)
            .order_by(a.c.created_at.desc(), a.c.action_id.desc())
            .limit(1)
        ).first()
        return row.to_status if row is not None else "needs_approval"

    def record_warehouse_approval_action(
        self,
        *,
        action_id: str,
        vendor_number: str,
        invoice_number: str,
        to_status: str,
        actor_identity: str,
        actor_identity_source: str,
        notes: str,
        created_at: str,
    ) -> dict[str, Any]:
        self.initialize()
        a = ap_warehouse_approval_actions_table
        with self._engine.begin() as connection:
            from_status = self._latest_warehouse_status(
                connection, vendor_number, invoice_number
            )
            connection.execute(
                a.insert().values(
                    action_id=action_id,
                    vendor_number=vendor_number,
                    invoice_number=invoice_number,
                    from_status=from_status,
                    to_status=to_status,
                    actor_identity=actor_identity,
                    actor_identity_source=actor_identity_source,
                    notes=notes,
                    created_at=created_at,
                )
            )
        return {
            "action_id": action_id,
            "vendor_number": vendor_number,
            "invoice_number": invoice_number,
            "from_status": from_status,
            "to_status": to_status,
            "actor_identity": actor_identity,
            "actor_identity_source": actor_identity_source,
            "notes": notes,
            "created_at": created_at,
        }

    def warehouse_approval_queue(self, division: str | None) -> dict[str, Any]:
        """Every currently-open ERP invoice (from the same open-ledger cache
        the dashboard uses), bucketed by its latest warehouse-approval
        action status (or 'needs_approval' when none exists yet), optionally
        filtered to one GL division. An invoice with no action row is never
        materialized as a row in ap_warehouse_approval_actions - status is
        always derived, matching ap_control_cases' derivation precedent.

        Linkage to a local ap_invoices row (once one exists via OCR capture)
        is a best-effort match on vendor_number + normalized invoice
        number - nullable and disclosed, not a guaranteed join."""

        self.initialize()
        # ap_invoices belongs to AccountsPayableRepository, which may not
        # have run its own lazy create_all yet if this is the first
        # accounts_payable call this process makes - initialize it here
        # (via the same engine this instance uses) so the LEFT JOIN below
        # never fails with "table doesn't exist".
        AccountsPayableRepository(self._engine).initialize()

        l = ap_erp_open_ledger_cache_table
        v = ap_erp_vendor_terms_cache_table
        a = ap_warehouse_approval_actions_table
        i = ap_invoices_table

        action_rank = (
            func.row_number()
            .over(
                partition_by=(a.c.vendor_number, a.c.invoice_number),
                order_by=(a.c.created_at.desc(), a.c.action_id.desc()),
            )
            .label("rn")
        )
        latest = (
            select(
                a.c.vendor_number,
                a.c.invoice_number,
                a.c.to_status,
                a.c.actor_identity,
                a.c.created_at,
                action_rank,
            )
        ).subquery()

        conditions = [latest.c.rn == 1]
        query_conditions = [l.c.gl_division == division] if division else []

        with self._engine.connect() as connection:
            rows = connection.execute(
                select(
                    l.c.vendor_number,
                    v.c.vendor_name,
                    l.c.invoice_number,
                    l.c.invoice_date,
                    l.c.due_date,
                    l.c.amount_invoiced,
                    l.c.amount_discount,
                    l.c.on_hold,
                    l.c.gl_division,
                    l.c.gl_account,
                    l.c.gl_department,
                    func.coalesce(latest.c.to_status, "needs_approval").label("status"),
                    latest.c.actor_identity.label("last_actor_identity"),
                    latest.c.created_at.label("last_action_at"),
                    i.c.ap_invoice_id.label("linked_ap_invoice_id"),
                )
                .select_from(
                    l.outerjoin(v, v.c.vendor_number == l.c.vendor_number)
                    .outerjoin(
                        latest,
                        (latest.c.vendor_number == l.c.vendor_number)
                        & (latest.c.invoice_number == l.c.invoice_number)
                        & (latest.c.rn == 1),
                    )
                    .outerjoin(
                        i,
                        (i.c.vendor_number == l.c.vendor_number)
                        & (i.c.normalized_invoice_number == func.upper(l.c.invoice_number)),
                    )
                )
                .where(*query_conditions)
                .order_by(l.c.due_date.is_(None), l.c.due_date, l.c.vendor_number, l.c.invoice_number)
            ).mappings().all()
            divisions = connection.execute(
                select(l.c.gl_division)
                .distinct()
                .where(l.c.gl_division.is_not(None))
                .order_by(l.c.gl_division)
            ).all()
        return {
            "items": [dict(row) for row in rows],
            "available_divisions": [row.gl_division for row in divisions],
        }


accounts_payable_erp_ledger_repository = AccountsPayableErpLedgerRepository()


def initialize_accounts_payable_erp_ledger_database() -> None:
    """Startup migration hook for the shared SQLite initialization boundary."""

    accounts_payable_erp_ledger_repository.initialize()
