from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Iterable

from pydantic import BaseModel, Field

from ..business_objects.models import OpenInvoice
from .business_rules_engine import (
    BusinessRuleResult,
    BusinessRulesEngine,
)
from .combination_matcher import (
    CombinationMatchResult,
    CombinationMatcher,
)
from .explanation_engine import (
    ExplanationEngine,
    RecommendationExplanation,
)
from .historical_behavior_engine import HistoricalBehaviorProfile
from .invoice_matcher import InvoiceMatchResult, InvoiceMatcher


class CashApplicationRecommendation(BaseModel):
    customer_number: str
    payment_amount: Decimal
    payment_date: date

    status: str
    confidence_score: int = Field(ge=0, le=100)
    review_required: bool
    auto_apply_allowed: bool = False

    recommended_invoice_numbers: list[str] = Field(
        default_factory=list
    )

    strategy: str | None = None
    reasons: list[str] = Field(default_factory=list)

    single_invoice_result: InvoiceMatchResult
    combination_result: CombinationMatchResult | None = None
    historical_behavior: HistoricalBehaviorProfile | None = None

    business_rule_result: BusinessRuleResult
    explanation: RecommendationExplanation


class RecommendationEngine:
    def __init__(
        self,
        invoice_matcher: InvoiceMatcher | None = None,
        combination_matcher: CombinationMatcher | None = None,
        business_rules_engine: BusinessRulesEngine | None = None,
        explanation_engine: ExplanationEngine | None = None,
    ) -> None:
        self.invoice_matcher = (
            invoice_matcher
            or InvoiceMatcher()
        )

        self.combination_matcher = (
            combination_matcher
            or CombinationMatcher()
        )

        self.business_rules_engine = (
            business_rules_engine
            or BusinessRulesEngine()
        )

        self.explanation_engine = (
            explanation_engine
            or ExplanationEngine()
        )

    def recommend(
        self,
        customer_number: str,
        payment_amount: Decimal,
        open_invoices: Iterable[OpenInvoice],
        supplied_invoice_numbers: list[str] | None = None,
        historical_behavior: HistoricalBehaviorProfile | None = None,
        payment_date: date | None = None,
    ) -> CashApplicationRecommendation:
        effective_payment_date = (
            payment_date
            or date.today()
        )

        invoices = list(open_invoices)

        supplied_numbers = [
            str(number).strip()
            for number in (
                supplied_invoice_numbers
                or []
            )
            if str(number).strip()
        ]

        single_result = self.invoice_matcher.match(
            customer_number=customer_number,
            payment_amount=payment_amount,
            open_invoices=invoices,
            supplied_invoice_numbers=supplied_numbers,
        )

        combination_result: CombinationMatchResult | None = None

        supplied_number_mismatch = (
            single_result.status
            in {
                "invoice_number_amount_mismatch",
                "invoice_numbers_amount_mismatch",
            }
        )

        decisive_single_match = (
            single_result.status
            in {
                "exact_match",
                "exact_amount_match",
            }
        )

        # Do not allow combination matching to silently override
        # supplied invoice-number mismatches.
        if (
            not decisive_single_match
            and not supplied_number_mismatch
        ):
            combination_result = (
                self.combination_matcher.match(
                    customer_number=customer_number,
                    payment_amount=payment_amount,
                    payment_date=effective_payment_date,
                    open_invoices=invoices,
                )
            )

        business_rule_result = (
            self.business_rules_engine.evaluate(
                customer_number=customer_number,
                payment_amount=payment_amount,
                payment_date=effective_payment_date,
                single_result=single_result,
                combination_result=combination_result,
                supplied_invoice_numbers=supplied_numbers,
                historical_behavior=historical_behavior,
            )
        )

        recommended_invoice_numbers = (
            self._determine_recommended_invoice_numbers(
                single_result=single_result,
                combination_result=combination_result,
                strategy=business_rule_result.selected_strategy,
            )
        )

        status = self._determine_status(
            business_rule_result
        )

        explanation = self.explanation_engine.explain(
            customer_number=customer_number,
            payment_amount=payment_amount,
            payment_date=effective_payment_date,
            rule_result=business_rule_result,
            single_result=single_result,
            combination_result=combination_result,
            historical_behavior=historical_behavior,
        )

        return CashApplicationRecommendation(
            customer_number=customer_number,
            payment_amount=payment_amount,
            payment_date=effective_payment_date,
            status=status,
            confidence_score=(
                business_rule_result.final_score
            ),
            review_required=(
                business_rule_result.review_required
            ),
            auto_apply_allowed=(
                business_rule_result.auto_apply_allowed
            ),
            recommended_invoice_numbers=(
                recommended_invoice_numbers
            ),
            strategy=(
                business_rule_result.selected_strategy
            ),
            reasons=list(
                explanation.reasoning
            ),
            single_invoice_result=single_result,
            combination_result=combination_result,
            historical_behavior=historical_behavior,
            business_rule_result=business_rule_result,
            explanation=explanation,
        )

    @staticmethod
    def _determine_recommended_invoice_numbers(
        single_result: InvoiceMatchResult,
        combination_result: CombinationMatchResult | None,
        strategy: str | None,
    ) -> list[str]:
        if strategy in {
            "single_invoice",
            "supplied_invoice_number_mismatch",
        }:
            return list(
                single_result.recommended_invoice_numbers
            )

        if (
            strategy == "exact_combination"
            and combination_result is not None
        ):
            return list(
                combination_result.recommended_invoice_numbers
            )

        # Ambiguous combinations are intentionally not placed into
        # the recommendation field.
        return []

    @staticmethod
    def _determine_status(
        business_rule_result: BusinessRuleResult,
    ) -> str:
        strategy = (
            business_rule_result.selected_strategy
        )

        if strategy in {
            "single_invoice",
            "exact_combination",
        }:
            return "recommended"

        if strategy in {
            "ambiguous_combination",
            "supplied_invoice_number_mismatch",
        }:
            return "manual_review"

        return "no_match"