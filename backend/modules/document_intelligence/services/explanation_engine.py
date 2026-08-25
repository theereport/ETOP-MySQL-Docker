from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from .business_rules_engine import BusinessRuleResult
from .combination_matcher import CombinationMatchResult
from .historical_behavior_engine import HistoricalBehaviorProfile
from .invoice_matcher import InvoiceMatchResult


class RecommendationExplanation(BaseModel):
    headline: str
    summary: str
    reasoning: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    confidence_explanation: str
    decision_trace: list[str] = Field(default_factory=list)


class ExplanationEngine:
    """
    Produces deterministic, user-facing explanations.

    No LLM is used here. The explanation is built directly from the
    matcher results and business-rule evaluation.
    """

    def explain(
        self,
        customer_number: str,
        payment_amount: Decimal,
        payment_date: date,
        rule_result: BusinessRuleResult,
        single_result: InvoiceMatchResult,
        combination_result: CombinationMatchResult | None = None,
        historical_behavior: HistoricalBehaviorProfile | None = None,
    ) -> RecommendationExplanation:
        strategy = rule_result.selected_strategy

        if strategy == "single_invoice":
            headline = "Exact Single-Invoice Match"

            summary = (
                f"The ${payment_amount:,.2f} payment for customer "
                f"{customer_number} matches one open invoice."
            )

        elif strategy == "exact_combination":
            invoice_count = self._recommended_combination_count(
                combination_result
            )

            headline = "Exact Multi-Invoice Match"

            summary = (
                f"The ${payment_amount:,.2f} payment for customer "
                f"{customer_number} matches an exact combination of "
                f"{invoice_count} open invoices."
            )

        elif strategy == "ambiguous_combination":
            combination_count = (
                len(combination_result.matches)
                if combination_result is not None
                else 0
            )

            headline = "Multiple Exact Combinations Found"

            summary = (
                f"The ${payment_amount:,.2f} payment for customer "
                f"{customer_number} has {combination_count} exact "
                "invoice combinations requiring review."
            )

        elif strategy == "supplied_invoice_number_mismatch":
            headline = "Supplied Invoice Amount Mismatch"

            summary = (
                "The supplied invoice information does not total "
                f"to the ${payment_amount:,.2f} payment amount."
            )

        else:
            headline = "No Exact Invoice Match"

            summary = (
                f"No exact invoice application was found for the "
                f"${payment_amount:,.2f} payment."
            )

        reasoning = list(rule_result.passed_rules)

        if not reasoning:
            reasoning = self._fallback_reasoning(
                single_result=single_result,
                combination_result=combination_result,
            )

        confidence_explanation = self._confidence_explanation(
            score=rule_result.final_score,
            review_required=rule_result.review_required,
            strategy=strategy,
        )

        decision_trace = list(rule_result.decision_trace)

        decision_trace.insert(
            0,
            f"Payment received date: {payment_date.isoformat()}.",
        )

        if historical_behavior is None:
            decision_trace.append(
                "No historical payment profile was used."
            )

        return RecommendationExplanation(
            headline=headline,
            summary=summary,
            reasoning=reasoning,
            warnings=list(rule_result.warnings),
            confidence_explanation=confidence_explanation,
            decision_trace=decision_trace,
        )

    @staticmethod
    def _recommended_combination_count(
        combination_result: CombinationMatchResult | None,
    ) -> int:
        if combination_result is None:
            return 0

        if combination_result.matches:
            return combination_result.matches[0].invoice_count

        return len(
            combination_result.recommended_invoice_numbers
        )

    @staticmethod
    def _fallback_reasoning(
        single_result: InvoiceMatchResult,
        combination_result: CombinationMatchResult | None,
    ) -> list[str]:
        reasons = list(single_result.reasons)

        if combination_result is not None:
            reasons.extend(combination_result.reasons)

        return reasons

    @staticmethod
    def _confidence_explanation(
        score: int,
        review_required: bool,
        strategy: str | None,
    ) -> str:
        if score >= 95 and not review_required:
            return (
                "Confidence is very high because the invoice number and "
                "payment amount agree exactly and no conflicting result remains."
            )

        if score >= 90:
            return (
                "Confidence is high because the recommendation is mathematically "
                "exact and follows the configured cash-application rules."
            )

        if score >= 75:
            return (
                "Confidence is moderate because an exact match exists, but "
                "manual review remains appropriate."
            )

        if strategy == "ambiguous_combination":
            return (
                "Confidence is limited because multiple exact mathematical "
                "combinations remain."
            )

        return (
            "Confidence is low because no sufficiently decisive invoice "
            "application was identified."
        )