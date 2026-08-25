from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from .ap_spend_parser import parse_ap_spend_question
from .ap_spend_schemas import (
    APSpendAmountSummary,
    APSpendDateBasisReadiness,
    APSpendMappingCheck,
    APSpendMeasureDefinition,
    APSpendMonthlyPeriod,
    APSpendParsedQuestion,
    APSpendQuestionResponse,
    APSpendReadinessResponse,
    APSpendVendorRank,
)
from .repository import ERPEvidenceRepository, erp_evidence_repository
from .schemas import EvidenceCoverageItem, EvidenceGovernance, EvidenceSourceReference


CONTRACT_VERSION = "ap-vendor-spend-intelligence@1.1.1"
EXACT_NUMERIC_TYPES = {
    "bigint",
    "decimal",
    "int",
    "integer",
    "mediumint",
    "numeric",
    "smallint",
    "tinyint",
}
NUMERIC_DATE_TYPES = EXACT_NUMERIC_TYPES | {"double", "float"}
NATIVE_DATE_TYPES = {"date", "datetime", "timestamp"}
CHARACTER_INVOICE_IDENTITY_TYPES = {"char", "varchar"}
NUMERIC_DATE_ENCODING_ENV = "ETOP_AP_PMGDTEINV_NUMERIC_ENCODING"
NUMERIC_DATE_ENCODINGS = {"YYYYMMDD", "MMDDYYYY"}

PMGLDS_CORE_FIELDS = (
    "PMGNBVND",
    "PMGNBINV",
    "PMGAMTINV",
    "PMGNBGLDV",
    "PMGNBGL",
)
PMVEND_IDENTITY_FIELDS = ("PVNUMVEN", "PVNAMVEN")
PMGLDS_EXACT_NUMERIC_FIELDS = (
    "PMGNBVND",
    "PMGAMTINV",
    "PMGNBGLDV",
    "PMGNBGL",
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _canonical_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
    ).hexdigest()


def _int(value: Any) -> int:
    if value in (None, ""):
        return 0
    return int(Decimal(str(value)))


def _money(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    return round(float(Decimal(str(value))), 2)


def _text(value: Any) -> str:
    return str(value or "").strip().removesuffix(".0")


def _currency(value: float) -> str:
    if value < 0:
        return f"-${abs(value):,.2f}"
    return f"${value:,.2f}"


def _column_signature(metadata: dict[str, Any]) -> tuple[str, str]:
    return (
        str(metadata.get("data_type") or "").strip().lower(),
        str(metadata.get("column_type") or "").strip().lower(),
    )


def _decimal_shape(column_type: str) -> tuple[int, int] | None:
    match = re.search(
        r"\b(?:decimal|numeric)\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)",
        column_type,
    )
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _exact_numeric_gap(field: str, metadata: dict[str, Any]) -> str | None:
    data_type, column_type = _column_signature(metadata)
    if data_type not in EXACT_NUMERIC_TYPES:
        return f"PMGLDS.{field} requires an exact numeric type; observed {column_type or data_type or 'unknown'}"
    return None


def _invoice_identity_type_gap(metadata: dict[str, Any]) -> str | None:
    data_type, column_type = _column_signature(metadata)
    if data_type in EXACT_NUMERIC_TYPES | CHARACTER_INVOICE_IDENTITY_TYPES:
        return None
    return (
        "PMGLDS.PMGNBINV requires an exact numeric, CHAR, or VARCHAR "
        f"identity type; observed {column_type or data_type or 'unknown'}"
    )


def _numeric_date_type_gap(metadata: dict[str, Any], encoding: str) -> str | None:
    data_type, column_type = _column_signature(metadata)
    if data_type in {"float", "double"}:
        return (
            f"PMGLDS.PMGDTEINV uses approximate {column_type or data_type}; "
            f"{encoding} requires exact eight-digit storage"
        )
    if data_type in {"tinyint", "smallint", "mediumint"}:
        return (
            f"PMGLDS.PMGDTEINV uses undersized {column_type or data_type}; "
            f"{encoding} requires an exact eight-digit range"
        )
    if data_type in {"decimal", "numeric"}:
        shape = _decimal_shape(column_type)
        if shape is None:
            return (
                "PMGLDS.PMGDTEINV decimal precision/scale could not be verified "
                f"from {column_type or 'runtime metadata'}"
            )
        precision, scale = shape
        if precision < 8 or scale != 0:
            return (
                f"PMGLDS.PMGDTEINV {column_type} cannot be used for exact "
                f"{encoding}; precision must be at least 8 and scale must be 0"
            )
    if data_type not in {"bigint", "int", "integer", "decimal", "numeric"}:
        return (
            f"PMGLDS.PMGDTEINV runtime type {column_type or data_type or 'unknown'} "
            f"is incompatible with exact {encoding} storage"
        )
    return None


class APVendorSpendService:
    def __init__(
        self,
        *,
        repository: ERPEvidenceRepository = erp_evidence_repository,
        clock=_now,
        today_provider=date.today,
    ) -> None:
        self.repository = repository
        self.clock = clock
        self.today_provider = today_provider

    def readiness(self) -> APSpendReadinessResponse:
        mapping, mapping_error = self._inspect_mapping()
        return self._build_readiness(
            generated_at=self.clock(),
            mapping=mapping,
            mapping_error=mapping_error,
        )

    def answer(self, question: str) -> APSpendQuestionResponse:
        parsed = parse_ap_spend_question(
            question,
            today=self.today_provider(),
        )
        mapping, mapping_error = self._inspect_mapping()
        mapping_checked_at = self.clock()
        readiness = self._build_readiness(
            generated_at=mapping_checked_at,
            mapping=mapping,
            mapping_error=mapping_error,
        )
        generated_at = self.clock()

        if parsed.unavailable_slots:
            return self._empty_question_response(
                generated_at=generated_at,
                status="unavailable",
                answer_text=self._unavailable_prompt(parsed),
                parsed=parsed,
                readiness=readiness,
            )
        if parsed.ambiguous_slots or parsed.missing_slots:
            return self._empty_question_response(
                generated_at=generated_at,
                status="needs_clarification",
                answer_text=self._clarification_prompt(parsed),
                parsed=parsed,
                readiness=readiness,
            )
        if mapping_error is not None:
            return self._empty_question_response(
                generated_at=generated_at,
                status="degraded",
                answer_text=(
                    "The deterministic question was parsed, but runtime ERP mapping "
                    "verification is unavailable. No financial row query was executed."
                ),
                parsed=parsed,
                readiness=readiness,
                warnings=[mapping_error],
            )

        question_gap = self._question_mapping_gap(parsed, mapping)
        if question_gap:
            return self._empty_question_response(
                generated_at=generated_at,
                status="unavailable",
                answer_text=(
                    "The question is supported, but its required source mapping is not "
                    "available in the runtime schema. No financial row query was executed."
                ),
                parsed=parsed,
                readiness=readiness,
                warnings=question_gap,
            )

        range_start, range_end = self._query_date_bounds(parsed, mapping)
        query_arguments = {
            "division": int(parsed.division or "0"),
            "account": int(parsed.account) if parsed.account else None,
            "time_basis": str(parsed.time_basis),
            "year": int(parsed.year or 0),
            "accounting_period": parsed.accounting_period,
            "range_start": range_start,
            "range_end_exclusive": range_end,
            "calendar_date_encoding": self._calendar_date_encoding(mapping),
        }

        try:
            vendor_fields = mapping.get("PMVEND", {})
            packet = self.repository.get_ap_spend_evidence(
                **query_arguments,
                include_ranking=parsed.intent == "top_vendor",
                include_monthly=parsed.intent == "top_vendor_by_month",
                include_vendor_names=(
                    parsed.intent in {"top_vendor", "top_vendor_by_month"}
                    and all(field in vendor_fields for field in PMVEND_IDENTITY_FIELDS)
                ),
            )
            total_row = packet["total"]
            ranking_rows = packet["ranking"]
            ranking_complete = packet["ranking_complete"]
            monthly_rows = packet["monthly_rankings"]
            vendor_names = packet["vendor_names"]
            vendor_identity_queried = bool(packet["vendor_identity_queried"])
            evidence_as_of = str(packet["snapshot_opened_at"])
            generated_at = self.clock()
        except Exception as exc:
            generated_at = self.clock()
            return self._empty_question_response(
                generated_at=generated_at,
                status="degraded",
                answer_text=(
                    "The governed read-only ERP aggregate could not be completed. No "
                    "result is shown as zero."
                ),
                parsed=parsed,
                readiness=readiness,
                warnings=[f"ERP vendor-spend evidence is unavailable: {exc}"],
                evidence_consistency="consistent_snapshot_query_failed",
            )

        total = self._total(total_row)
        monthly_periods = (
            self._monthly_periods(monthly_rows, vendor_names)
            if parsed.intent == "top_vendor_by_month"
            else []
        )
        leader_set_complete: bool | None = (
            ranking_complete if parsed.intent == "top_vendor" else None
        )
        if total.distribution_row_count == 0:
            return self._question_response(
                generated_at=generated_at,
                status="no_evidence",
                answer_text=(
                    "No PMGLDS distribution rows matched the parsed division, account, "
                    "and date basis. ETOP did not convert the empty result into spend."
                ),
                parsed=parsed,
                readiness=readiness,
                total=total,
                ranking=[],
                leaders=[],
                monthly_periods=monthly_periods,
                ranking_complete=ranking_complete,
                leader_set_complete=leader_set_complete,
                vendor_identity_queried=False,
                warnings=[],
                evidence_as_of=evidence_as_of,
            )
        if total.amount_available_row_count == 0:
            return self._question_response(
                generated_at=generated_at,
                status="no_evidence",
                answer_text=(
                    f"{total.distribution_row_count} PMGLDS distribution row(s) matched "
                    "the parsed filters, but none had a PMGAMTINV amount. ETOP did not "
                    "assert a zero spend total or a highest-spend vendor."
                ),
                parsed=parsed,
                readiness=readiness,
                total=total,
                ranking=[],
                leaders=[],
                monthly_periods=monthly_periods,
                ranking_complete=None,
                leader_set_complete=None,
                vendor_identity_queried=False,
                warnings=[
                    "All matching PMGLDS rows lacked PMGAMTINV; the zero-valued SQL aggregate is an empty-sum placeholder, not spend evidence."
                ],
                evidence_as_of=evidence_as_of,
            )

        warnings: list[str] = []
        if total.missing_amount_row_count:
            warnings.append(
                f"{total.missing_amount_row_count} matching PMGLDS row(s) had no PMGAMTINV value and are excluded from amount sums."
            )
        if total.negative_distribution_amount < 0:
            warnings.append(
                "Negative PMGAMTINV rows are disclosed separately and reduce the net signed amount; ETOP does not infer their business reason."
            )

        ranking: list[APSpendVendorRank] = []
        leaders: list[APSpendVendorRank] = []
        if parsed.intent == "top_vendor":
            vendor_fields = mapping.get("PMVEND", {})
            if not all(field in vendor_fields for field in PMVEND_IDENTITY_FIELDS):
                warnings.append(
                    "PMVEND vendor-name mapping is incomplete; rankings show vendor numbers only."
                )
            ranking = self._ranking(ranking_rows, vendor_names)
            if ranking:
                highest = ranking[0].net_signed_amount
                leaders = [
                    row for row in ranking if row.net_signed_amount == highest
                ]
            if ranking_complete is True:
                leader_set_complete = True
            elif ranking_complete is False:
                # Once a lower amount is visible inside the cap, deterministic
                # descending order proves that omitted rows cannot join rank 1.
                # If every displayed row is a leader, the next row can still tie.
                leader_set_complete = bool(ranking) and len(leaders) < len(ranking)
            if ranking_complete is False:
                warnings.append(
                    f"The displayed ranking is limited to the first {self.repository.AP_SPEND_VENDOR_LIMIT} vendors after deterministic ordering."
                )
            if leader_set_complete is False:
                warnings.append(
                    "Every displayed vendor shares the highest net signed amount, so additional undisplayed vendors may share rank 1. The displayed leader count is a lower bound, not an exact tie count."
                )
        elif parsed.intent == "top_vendor_by_month":
            vendor_fields = mapping.get("PMVEND", {})
            if not all(field in vendor_fields for field in PMVEND_IDENTITY_FIELDS):
                warnings.append(
                    "PMVEND vendor-name mapping is incomplete; monthly leaders show vendor numbers only."
                )
            incomplete_months = [
                period.calendar_month
                for period in monthly_periods
                if period.status == "available" and not period.leader_set_complete
            ]
            if incomplete_months:
                warnings.append(
                    "The bounded leader set may omit additional tied rank-1 vendors "
                    "for calendar month(s) "
                    + ", ".join(str(month) for month in incomplete_months)
                    + ". Displayed leader counts for those months are lower bounds."
                )

        answer_text = self._answer_text(
            parsed,
            total,
            leaders,
            monthly_periods=monthly_periods,
            leader_set_complete=leader_set_complete,
        )
        return self._question_response(
            generated_at=generated_at,
            status="answered",
            answer_text=answer_text,
            parsed=parsed,
            readiness=readiness,
            total=total,
            ranking=ranking,
            leaders=leaders,
            monthly_periods=monthly_periods,
            ranking_complete=ranking_complete,
            leader_set_complete=leader_set_complete,
            vendor_identity_queried=vendor_identity_queried,
            warnings=warnings,
            evidence_as_of=evidence_as_of,
        )

    def _inspect_mapping(
        self,
    ) -> tuple[dict[str, dict[str, dict[str, Any]]], str | None]:
        try:
            return self.repository.inspect_ap_spend_mapping(), None
        except Exception as exc:
            return {"PMGLDS": {}, "PMVEND": {}}, str(exc)

    def _build_readiness(
        self,
        *,
        generated_at: str,
        mapping: dict[str, dict[str, dict[str, Any]]],
        mapping_error: str | None,
    ) -> APSpendReadinessResponse:
        pmglds = mapping.get("PMGLDS", {})
        pmvend = mapping.get("PMVEND", {})
        checks: list[APSpendMappingCheck] = []

        core_missing = [field for field in PMGLDS_CORE_FIELDS if field not in pmglds]
        core_incompatible = [
            gap
            for field in PMGLDS_EXACT_NUMERIC_FIELDS
            if field in pmglds
            for gap in [_exact_numeric_gap(field, pmglds[field])]
            if gap is not None
        ]
        if "PMGNBINV" in pmglds:
            invoice_identity_gap = _invoice_identity_type_gap(
                pmglds["PMGNBINV"]
            )
            if invoice_identity_gap:
                core_incompatible.append(invoice_identity_gap)
        checks.append(
            APSpendMappingCheck(
                key="signed_distribution_source",
                label="Signed posted AP GL distributions",
                status=(
                    "degraded"
                    if mapping_error
                    else "available"
                    if not core_missing and not core_incompatible
                    else "unavailable"
                ),
                source="MaddenCo PMGLDS",
                required_fields=list(PMGLDS_CORE_FIELDS),
                missing_fields=core_missing,
                incompatible_fields=core_incompatible,
                explanation=(
                    "PMGLDS supplies vendor/invoice identity, signed distribution amount, division, and GL account."
                    if not core_missing and not core_incompatible and not mapping_error
                    else "One or more fixed PMGLDS fields required for the aggregate were missing or type-incompatible; financial rows remain unread."
                ),
            )
        )

        vendor_missing = [
            field for field in PMVEND_IDENTITY_FIELDS if field not in pmvend
        ]
        checks.append(
            APSpendMappingCheck(
                key="vendor_identity",
                label="Vendor identity",
                status=(
                    "degraded"
                    if mapping_error
                    else "available"
                    if not vendor_missing
                    else "partial"
                ),
                source="MaddenCo PMVEND",
                required_fields=list(PMVEND_IDENTITY_FIELDS),
                missing_fields=vendor_missing,
                incompatible_fields=[],
                explanation=(
                    "Vendor names are read only after bounded PMGLDS ranking returns vendor numbers."
                    if not vendor_missing and not mapping_error
                    else "Vendor-number ranking may remain available, but vendor names cannot be asserted from an incomplete mapping."
                ),
            )
        )

        calendar_data_type = str(
            pmglds.get("PMGDTEINV", {}).get("data_type") or ""
        ).lower()
        calendar_encoding = self._calendar_date_encoding(mapping)
        calendar_type_supported = calendar_encoding is not None
        accounting_year_supported = (
            "PMGYR" in pmglds
            and _exact_numeric_gap("PMGYR", pmglds["PMGYR"]) is None
        )
        accounting_period_supported = (
            accounting_year_supported
            and "PMGPR" in pmglds
            and _exact_numeric_gap("PMGPR", pmglds["PMGPR"]) is None
        )
        date_bases = [
            APSpendDateBasisReadiness(
                key="calendar_invoice_date",
                label="Calendar invoice date",
                status=(
                    "degraded"
                    if mapping_error
                    else "available"
                    if "PMGDTEINV" in pmglds and calendar_type_supported
                    else "unavailable"
                ),
                source_fields=["PMGLDS.PMGDTEINV"],
                explanation=(
                    f"Calendar ranges use PMGDTEINV with runtime data type {calendar_data_type} and governed encoding {calendar_encoding}."
                    if calendar_type_supported
                    else f"PMGDTEINV is missing, has an unsupported type, or is numeric without an approved {NUMERIC_DATE_ENCODING_ENV}=YYYYMMDD|MMDDYYYY configuration."
                ),
            ),
            APSpendDateBasisReadiness(
                key="erp_accounting_year",
                label="ERP accounting year",
                status=(
                    "degraded"
                    if mapping_error
                    else "available"
                    if accounting_year_supported
                    else "unavailable"
                ),
                source_fields=["PMGLDS.PMGYR"],
                explanation="Uses the raw ERP accounting-year value and does not relabel it as calendar or fiscal year.",
            ),
            APSpendDateBasisReadiness(
                key="erp_accounting_period",
                label="ERP accounting year and period",
                status=(
                    "degraded"
                    if mapping_error
                    else "available"
                    if accounting_period_supported
                    else "unavailable"
                ),
                source_fields=["PMGLDS.PMGYR", "PMGLDS.PMGPR"],
                explanation="Uses raw PMGYR/PMGPR values only when the question explicitly asks for an ERP accounting year or period.",
            ),
            APSpendDateBasisReadiness(
                key="fiscal_calendar",
                label="Approved fiscal calendar",
                status="unavailable",
                source_fields=[],
                explanation="No approved fiscal-year start, adjustment-period, or period-to-calendar mapping is connected.",
            ),
        ]

        dictionary_status, dictionary_path, dictionary_warning = (
            self._local_dictionary_readiness()
        )
        warnings: list[str] = []
        if mapping_error:
            warnings.append(
                f"Runtime INFORMATION_SCHEMA validation is unavailable: {mapping_error}"
            )
        if dictionary_warning:
            warnings.append(dictionary_warning)

        if mapping_error:
            status = "degraded"
        elif core_missing or core_incompatible:
            status = "unavailable"
        elif any(item.status == "unavailable" for item in date_bases[:3]):
            status = "partial"
        else:
            status = "available"

        product_owner_mappings_needed = [
            "Approved fiscal calendar, adjustment-period handling, and fiscal-year label if fiscal questions are required.",
            "Authoritative reversal/void treatment if management spend should differ from PMGAMTINV signed-as-stored netting.",
            "Currency/consolidation rule if PMGLDS contains more than one monetary basis.",
        ]
        configured_date_encoding = os.getenv(
            NUMERIC_DATE_ENCODING_ENV, ""
        ).strip().upper()
        if (
            calendar_data_type in NUMERIC_DATE_TYPES
            and configured_date_encoding not in NUMERIC_DATE_ENCODINGS
        ):
            product_owner_mappings_needed.insert(
                0,
                f"Confirm whether numeric PMGLDS.PMGDTEINV is YYYYMMDD or MMDDYYYY and set {NUMERIC_DATE_ENCODING_ENV} to that exact approved value.",
            )
        elif (
            calendar_data_type in NUMERIC_DATE_TYPES
            and configured_date_encoding in NUMERIC_DATE_ENCODINGS
        ):
            date_gap = _numeric_date_type_gap(
                pmglds.get("PMGDTEINV", {}),
                configured_date_encoding,
            )
            if date_gap:
                warnings.append(date_gap)

        return APSpendReadinessResponse(
            contract_version=CONTRACT_VERSION,
            generated_at=generated_at,
            status=status,
            source_schema=os.getenv("MYSQL_DATABASE", "configured_schema"),
            mapping_checks=checks,
            date_bases=date_bases,
            measure=APSpendMeasureDefinition(
                interpretation=(
                    "Sum PMGLDS.PMGAMTINV exactly as stored for the bounded filters. "
                    "Positive, negative, and net signed amounts are reported separately."
                ),
                excluded_meanings=[
                    "cash paid or payment execution",
                    "current open Accounts Payable",
                    "approved invoice state",
                    "purchase-order or receipt match",
                    "vendor performance score",
                    "fiscal-calendar interpretation without an approved mapping",
                ],
            ),
            local_data_dictionary_status=dictionary_status,
            local_data_dictionary_path=dictionary_path,
            product_owner_mappings_needed=product_owner_mappings_needed,
            governance=self._governance(),
            warnings=warnings,
        )

    @staticmethod
    def _local_dictionary_readiness() -> tuple[str, str | None, str | None]:
        backend_root = Path(__file__).resolve().parents[2]
        candidates = [
            backend_root / "sql_knowledge" / "generated" / "data_dictionary.json",
            backend_root / "sql_knowledge" / "data_dictionary.json",
        ]
        path = next((candidate for candidate in candidates if candidate.is_file()), None)
        if path is None:
            return (
                "unavailable",
                None,
                "The generated local data_dictionary.json is not present in this accepted source tree; SRC-005 and runtime INFORMATION_SCHEMA remain the declared mapping evidence.",
            )
        display_path = f"backend/{path.relative_to(backend_root).as_posix()}"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            tables = payload.get("tables", []) if isinstance(payload, dict) else []
            pmglds = next(
                (
                    table
                    for table in tables
                    if isinstance(table, dict)
                    and str(table.get("name") or "").upper() == "PMGLDS"
                ),
                None,
            )
            if pmglds is None:
                return (
                    "partial",
                    display_path,
                    "The local data dictionary exists but does not contain a PMGLDS record; it does not authorize a fallback mapping.",
                )
            columns = {
                str(column.get("name") or "").upper()
                for column in pmglds.get("columns", [])
                if isinstance(column, dict)
            }
            missing = [field for field in PMGLDS_CORE_FIELDS if field not in columns]
            return (
                "available" if not missing else "partial",
                display_path,
                None
                if not missing
                else "The local data dictionary is missing one or more fixed AP spend fields and is diagnostic only.",
            )
        except (OSError, ValueError, TypeError) as exc:
            return (
                "degraded",
                display_path,
                f"The local data dictionary could not be validated and is not used for a financial query: {exc}",
            )

    @staticmethod
    def _calendar_date_encoding(
        mapping: dict[str, dict[str, dict[str, Any]]],
    ) -> str | None:
        data_type = str(
            mapping.get("PMGLDS", {})
            .get("PMGDTEINV", {})
            .get("data_type")
            or ""
        ).lower()
        if data_type in NATIVE_DATE_TYPES:
            return "NATIVE_DATE"
        if data_type in NUMERIC_DATE_TYPES:
            configured = os.getenv(NUMERIC_DATE_ENCODING_ENV, "").strip().upper()
            metadata = mapping.get("PMGLDS", {}).get("PMGDTEINV", {})
            if (
                configured in NUMERIC_DATE_ENCODINGS
                and _numeric_date_type_gap(metadata, configured) is None
            ):
                return configured
        return None

    @staticmethod
    def _question_mapping_gap(
        parsed: APSpendParsedQuestion,
        mapping: dict[str, dict[str, dict[str, Any]]],
    ) -> list[str]:
        pmglds = mapping.get("PMGLDS", {})
        required = list(PMGLDS_CORE_FIELDS)
        if parsed.time_basis == "calendar_invoice_date":
            required.append("PMGDTEINV")
        elif parsed.time_basis == "erp_accounting_year":
            required.append("PMGYR")
        elif parsed.time_basis == "erp_accounting_period":
            required.extend(["PMGYR", "PMGPR"])
        missing = [f"PMGLDS.{field}" for field in required if field not in pmglds]
        for field in required:
            if field in pmglds and field != "PMGDTEINV":
                gap = (
                    _invoice_identity_type_gap(pmglds[field])
                    if field == "PMGNBINV"
                    else _exact_numeric_gap(field, pmglds[field])
                )
                if gap:
                    missing.append(gap)
        if parsed.time_basis == "calendar_invoice_date" and "PMGDTEINV" in pmglds:
            data_type = str(pmglds["PMGDTEINV"].get("data_type") or "").lower()
            if data_type not in NUMERIC_DATE_TYPES | NATIVE_DATE_TYPES:
                missing.append(
                    f"Supported PMGLDS.PMGDTEINV runtime type (observed {data_type or 'unknown'})"
                )
            elif data_type in NUMERIC_DATE_TYPES:
                configured = os.getenv(NUMERIC_DATE_ENCODING_ENV, "").strip().upper()
                if configured not in NUMERIC_DATE_ENCODINGS:
                    missing.append(
                        f"Approved numeric PMGLDS.PMGDTEINV encoding via {NUMERIC_DATE_ENCODING_ENV}=YYYYMMDD|MMDDYYYY"
                    )
                else:
                    gap = _numeric_date_type_gap(pmglds["PMGDTEINV"], configured)
                    if gap:
                        missing.append(gap)
        return missing

    @staticmethod
    def _query_date_bounds(
        parsed: APSpendParsedQuestion,
        mapping: dict[str, dict[str, dict[str, Any]]],
    ) -> tuple[str | int | None, str | int | None]:
        if parsed.time_basis != "calendar_invoice_date":
            return None, None
        encoding = APVendorSpendService._calendar_date_encoding(mapping)
        if encoding == "YYYYMMDD":
            return (
                int(str(parsed.range_start).replace("-", "")),
                int(str(parsed.range_end_exclusive).replace("-", "")),
            )
        if encoding in {"MMDDYYYY", "NATIVE_DATE"}:
            return parsed.range_start, parsed.range_end_exclusive
        raise ValueError("Unsupported or unconfigured PMGDTEINV runtime date encoding.")

    @staticmethod
    def _total(row: dict[str, Any]) -> APSpendAmountSummary:
        return APSpendAmountSummary(
            distribution_row_count=_int(row.get("distribution_row_count")),
            amount_available_row_count=_int(row.get("amount_available_row_count")),
            missing_amount_row_count=_int(row.get("missing_amount_row_count")),
            invoice_identity_count=_int(row.get("invoice_identity_count")),
            vendor_count=_int(row.get("vendor_count")),
            positive_distribution_amount=_money(
                row.get("positive_distribution_amount")
            ),
            negative_distribution_amount=_money(
                row.get("negative_distribution_amount")
            ),
            net_signed_amount=_money(row.get("net_signed_amount")),
        )

    @staticmethod
    def _ranking(
        rows: list[dict[str, Any]],
        vendor_names: dict[str, str | None],
    ) -> list[APSpendVendorRank]:
        result: list[APSpendVendorRank] = []
        prior_amount: float | None = None
        rank = 0
        for index, row in enumerate(rows, start=1):
            net = _money(row.get("net_signed_amount"))
            if prior_amount is None or net != prior_amount:
                rank = index
            vendor_number = _text(row.get("vendor_number")) or "unavailable"
            result.append(
                APSpendVendorRank(
                    rank=rank,
                    vendor_number=vendor_number,
                    vendor_name=vendor_names.get(vendor_number),
                    distribution_row_count=_int(row.get("distribution_row_count")),
                    amount_available_row_count=_int(
                        row.get("amount_available_row_count")
                    ),
                    missing_amount_row_count=_int(
                        row.get("missing_amount_row_count")
                    ),
                    invoice_identity_count=_int(row.get("invoice_identity_count")),
                    positive_distribution_amount=_money(
                        row.get("positive_distribution_amount")
                    ),
                    negative_distribution_amount=_money(
                        row.get("negative_distribution_amount")
                    ),
                    net_signed_amount=net,
                )
            )
            prior_amount = net
        return result

    def _monthly_periods(
        self,
        periods: list[dict[str, Any]],
        vendor_names: dict[str, str | None],
    ) -> list[APSpendMonthlyPeriod]:
        result: list[APSpendMonthlyPeriod] = []
        for period in sorted(
            periods,
            key=lambda item: (
                int(item.get("calendar_year") or 0),
                int(item.get("calendar_month") or 0),
            ),
        )[: self.repository.AP_SPEND_MONTHLY_PERIOD_LIMIT]:
            ranking = self._ranking(period.get("ranking") or [], vendor_names)
            ranking_complete = bool(period.get("ranking_complete"))
            leaders: list[APSpendVendorRank] = []
            if ranking:
                highest = ranking[0].net_signed_amount
                leaders = [
                    vendor
                    for vendor in ranking
                    if vendor.net_signed_amount == highest
                ]
            leader_set_complete = (
                ranking_complete
                or bool(ranking) and len(leaders) < len(ranking)
            )
            month = int(period.get("calendar_month") or 0)
            result.append(
                APSpendMonthlyPeriod(
                    calendar_year=int(period.get("calendar_year") or 0),
                    calendar_month=month,
                    range_start=str(period.get("range_start") or ""),
                    range_end_exclusive=str(
                        period.get("range_end_exclusive") or ""
                    ),
                    status="available" if leaders else "no_evidence",
                    leaders=leaders,
                    ranking_complete=ranking_complete,
                    leader_set_complete=leader_set_complete,
                    explanation=(
                        "Ranked the bounded month by net signed PMGAMTINV and retained every displayed rank-1 vendor."
                        + (
                            " Additional undisplayed vendors may share rank 1."
                            if leaders and not leader_set_complete
                            else ""
                        )
                        if leaders
                        else "No vendor group with a non-null PMGAMTINV amount was available for this calendar month; ETOP did not create a zero leader."
                    ),
                )
            )
        return result

    @staticmethod
    def _time_label(parsed: APSpendParsedQuestion) -> str:
        if parsed.time_basis == "calendar_invoice_date":
            if parsed.month:
                return f"calendar month {parsed.year}-{parsed.month:02d} by PMGDTEINV"
            return f"calendar year {parsed.year} by PMGDTEINV"
        if parsed.time_basis == "erp_accounting_period":
            return f"ERP accounting year {parsed.year}, period {parsed.accounting_period} by PMGYR/PMGPR"
        return f"ERP accounting year {parsed.year} by PMGYR"

    def _answer_text(
        self,
        parsed: APSpendParsedQuestion,
        total: APSpendAmountSummary,
        leaders: list[APSpendVendorRank],
        *,
        monthly_periods: list[APSpendMonthlyPeriod],
        leader_set_complete: bool | None,
    ) -> str:
        filter_label = f"division {parsed.division}"
        if parsed.account:
            filter_label += f", account {parsed.account}"
        time_label = self._time_label(parsed)
        if parsed.intent == "total_spend":
            return (
                f"For {filter_label} in {time_label}, the net signed posted AP "
                f"GL-distribution amount is {_currency(total.net_signed_amount)}. "
                f"Positive distributions total {_currency(total.positive_distribution_amount)}; "
                f"negative distributions total {_currency(total.negative_distribution_amount)}."
            )
        if parsed.intent == "top_vendor_by_month":
            available_periods = [
                period for period in monthly_periods if period.status == "available"
            ]
            incomplete_periods = [
                period
                for period in available_periods
                if not period.leader_set_complete
            ]
            return (
                f"For {filter_label} in calendar year {parsed.year} by PMGDTEINV, "
                f"ETOP evaluated {len(monthly_periods)} ordered calendar months and "
                f"found highest-vendor evidence for {len(available_periods)} month(s). "
                "The monthly table reports each leader's positive, negative, and net "
                "signed posted AP GL-distribution amount."
                + (
                    f" {len(incomplete_periods)} month(s) may have additional tied "
                    "rank-1 vendors beyond the per-month cap."
                    if incomplete_periods
                    else ""
                )
            )
        if not leaders:
            return (
                f"PMGLDS rows matched {filter_label} in {time_label}, but no vendor "
                "ranking row was available."
            )
        if len(leaders) > 1:
            names = ", ".join(
                f"{item.vendor_name or 'Vendor ' + item.vendor_number} (#{item.vendor_number})"
                for item in leaders
            )
            if leader_set_complete is False:
                return (
                    f"For {filter_label} in {time_label}, at least {len(leaders)} "
                    "displayed vendors share the highest net signed posted AP "
                    f"GL-distribution amount at {_currency(leaders[0].net_signed_amount)}: "
                    f"{names}. The row cap may hide additional vendors at the same "
                    "amount, so ETOP does not assert an exact tie count."
                )
            return (
                f"For {filter_label} in {time_label}, {len(leaders)} vendors tie for "
                f"the highest net signed posted AP GL-distribution amount at "
                f"{_currency(leaders[0].net_signed_amount)}: {names}."
            )
        leader = leaders[0]
        answer = (
            f"For {filter_label} in {time_label}, "
            f"{leader.vendor_name or 'vendor ' + leader.vendor_number} "
            f"(#{leader.vendor_number}) has the highest net signed posted AP "
            f"GL-distribution amount at {_currency(leader.net_signed_amount)}. "
            f"Its positive distributions total {_currency(leader.positive_distribution_amount)}; "
            f"negative distributions total {_currency(leader.negative_distribution_amount)}."
        )
        if leader_set_complete is False:
            return (
                answer
                + " The row cap may hide another vendor at the same amount, so this leader is not asserted as unique."
            )
        return answer

    @staticmethod
    def _clarification_prompt(parsed: APSpendParsedQuestion) -> str:
        issues: list[str] = []
        if parsed.missing_slots:
            issues.append("missing " + ", ".join(parsed.missing_slots))
        if parsed.ambiguous_slots:
            issues.append("ambiguous " + ", ".join(parsed.ambiguous_slots))
        return (
            "I can answer only the governed total-spend or highest-vendor forms. "
            + "; ".join(issues)
            + ". State one division and one calendar month/year or explicit ERP accounting year/period."
        )

    @staticmethod
    def _unavailable_prompt(parsed: APSpendParsedQuestion) -> str:
        if "fiscal_calendar" in parsed.unavailable_slots:
            return (
                "Fiscal-year interpretation is unavailable because no approved fiscal "
                "calendar is connected. Ask for a calendar year by invoice date or an "
                "explicit ERP accounting year/period."
            )
        if "unsupported_financial_measure" in parsed.unavailable_slots:
            return (
                "Cash-paid and current-open-payable measures are not connected. This "
                "workspace answers only signed posted AP GL-distribution questions."
            )
        return (
            "Arbitrary SQL and unsupported question forms are not executed. Use a "
            "supported deterministic vendor-spend question."
        )

    @staticmethod
    def _governance() -> EvidenceGovernance:
        return EvidenceGovernance(
            source_authority=(
                "MaddenCo PMGLDS remains authoritative for posted AP GL-distribution "
                "rows and PMVEND for vendor identity. ETOP provides a read-only bounded aggregate."
            ),
            statements=[
                "The question parser maps only fixed supported intents and slots; it never generates or executes model-authored SQL.",
                "PMGAMTINV is summed signed as stored, with positive, negative, and net amounts disclosed separately.",
                "Calendar results use PMGDTEINV; ERP accounting results use PMGYR/PMGPR only when explicitly requested.",
                "The total, bounded ranking, optional twelve fixed monthly rankings, and minimized vendor identities in an answered packet are read in one read-only consistent database snapshot; snapshot setup fails closed.",
                "Results are not cash paid, open AP, approval, payment, posting, vendor performance, or a financial Decision.",
                "No export, notification, external transfer, or ERP mutation follows this query.",
            ],
        )

    @staticmethod
    def _suggested_questions() -> list[str]:
        return [
            "What was total vendor spend in division 3 for calendar year 2026?",
            "Which vendor had the highest spend for account 5050-3 this month?",
            "Which vendor had the highest spend each month for account 5050-3 in calendar year 2026?",
            "Which vendor had the highest spend for account 5050-3 in ERP accounting year 2026 period 8?",
        ]

    def _question_response(
        self,
        *,
        generated_at: str,
        status: str,
        answer_text: str,
        parsed: APSpendParsedQuestion,
        readiness: APSpendReadinessResponse,
        total: APSpendAmountSummary | None,
        ranking: list[APSpendVendorRank],
        leaders: list[APSpendVendorRank],
        monthly_periods: list[APSpendMonthlyPeriod],
        ranking_complete: bool | None,
        leader_set_complete: bool | None,
        vendor_identity_queried: bool,
        warnings: list[str],
        evidence_as_of: str,
    ) -> APSpendQuestionResponse:
        source_schema = readiness.source_schema
        sources = [
            EvidenceSourceReference(
                source_system="MaddenCo ERP",
                source_schema=source_schema,
                source_object="PMGLDS",
                retrieved_at=generated_at,
                contract_version=CONTRACT_VERSION,
            )
        ]
        if parsed.intent in {"top_vendor", "top_vendor_by_month"} and vendor_identity_queried:
            sources.append(
                EvidenceSourceReference(
                    source_system="MaddenCo ERP",
                    source_schema=source_schema,
                    source_object="PMVEND",
                    retrieved_at=generated_at,
                    contract_version=CONTRACT_VERSION,
                )
            )
        if total is None:
            amount_status = "degraded"
            amount_complete = False
            amount_explanation = "No aggregate summary is available."
        elif total.distribution_row_count == 0:
            amount_status = "unavailable"
            amount_complete = True
            amount_explanation = (
                "The bounded aggregate completed and found no matching PMGLDS rows; "
                "the empty result is not reported as spend."
            )
        elif total.amount_available_row_count == 0:
            amount_status = "unavailable"
            amount_complete = False
            amount_explanation = (
                "Matching PMGLDS rows exist, but every PMGAMTINV is missing; no zero "
                "spend or vendor leader is asserted."
            )
        elif total.missing_amount_row_count:
            amount_status = "partial"
            amount_complete = False
            amount_explanation = (
                "The aggregate covers the exact parsed filters, but one or more "
                "matching rows lack PMGAMTINV and are excluded from amount sums."
            )
        else:
            amount_status = "available"
            amount_complete = True
            amount_explanation = (
                "The aggregate covers every PMGLDS row matching the exact parsed "
                "filters and every matching row has PMGAMTINV."
            )

        coverage = [
            EvidenceCoverageItem(
                key="signed_posted_ap_gl_distribution",
                label="Signed posted AP GL-distribution amount",
                status=amount_status,
                source="MaddenCo PMGLDS.PMGAMTINV",
                as_of=evidence_as_of,
                record_count=total.distribution_row_count if total else 0,
                complete=amount_complete,
                explanation=(
                    amount_explanation
                    + " Related PMGLDS aggregates were read in one read-only consistent snapshot."
                ),
            )
        ]
        if parsed.intent == "top_vendor":
            ranking_source = "MaddenCo PMGLDS"
            if vendor_identity_queried:
                ranking_source += " plus minimized PMVEND identity"
            leader_explanation = (
                "The displayed leader set is complete because the ranking is complete or a lower net amount is visible before the row cap."
                if leader_set_complete is True
                else "Every displayed row is rank 1 and the cap was reached; additional undisplayed vendors may share the highest amount."
                if leader_set_complete is False
                else "No leader-set completeness determination applies."
            )
            ranking_has_amount_evidence = bool(
                total and total.amount_available_row_count > 0
            )
            coverage.append(
                EvidenceCoverageItem(
                    key="vendor_ranking",
                    label="Bounded vendor ranking",
                    status=(
                        "unavailable"
                        if not ranking_has_amount_evidence
                        else "available"
                        if ranking_complete is not False
                        else "partial"
                    ),
                    source=ranking_source,
                    as_of=evidence_as_of,
                    record_count=len(ranking),
                    complete=(
                        ranking_complete if ranking_has_amount_evidence else False
                    ),
                    explanation=(
                        "No vendor ranking is asserted because matching amount evidence is unavailable."
                        if not ranking_has_amount_evidence
                        else f"Ordered by net signed PMGAMTINV descending and returned at most {self.repository.AP_SPEND_VENDOR_LIMIT} vendors. Equal displayed net amounts retain the same rank. {leader_explanation}"
                    ),
                )
            )
        elif parsed.intent == "top_vendor_by_month":
            available_months = [
                period for period in monthly_periods if period.status == "available"
            ]
            monthly_has_amount_evidence = bool(
                total and total.amount_available_row_count > 0
            )
            monthly_complete = monthly_has_amount_evidence and (
                len(monthly_periods) == self.repository.AP_SPEND_MONTHLY_PERIOD_LIMIT
                and all(period.leader_set_complete for period in available_months)
            )
            coverage.append(
                EvidenceCoverageItem(
                    key="monthly_vendor_leaders",
                    label="Bounded monthly highest-vendor evidence",
                    status=(
                        "unavailable"
                        if not monthly_has_amount_evidence
                        else "available"
                        if monthly_complete
                        else "partial"
                    ),
                    source=(
                        "MaddenCo PMGLDS plus minimized PMVEND identity"
                        if vendor_identity_queried
                        else "MaddenCo PMGLDS"
                    ),
                    as_of=evidence_as_of,
                    record_count=sum(
                        len(period.leaders) for period in monthly_periods
                    ),
                    complete=monthly_complete,
                    explanation=(
                        "No monthly leader is asserted because matching amount evidence is unavailable."
                        if not monthly_has_amount_evidence
                        else f"Evaluated {len(monthly_periods)} ordered calendar months inside one read-only consistent snapshot. Each month uses a fixed parameterized PMGLDS ranking capped at {self.repository.AP_SPEND_MONTHLY_LEADER_LIMIT} displayed vendors; empty months remain no evidence."
                    ),
                )
            )
        payload = {
            "contract_version": CONTRACT_VERSION,
            "generated_at": generated_at,
            "evidence_as_of": evidence_as_of,
            "status": status,
            "answer_text": answer_text,
            "parsed": parsed.model_dump(),
            "readiness": readiness.model_dump(),
            "total": total.model_dump() if total else None,
            "ranking": [item.model_dump() for item in ranking],
            "leaders": [item.model_dump() for item in leaders],
            "monthly_periods": [
                item.model_dump() for item in monthly_periods
            ],
            "ranking_row_limit": self.repository.AP_SPEND_VENDOR_LIMIT,
            "monthly_period_limit": self.repository.AP_SPEND_MONTHLY_PERIOD_LIMIT,
            "monthly_leader_limit": self.repository.AP_SPEND_MONTHLY_LEADER_LIMIT,
            "ranking_complete": ranking_complete,
            "leader_set_complete": leader_set_complete,
            "evidence_consistency": "single_read_only_consistent_snapshot",
            "coverage": [item.model_dump() for item in coverage],
            "source_references": [item.model_dump() for item in sources],
            "governance": self._governance().model_dump(),
            "warnings": warnings,
            "suggested_questions": self._suggested_questions(),
        }
        return APSpendQuestionResponse(
            **payload,
            evidence_sha256=_canonical_hash(payload),
        )

    def _empty_question_response(
        self,
        *,
        generated_at: str,
        status: str,
        answer_text: str,
        parsed: APSpendParsedQuestion,
        readiness: APSpendReadinessResponse,
        warnings: list[str] | None = None,
        evidence_consistency: str = "no_financial_query",
    ) -> APSpendQuestionResponse:
        payload = {
            "contract_version": CONTRACT_VERSION,
            "generated_at": generated_at,
            "evidence_as_of": None,
            "status": status,
            "answer_text": answer_text,
            "parsed": parsed.model_dump(),
            "readiness": readiness.model_dump(),
            "total": None,
            "ranking": [],
            "leaders": [],
            "monthly_periods": [],
            "ranking_row_limit": self.repository.AP_SPEND_VENDOR_LIMIT,
            "monthly_period_limit": self.repository.AP_SPEND_MONTHLY_PERIOD_LIMIT,
            "monthly_leader_limit": self.repository.AP_SPEND_MONTHLY_LEADER_LIMIT,
            "ranking_complete": None,
            "leader_set_complete": None,
            "evidence_consistency": evidence_consistency,
            "coverage": [],
            "source_references": [],
            "governance": self._governance().model_dump(),
            "warnings": warnings or [],
            "suggested_questions": self._suggested_questions(),
        }
        return APSpendQuestionResponse(
            **payload,
            evidence_sha256=_canonical_hash(payload),
        )


ap_vendor_spend_service = APVendorSpendService()
