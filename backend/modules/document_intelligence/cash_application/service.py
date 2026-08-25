from __future__ import annotations

from decimal import Decimal

from .candidate_builder import InvoiceCandidateBuilder
from .data_provider import CashApplicationDataProvider
from .intent_analyzer import PaymentIntentAnalyzer
from .learning_repository import PaymentBehaviorRepository
from .models import (
    CashApplicationDecision,
    LockboxRecommendationRequest,
    LockboxRecommendationResponse,
    SuggestedAllocation,
)
from ..business_objects.models import CustomerAgingSnapshot, OpenInvoice
from ..resolution.aging_matcher import AgingBucketMatcher
from ..resolution.allocation_matcher import AllocationMatcher


class CashApplicationIntelligenceService:
    def __init__(
        self,
        behavior_repository: PaymentBehaviorRepository | None = None,
    ):
        self.aging_matcher = AgingBucketMatcher()
        self.intent_analyzer = PaymentIntentAnalyzer()
        self.candidate_builder = InvoiceCandidateBuilder()
        self.allocation_matcher = AllocationMatcher()
        self.behavior_repository = (
            behavior_repository or PaymentBehaviorRepository()
        )
        self.behavior_repository.initialize()

    def resolve(
        self,
        customer_number: str,
        check_amount: Decimal,
        aging: CustomerAgingSnapshot,
        invoices: list[OpenInvoice],
    ) -> CashApplicationDecision:
        historical_pattern = self.behavior_repository.get_best_pattern(
            customer_number
        )

        aging_match = self.aging_matcher.match(
            check_amount=check_amount,
            aging=aging,
        )

        intent = self.intent_analyzer.analyze(
            check_amount=check_amount,
            aging=aging,
            aging_match=aging_match,
            historical_pattern=historical_pattern,
        )

        candidate_set = self.candidate_builder.build(
            customer_number=customer_number,
            invoices=invoices,
            intent=intent,
        )

        allocation_result = self.allocation_matcher.match(
            check_amount=check_amount,
            invoices=candidate_set.invoices,
        )

        overall_confidence = self._overall_confidence(
            intent.confidence,
            allocation_result.confidence,
            historical_pattern.confidence if historical_pattern else None,
        )

        status = "not_found"
        if allocation_result.status == "exact":
            status = (
                "recommended"
                if overall_confidence >= 0.90
                else "review_required"
            )
        elif allocation_result.status == "review_required":
            status = "review_required"

        reasons = list(intent.explanation)
        if allocation_result.status == "exact":
            reasons.append(
                f"Invoice allocation matched by {allocation_result.method}."
            )
        if historical_pattern:
            reasons.append(
                "Historical customer payment behavior was included in scoring."
            )

        warnings = (
            list(candidate_set.warnings)
            + list(allocation_result.warnings)
        )

        return CashApplicationDecision(
            status=status,
            customer_number=customer_number,
            check_amount=check_amount,
            payment_intent=intent,
            aging_match=aging_match,
            candidate_set=candidate_set,
            allocation_result=allocation_result,
            historical_pattern=historical_pattern,
            overall_confidence=overall_confidence,
            decision_reasons=reasons,
            warnings=warnings,
        )

    @staticmethod
    def _overall_confidence(
        intent_confidence: float,
        allocation_confidence: float,
        historical_confidence: float | None,
    ) -> float:
        weighted = (
            intent_confidence * 0.35
            + allocation_confidence * 0.55
        )

        if historical_confidence is not None:
            weighted += historical_confidence * 0.10
        else:
            weighted += 0.05

        return round(min(weighted, 1.0), 4)


class LockboxRecommendationService:
    def __init__(
        self,
        data_provider: CashApplicationDataProvider,
        intelligence_service: CashApplicationIntelligenceService | None = None,
    ):
        self.data_provider = data_provider
        self.intelligence_service = (
            intelligence_service or CashApplicationIntelligenceService()
        )

    def recommend(
        self,
        request: LockboxRecommendationRequest,
    ) -> LockboxRecommendationResponse:
        customer_match = self.data_provider.resolve_customer(request.identity)

        if customer_match is None:
            return LockboxRecommendationResponse(
                status="customer_not_found",
                transaction_id=request.transaction_id,
                check_amount=request.check_amount,
                decision_reasons=[
                    "No ERP customer could be resolved from the extracted "
                    "customer identity and bank information."
                ],
            )

        customer_data = self.data_provider.load_customer_data(
            customer_match.customer_number
        )

        decision = self.intelligence_service.resolve(
            customer_number=customer_match.customer_number,
            check_amount=request.check_amount,
            aging=customer_data.aging,
            invoices=customer_data.invoices,
        )

        suggestions = self._build_suggestions(request, decision)

        suggested_total = sum(
            (item.suggested_apply_amount for item in suggestions),
            Decimal("0.00"),
        )
        difference = request.check_amount - suggested_total

        if not suggestions and decision.status == "not_found":
            status = "no_invoice_match"
        elif decision.status == "recommended":
            status = "recommended"
        else:
            status = "review_required"

        return LockboxRecommendationResponse(
            status=status,
            transaction_id=request.transaction_id,
            customer_match=customer_match,
            decision=decision,
            suggested_allocations=suggestions,
            check_amount=request.check_amount,
            suggested_total=suggested_total,
            difference=difference,
            can_auto_approve=False,
            decision_reasons=list(decision.decision_reasons),
            warnings=list(customer_match.warnings) + list(decision.warnings),
        )

    def _build_suggestions(
        self,
        request: LockboxRecommendationRequest,
        decision: CashApplicationDecision,
    ) -> list[SuggestedAllocation]:
        result = decision.allocation_result
        if result is None:
            return []

        proposals = result.proposals or []
        extracted_invoice_numbers = set(request.extracted_invoice_numbers)
        suggestions: list[SuggestedAllocation] = []

        candidate_lookup: dict[str, OpenInvoice] = {}
        if decision.candidate_set is not None:
            candidate_lookup = {
                invoice.invoice_number: invoice
                for invoice in decision.candidate_set.invoices
            }

        for proposal in proposals:
            invoice = candidate_lookup.get(proposal.invoice_number)

            reason = (
                "Invoice appeared on the remittance and matched ERP open-invoice data."
                if proposal.invoice_number in extracted_invoice_numbers
                else "Invoice was selected by the cash-application engine."
            )

            suggestions.append(
                SuggestedAllocation(
                    invoice_number=proposal.invoice_number,
                    open_amount=proposal.open_amount,
                    suggested_apply_amount=proposal.proposed_amount,
                    invoice_date=self._string_or_none(
                        invoice.invoice_date if invoice else None
                    ),
                    due_date=self._string_or_none(
                        invoice.due_date if invoice else None
                    ),
                    aging_bucket=proposal.aging_bucket,
                    confidence=float(result.confidence),
                    reason=reason,
                )
            )

        return suggestions

    @staticmethod
    def _string_or_none(value):
        return str(value) if value is not None else None
