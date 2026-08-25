"""Application service for read-only ERP Payment Notes reconciliation."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from .erp_repository import ERP_CONTRACT_VERSION, PaymentNotesERPError, PaymentNotesERPRepository
from .matching import (
    INVOICE_EXTRACTION_RULE_VERSION,
    MATCH_RULE_VERSION,
    ExpectedPayment,
    MatchDecision,
    block_cross_run_reuse,
    enrich_signatures,
    enforce_deposit_one_to_one,
    match_payment_item,
)
from .remote_capture import (
    REMOTE_CAPTURE_PARSER_VERSION,
    ParsedRemoteCapture,
    parse_remote_capture,
    physical_items,
)
from .repository import PaymentNotesRepository, payment_notes_repository
from .route_reference import (
    ROUTE_REFERENCE_PARSER_VERSION,
    RouteReferenceData,
    parse_route_reference,
    resolve_store,
)


class PaymentNotesValidationError(ValueError):
    pass


class PaymentNotesPreconditionError(RuntimeError):
    pass


class PaymentNotesService:
    def __init__(
        self,
        repository: PaymentNotesRepository = payment_notes_repository,
        erp: PaymentNotesERPRepository | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.repository = repository
        self.erp = erp
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.id_factory = id_factory or (lambda: uuid4().hex)

    def _now(self) -> str:
        return self.clock().astimezone(timezone.utc).isoformat()

    @staticmethod
    def _actor(session: dict[str, Any]) -> str:
        user = session["user"]
        return str(user.get("username") or user["user_id"])

    def actor_for_token(self, token: str) -> str:
        from core.auth import session_for_token

        return self._actor(session_for_token(token))

    def governance(self) -> dict[str, Any]:
        return {
            "module_id": "payment_notes",
            "authority_boundary": "evidence_and_recommendation_only",
            "erp_access": "read_only",
            "erp_writes": False,
            "balancing_item_type": "Virtual Credit",
            "match_rule_version": MATCH_RULE_VERSION,
            "invoice_extraction_rule_version": INVOICE_EXTRACTION_RULE_VERSION,
            "remote_capture_parser_version": REMOTE_CAPTURE_PARSER_VERSION,
            "route_reference_parser_version": ROUTE_REFERENCE_PARSER_VERSION,
            "erp_contract_version": ERP_CONTRACT_VERSION,
            "erp_snapshot_mode": "independent_bounded_read_only_queries",
            "cross_run_reuse_policy": "unresolved_fail_closed",
        }

    @staticmethod
    def _cross_run_summary(
        payment_id: str,
        uses: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "payment_id": payment_id,
            "prior_run_ids": sorted({str(item["run_id"]) for item in uses}),
            "prior_item_ids": sorted({str(item["item_id"]) for item in uses}),
            "source_types": sorted({str(item["source_type"]) for item in uses}),
        }

    @staticmethod
    def _expected_query_evidence(
        *,
        store: str,
        routes: tuple[str, ...],
        start: date,
        end: date,
        result: Any,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        rows = [asdict(payment) for payment in result.payments]
        canonical = {
            "source_object": "KMTDTA.WHSIGPAY",
            "store_number": store,
            "routes": list(routes),
            "date_from": start.isoformat(),
            "date_to": end.isoformat(),
            "rows": rows,
        }
        metadata = {
            key: value for key, value in canonical.items() if key != "rows"
        }
        metadata.update(
            {
                "retrieved_at": result.retrieved_at,
                "row_limit": result.row_limit,
                "returned_count": len(result.payments),
                "complete": result.complete,
                "canonical_evidence_sha256": PaymentNotesRepository.sha256(canonical),
            }
        )
        return metadata, canonical

    @staticmethod
    def _signature_query_evidence(
        *,
        pairs: list[tuple[str, str]],
        result: Any,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        rows = [
            asdict(evidence)
            for pair in sorted(result.evidence)
            for evidence in result.evidence[pair]
        ]
        canonical = {
            "source_object": "KMTDTA.WHSIGIMG",
            "requested_pairs": [list(pair) for pair in pairs],
            "rows": rows,
        }
        metadata = {
            "source_object": "KMTDTA.WHSIGIMG",
            "retrieved_at": result.retrieved_at,
            "row_limit": result.row_limit,
            "pair_count": result.pair_count,
            "returned_count": len(rows),
            "complete": result.complete,
            "canonical_evidence_sha256": PaymentNotesRepository.sha256(canonical),
        }
        return metadata, canonical

    def import_route_reference(
        self, content: bytes, source_name: str, version_label: str,
        idempotency_key: str, actor: str,
    ) -> dict[str, Any]:
        label = version_label.strip()
        if not label:
            raise PaymentNotesValidationError("Route-reference version_label is required.")
        parsed = parse_route_reference(content, source_name)
        row = self.repository.create_route_reference(
            reference_id="PNR-" + self.id_factory(), version_label=label,
            payload=parsed.to_dict(), actor=actor, occurred_at=self._now(),
            idempotency_key=idempotency_key,
        )
        return self._route_summary(row, self.repository.get_active_route_reference())

    def activate_route_reference(self, reference_id: str, idempotency_key: str, actor: str) -> dict[str, Any]:
        self.repository.activate_route_reference(
            activation_id="PNA-" + self.id_factory(), reference_id=reference_id,
            actor=actor, occurred_at=self._now(), idempotency_key=idempotency_key,
        )
        active = self.repository.get_active_route_reference()
        assert active is not None
        return self._route_summary(active, active)

    @staticmethod
    def _route_summary(row: dict[str, Any], active: dict[str, Any] | None) -> dict[str, Any]:
        payload = row["payload"]
        is_active = bool(active and active["reference_id"] == row["reference_id"])
        return {
            "reference_id": row["reference_id"], "version_label": row["version_label"],
            "source_name": row["source_name"], "source_sha256": row["source_sha256"],
            "source_size": row["source_size"], "parser_version": row["parser_version"],
            "mapping_count": len(payload["mappings"]),
            "input_row_count": payload["input_row_count"], "blank_row_count": payload["blank_row_count"],
            "duplicate_mapping_count": payload["duplicate_mapping_count"],
            "conflict_count": len(payload["conflicts"]), "warnings": payload["warnings"],
            "created_by": row["created_by"], "created_at": row["created_at"],
            "is_active": is_active,
            "activated_at": active.get("activated_at") if is_active else None,
        }

    def list_route_references(self) -> dict[str, Any]:
        active = self.repository.get_active_route_reference()
        items = [self._route_summary(row, active) for row in self.repository.list_route_references()]
        return {"items": items, "total": len(items)}

    def route_reference_status(self) -> dict[str, Any]:
        active = self.repository.get_active_route_reference()
        return {
            "configured": active is not None,
            "active_reference": self._route_summary(active, active) if active else None,
            "run_creation_allowed": active is not None,
            "message": "Active route reference is ready." if active else "Activate a route reference before creating a run.",
        }

    @staticmethod
    def _parse_date(value: str, field: str) -> date:
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise PaymentNotesValidationError(f"{field} must be YYYY-MM-DD.") from exc

    def create_run(
        self, content: bytes, source_name: str, date_from: str, date_to: str,
        idempotency_key: str, actor: str,
    ) -> dict[str, Any]:
        start, end = self._parse_date(date_from, "date_from"), self._parse_date(date_to, "date_to")
        if end < start:
            raise PaymentNotesValidationError("date_to must not precede date_from.")
        active = self.repository.get_active_route_reference()
        if active is None:
            raise PaymentNotesPreconditionError("No active route reference; run creation fails closed.")
        parsed = parse_remote_capture(content, source_name)
        erp = self.erp or PaymentNotesERPRepository()
        run_id = "PNRUN-" + self.id_factory()
        bank_items = physical_items(parsed, run_id)
        row_by_number = {row.source_row_number: row for row in parsed.rows}
        route_payload = active["payload"]
        payments_by_store: dict[str, tuple[tuple[ExpectedPayment, ...], bool, list[str]]] = {}
        route_resolutions: dict[str, dict[str, Any]] = {}
        run_warnings: list[str] = []
        expected_query_provenance: list[dict[str, Any]] = []
        expected_query_snapshots: list[dict[str, Any]] = []
        erp_query_complete = True
        for store in sorted({item.store_number for item in bank_items}):
            resolution = resolve_store(route_payload, store)
            route_resolutions[store] = asdict(resolution)
            if not resolution.routes:
                payments_by_store[store] = ((), False, [f"Store {store} route mapping is {resolution.status}."])
                erp_query_complete = False
                continue
            try:
                evidence = erp.get_expected_payments(resolution.routes, start, end)
                query_provenance, query_snapshot = self._expected_query_evidence(
                    store=store,
                    routes=resolution.routes,
                    start=start,
                    end=end,
                    result=evidence,
                )
                expected_query_provenance.append(query_provenance)
                expected_query_snapshots.append(query_snapshot)
                # Defense in depth: SQL also has the fixed CHECK predicate.
                checks = tuple(p for p in evidence.payments if p.payment_type.strip().upper() == "CHECK")
                warnings = [] if evidence.complete else ["ERP Payment Notes row limit was reached."]
                complete = evidence.complete and not resolution.conflicting_routes
                erp_query_complete = erp_query_complete and complete
                if resolution.conflicting_routes:
                    warnings.append(
                        "One or more routes for this store are conflicted and excluded; automatic selection is blocked."
                    )
                payments_by_store[store] = (checks, complete, warnings)
            except PaymentNotesERPError as exc:
                payments_by_store[store] = ((), False, [str(exc)])
                erp_query_complete = False
                failed_canonical = {
                    "source_object": "KMTDTA.WHSIGPAY",
                    "store_number": store,
                    "routes": list(resolution.routes),
                    "date_from": start.isoformat(),
                    "date_to": end.isoformat(),
                    "rows": [],
                }
                expected_query_provenance.append(
                    {
                        key: value
                        for key, value in failed_canonical.items()
                        if key != "rows"
                    }
                    | {
                        "retrieved_at": self._now(),
                        "row_limit": int(
                            getattr(erp, "EXPECTED_PAYMENT_ROW_LIMIT", 5_000)
                        ),
                        "returned_count": 0,
                        "complete": False,
                        "canonical_evidence_sha256": PaymentNotesRepository.sha256(
                            failed_canonical
                        ),
                        "error": str(exc),
                    }
                )
                expected_query_snapshots.append(failed_canonical)

        decisions: dict[str, MatchDecision] = {}
        for item in bank_items:
            payments, complete, warnings = payments_by_store[item.store_number]
            decision = match_payment_item(item, payments, source_complete=complete)
            if warnings:
                decision = MatchDecision(
                    disposition=decision.disposition, tier=decision.tier,
                    selected_payment_id=decision.selected_payment_id,
                    candidates=decision.candidates, warnings=decision.warnings + tuple(warnings),
                    rule_version=decision.rule_version, source_complete=decision.source_complete,
                    candidate_total_count=decision.candidate_total_count,
                    candidate_display_cap=decision.candidate_display_cap,
                    candidate_population_complete=decision.candidate_population_complete,
                    cross_run_reuse_evidence=decision.cross_run_reuse_evidence,
                )
            decisions[item.item_id] = decision

        # A WHSIGPAY identity may satisfy at most one bank item in the entire
        # run, including when source rows span multiple deposits.
        decisions = enforce_deposit_one_to_one(decisions)

        automatically_selected = {
            decision.selected_payment_id
            for decision in decisions.values()
            if decision.selected_payment_id
        }
        prior_uses = self.repository.prior_run_payment_uses(
            {str(value) for value in automatically_selected}
        )
        for item_id, decision in tuple(decisions.items()):
            selected = decision.selected_payment_id
            if selected and selected in prior_uses:
                decisions[item_id] = block_cross_run_reuse(
                    decision,
                    [self._cross_run_summary(selected, prior_uses[selected])],
                )

        pairs: set[tuple[str, str]] = set()
        for decision in decisions.values():
            for candidate in decision.candidates:
                if candidate.candidate_tier == "T4_AMOUNT_ONLY_REVIEW":
                    continue
                if candidate.expected_payment.invoice_reference_status != "provisional_8_10_digit_tokens":
                    # Partial or otherwise ungoverned invoice serialization
                    # cannot support a definitive WHSIGIMG lookup.
                    continue
                pairs.update((candidate.expected_payment.customer_number, invoice) for invoice in candidate.expected_payment.invoice_numbers)
        signature_map: dict[tuple[str, str], tuple[Any, ...]] = {}
        signature_complete = True
        signature_query_provenance: list[dict[str, Any]] = []
        signature_query_snapshots: list[dict[str, Any]] = []
        ordered_pairs = sorted(pairs)
        for index in range(0, len(ordered_pairs), erp.MAX_SIGNATURE_PAIRS):
            query_pairs = ordered_pairs[index:index + erp.MAX_SIGNATURE_PAIRS]
            try:
                result = erp.get_signature_evidence(query_pairs)
                query_provenance, query_snapshot = self._signature_query_evidence(
                    pairs=query_pairs,
                    result=result,
                )
                signature_query_provenance.append(query_provenance)
                signature_query_snapshots.append(query_snapshot)
                signature_map.update(result.evidence)
                signature_complete = signature_complete and result.complete
            except PaymentNotesERPError as exc:
                signature_complete = False
                run_warnings.append(str(exc))
                failed_canonical = {
                    "source_object": "KMTDTA.WHSIGIMG",
                    "requested_pairs": [list(pair) for pair in query_pairs],
                    "rows": [],
                }
                signature_query_provenance.append(
                    {
                        "source_object": "KMTDTA.WHSIGIMG",
                        "retrieved_at": self._now(),
                        "row_limit": int(
                            getattr(erp, "SIGNATURE_ROW_LIMIT", 2_000)
                        ),
                        "pair_count": len(query_pairs),
                        "returned_count": 0,
                        "complete": False,
                        "canonical_evidence_sha256": PaymentNotesRepository.sha256(
                            failed_canonical
                        ),
                        "error": str(exc),
                    }
                )
                signature_query_snapshots.append(failed_canonical)
                break
        if not signature_complete:
            run_warnings.append("Signature evidence is incomplete; matching was not changed.")
        decisions = {item_id: enrich_signatures(decision, signature_map) for item_id, decision in decisions.items()}

        item_payloads: list[dict[str, Any]] = []
        for item in bank_items:
            source_row = row_by_number[item.source_row_number]
            public = source_row.public_dict(item.item_id)
            public["route_resolution"] = route_resolutions[item.store_number]
            public["match"] = decisions[item.item_id].to_dict()
            item_payloads.append(public)
        deposits = []
        for deposit in parsed.deposits:
            value = deposit.to_dict()
            value["counts_final"] = deposit.quarantined_row_count == 0
            deposits.append(value)
        source_incomplete = bool(parsed.quarantined_rows) or any(
            deposit.status != "BALANCED" for deposit in parsed.deposits
        ) or any(not decision.source_complete for decision in decisions.values())
        requires_review = any(decision.selected_payment_id is None for decision in decisions.values())
        status = "source_incomplete" if source_incomplete else ("requires_review" if requires_review else "completed")
        payload = {
            "run_id": run_id, "status": status,
            "source": {"name": parsed.source_name, "sha256": parsed.source_sha256, "size": parsed.source_size,
                       "parser_version": parsed.parser_version, "source_row_count": parsed.source_row_count},
            "route_reference": {"reference_id": active["reference_id"], "version_label": active["version_label"],
                                "source_sha256": active["source_sha256"]},
            "date_from": start.isoformat(), "date_to": end.isoformat(),
            "erp_provenance": {
                "contract_version": ERP_CONTRACT_VERSION,
                "snapshot_mode": "independent_bounded_read_only_queries",
                "expected_payment_queries": expected_query_provenance,
                "signature_queries": signature_query_provenance,
                "expected_payment_query_count": len(expected_query_provenance),
                "signature_query_count": len(signature_query_provenance),
                "complete": erp_query_complete and signature_complete,
            },
            "deposits": deposits, "items": item_payloads,
            "quarantined_rows": [row.public_dict() for row in parsed.quarantined_rows],
            "warnings": list(dict.fromkeys(run_warnings)),
            "_private_evidence": {
                "bank_rows": [
                    {
                        "source_row_number": row.source_row_number,
                        "source_record_sha256": row.source_record_sha256,
                        "raw_values": row.redacted_raw_values(),
                    }
                    for row in parsed.rows
                ],
                "quarantined_raw_rows": [
                    {
                        "source_row_number": row.source_row_number,
                        "source_record_sha256": row.source_record_sha256,
                        "raw_values": list(row.redacted_raw_values()),
                    }
                    for row in parsed.quarantined_rows
                ],
                "erp_expected_payment_snapshots": expected_query_snapshots,
                "erp_signature_snapshots": signature_query_snapshots,
            },
        }
        stored = self.repository.create_run(run_id=run_id, payload=payload, actor=actor,
                                            occurred_at=self._now(), idempotency_key=idempotency_key)
        return self._public_run(stored)

    @staticmethod
    def _public_run(stored: dict[str, Any]) -> dict[str, Any]:
        payload = dict(stored["payload"])
        payload.pop("_private_evidence", None)
        reviews = list(stored.get("reviews", []))
        current: dict[str, dict[str, Any]] = {}
        for review in reviews:
            current[review["item_id"]] = review
        payload["items"] = [{**item, "current_review": current.get(item["item_id"])} for item in payload["items"]]
        payload.update({"created_by": stored["created_by"], "created_at": stored["created_at"], "reviews": reviews})
        return payload

    def get_run(self, run_id: str) -> dict[str, Any]:
        return self._public_run(self.repository.get_run(run_id))

    def list_runs(self, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        rows = self.repository.list_runs(limit, offset)
        keys = ("run_id", "source_name", "source_sha256", "source_size", "route_reference_id", "date_from", "date_to",
                "status", "deposit_count", "physical_item_count", "quarantined_row_count", "created_by", "created_at")
        items = [{key: row[key] for key in keys} for row in rows]
        return {"items": items, "total": self.repository.count_runs()}

    def review_item(self, run_id: str, item_id: str, payload: Any, actor: str) -> dict[str, Any]:
        run = self.get_run(run_id)
        item = next((value for value in run["items"] if value["item_id"] == item_id), None)
        if item is None:
            raise PaymentNotesValidationError("The reviewed item does not belong to this run.")
        candidate_ids = {candidate["payment_id"] for candidate in item["match"]["candidates"]}
        if payload.decision == "accept_candidate":
            if not item["match"].get("candidate_population_complete", True):
                raise PaymentNotesPreconditionError(
                    "The displayed candidate population is incomplete; candidate acceptance fails closed."
                )
            if not payload.selected_payment_id or payload.selected_payment_id not in candidate_ids:
                raise PaymentNotesValidationError("accept_candidate requires a candidate payment from this item.")
            prior_uses = self.repository.prior_run_payment_uses(
                {payload.selected_payment_id},
                exclude_run_id=run_id,
            )
            if prior_uses:
                raise PaymentNotesPreconditionError(
                    "CROSS_RUN_REUSE_POLICY_UNRESOLVED: the selected Payment Note appears in prior run evidence."
                )
            for other in run["items"]:
                if other["item_id"] == item_id:
                    continue
                current = other.get("current_review")
                if current:
                    effective = (
                        current.get("selected_payment_id")
                        if current.get("decision") == "accept_candidate"
                        else None
                    )
                else:
                    effective = other["match"].get("selected_payment_id")
                if effective == payload.selected_payment_id:
                    raise PaymentNotesPreconditionError(
                        "The selected Payment Note is already assigned to another bank item in this run."
                    )
        elif payload.selected_payment_id is not None:
            raise PaymentNotesValidationError("selected_payment_id is only valid for accept_candidate.")
        event = self.repository.append_review(
            event_id="PNREV-" + self.id_factory(), run_id=run_id, item_id=item_id,
            decision=payload.decision, selected_payment_id=payload.selected_payment_id,
            reason=payload.reason.strip(), actor=actor, occurred_at=self._now(),
            idempotency_key=payload.idempotency_key,
        )
        return {"event": event, "current_review": event, "item_id": item_id, "run_id": run_id}


__all__ = ["PaymentNotesPreconditionError", "PaymentNotesService", "PaymentNotesValidationError"]
