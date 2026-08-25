from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from .combination_matcher import CombinationMatchResult
from .historical_behavior_engine import HistoricalBehaviorProfile
from .invoice_matcher import InvoiceMatchResult


class RuleScoreComponent(BaseModel):
    rule_code: str
    rule_name: str
    score_adjustment: int
    passed: bool
    explanation: str


class BusinessRuleResult(BaseModel):
    base_score: int = Field(default=0, ge=0, le=100)
    final_score: int = Field(default=0, ge=0, le=100)

    auto_apply_allowed: bool = False
    review_required: bool = True

    selected_strategy: str | None = None

    passed_rules: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    decision_trace: list[str] = Field(default_factory=list)
    score_components: list[RuleScoreComponent] = Field(default_factory=list)


class BusinessRulesEngine:
    """
    Evaluates matcher results using deterministic K&M cash-application rules.

    This engine does not search invoices and does not change invoice totals.

    It evaluates:

    - Supplied invoice numbers
    - Exact single-invoice matches
    - Exact multi-invoice combinations
    - Due-date priority
    - Ambiguous combinations
    - Historical customer behavior

    Historical behavior may adjust confidence, but it may never override
    deterministic invoice matching.
    """

    EXACT_SINGLE_STATUSES = {
        "exact_match",
        "exact_amount_match",
    }

    SUPPLIED_NUMBER_MISMATCH_STATUSES = {
        "invoice_number_amount_mismatch",
        "invoice_numbers_amount_mismatch",
    }

    EXACT_COMBINATION_STATUS = "exact_combination_match"
    AMBIGUOUS_COMBINATION_STATUS = "ambiguous_exact_combinations"

    def evaluate(
        self,
        customer_number: str,
        payment_amount: Decimal,
        payment_date: date,
        single_result: InvoiceMatchResult,
        combination_result: CombinationMatchResult | None = None,
        supplied_invoice_numbers: list[str] | None = None,
        historical_behavior: HistoricalBehaviorProfile | None = None,
    ) -> BusinessRuleResult:
        supplied_numbers = [
            str(number).strip()
            for number in (supplied_invoice_numbers or [])
            if str(number).strip()
        ]

        result = BusinessRuleResult()

        result.decision_trace.extend(
            [
                f"Customer {customer_number} was evaluated.",
                f"Payment amount is ${payment_amount:,.2f}.",
                f"Payment received date is {payment_date.isoformat()}.",
            ]
        )

        if supplied_numbers:
            result.decision_trace.append(
                f"{len(supplied_numbers)} supplied invoice number(s) were provided."
            )
        else:
            result.decision_trace.append(
                "No supplied invoice numbers were provided."
            )

        # Rule order matters. A supplied invoice-number mismatch should
        # remain review-only and should not flow into an automatic combination.
        if single_result.status in self.SUPPLIED_NUMBER_MISMATCH_STATUSES:
            return self._evaluate_supplied_invoice_mismatch(
                result=result,
                single_result=single_result,
            )

        if single_result.status in self.EXACT_SINGLE_STATUSES:
            return self._evaluate_exact_single_match(
                result=result,
                single_result=single_result,
                supplied_invoice_numbers=supplied_numbers,
                historical_behavior=historical_behavior,
            )

        result.decision_trace.append(
            f"Single-invoice matcher returned '{single_result.status}'."
        )

        if combination_result is None:
            result.warnings.append(
                "The combination matcher did not return a result."
            )
            result.decision_trace.append(
                "No multi-invoice result was available."
            )
            return self._finalize(
                result=result,
                base_score=0,
                auto_apply_allowed=False,
                review_required=True,
                strategy="no_match",
            )

        if combination_result.status == self.EXACT_COMBINATION_STATUS:
            return self._evaluate_exact_combination(
                result=result,
                combination_result=combination_result,
                historical_behavior=historical_behavior,
            )

        if combination_result.status == self.AMBIGUOUS_COMBINATION_STATUS:
            return self._evaluate_ambiguous_combination(
                result=result,
                combination_result=combination_result,
                historical_behavior=historical_behavior,
            )

        return self._evaluate_no_match(
            result=result,
            combination_result=combination_result,
        )

    def _evaluate_supplied_invoice_mismatch(
        self,
        result: BusinessRuleResult,
        single_result: InvoiceMatchResult,
    ) -> BusinessRuleResult:
        result.score_components.append(
            RuleScoreComponent(
                rule_code="SUPPLIED_INVOICE_MISMATCH",
                rule_name="Supplied invoice amount validation",
                score_adjustment=0,
                passed=False,
                explanation=(
                    "The supplied invoice number or invoice numbers do not "
                    "total exactly to the payment amount."
                ),
            )
        )

        result.warnings.append(
            "Supplied invoice numbers do not agree with the payment amount."
        )

        result.decision_trace.extend(
            [
                "Supplied invoice numbers were validated.",
                "The supplied invoices did not total exactly to the payment.",
                "Combination matching was not allowed to override the supplied-number mismatch.",
                "Manual review is required.",
            ]
        )

        return self._finalize(
            result=result,
            base_score=single_result.confidence_score,
            auto_apply_allowed=False,
            review_required=True,
            strategy="supplied_invoice_number_mismatch",
        )

    def _evaluate_exact_single_match(
        self,
        result: BusinessRuleResult,
        single_result: InvoiceMatchResult,
        supplied_invoice_numbers: list[str],
        historical_behavior: HistoricalBehaviorProfile | None,
    ) -> BusinessRuleResult:
        base_score = single_result.confidence_score

        result.score_components.append(
            RuleScoreComponent(
                rule_code="EXACT_SINGLE_AMOUNT",
                rule_name="Exact single-invoice amount",
                score_adjustment=0,
                passed=True,
                explanation=(
                    "One open invoice matches the payment amount exactly."
                ),
            )
        )

        result.passed_rules.append(
            "An exact single-invoice amount match was found."
        )

        result.decision_trace.append(
            "The payment matched one open invoice exactly."
        )

        supplied_match = bool(supplied_invoice_numbers)

        if supplied_match:
            base_score += 2

            result.score_components.append(
                RuleScoreComponent(
                    rule_code="SUPPLIED_INVOICE_CONFIRMED",
                    rule_name="Supplied invoice confirmation",
                    score_adjustment=2,
                    passed=True,
                    explanation=(
                        "The supplied invoice information supports the exact match."
                    ),
                )
            )

            result.passed_rules.append(
                "Supplied invoice information supports the recommendation."
            )

            result.decision_trace.append(
                "The supplied invoice information was confirmed."
            )

        else:
            result.score_components.append(
                RuleScoreComponent(
                    rule_code="NO_SUPPLIED_INVOICE",
                    rule_name="No supplied invoice number",
                    score_adjustment=0,
                    passed=False,
                    explanation=(
                        "The match is based on amount because no invoice number "
                        "was supplied."
                    ),
                )
            )

        historical_adjustment = self._single_invoice_history_adjustment(
            historical_behavior=historical_behavior,
        )

        if historical_adjustment != 0:
            base_score += historical_adjustment

            result.score_components.append(
                RuleScoreComponent(
                    rule_code="SINGLE_INVOICE_HISTORY",
                    rule_name="Historical single-invoice behavior",
                    score_adjustment=historical_adjustment,
                    passed=historical_adjustment > 0,
                    explanation=self._single_history_explanation(
                        historical_behavior=historical_behavior,
                        adjustment=historical_adjustment,
                    ),
                )
            )

        if historical_behavior is not None:
            result.decision_trace.append(
                self._history_trace(historical_behavior)
            )

        exact_invoice_number_match = (
            single_result.status == "exact_match"
        )

        auto_apply_allowed = (
            exact_invoice_number_match
            and supplied_match
            and base_score >= 99
        )

        review_required = not auto_apply_allowed

        if auto_apply_allowed:
            result.passed_rules.append(
                "The recommendation meets the configured automatic-application threshold."
            )
            result.decision_trace.append(
                "Automatic application is allowed."
            )
        else:
            result.warnings.append(
                "The exact match remains reviewable under the current automatic-application policy."
            )
            result.decision_trace.append(
                "The result remains available for review."
            )

        return self._finalize(
            result=result,
            base_score=base_score,
            auto_apply_allowed=auto_apply_allowed,
            review_required=review_required,
            strategy="single_invoice",
        )

    def _evaluate_exact_combination(
        self,
        result: BusinessRuleResult,
        combination_result: CombinationMatchResult,
        historical_behavior: HistoricalBehaviorProfile | None,
    ) -> BusinessRuleResult:
        base_score = combination_result.confidence_score

        result.score_components.append(
            RuleScoreComponent(
                rule_code="EXACT_COMBINATION",
                rule_name="Exact multi-invoice amount",
                score_adjustment=0,
                passed=True,
                explanation=(
                    "One multi-invoice combination totals exactly to the payment amount."
                ),
            )
        )

        result.passed_rules.append(
            "An exact multi-invoice combination was found."
        )

        result.decision_trace.append(
            "The single-invoice matcher did not produce a decisive match."
        )

        result.decision_trace.append(
            "The combination matcher found one exact invoice combination."
        )

        due_date_adjustment = self._evaluate_due_date_priority(
            result=result,
            combination_result=combination_result,
        )

        base_score += due_date_adjustment

        history_adjustment = self._combination_history_adjustment(
            historical_behavior=historical_behavior,
        )

        base_score += history_adjustment

        if historical_behavior is not None:
            result.score_components.append(
                RuleScoreComponent(
                    rule_code="COMBINATION_HISTORY",
                    rule_name="Historical combination behavior",
                    score_adjustment=history_adjustment,
                    passed=history_adjustment > 0,
                    explanation=self._combination_history_explanation(
                        historical_behavior=historical_behavior,
                        adjustment=history_adjustment,
                    ),
                )
            )

            result.decision_trace.append(
                self._history_trace(historical_behavior)
            )

        # Exact combinations remain reviewable until the organization
        # explicitly approves automatic multi-invoice application.
        result.warnings.append(
            "Exact multi-invoice combinations require review under the current policy."
        )

        result.decision_trace.append(
            "Manual review is required because the recommendation contains multiple invoices."
        )

        return self._finalize(
            result=result,
            base_score=base_score,
            auto_apply_allowed=False,
            review_required=True,
            strategy="exact_combination",
        )

    def _evaluate_ambiguous_combination(
        self,
        result: BusinessRuleResult,
        combination_result: CombinationMatchResult,
        historical_behavior: HistoricalBehaviorProfile | None,
    ) -> BusinessRuleResult:
        base_score = combination_result.confidence_score

        result.score_components.append(
            RuleScoreComponent(
                rule_code="MULTIPLE_EXACT_COMBINATIONS",
                rule_name="Combination ambiguity",
                score_adjustment=-20,
                passed=False,
                explanation=(
                    "More than one exact invoice combination totals to the payment."
                ),
            )
        )

        base_score -= 20

        result.warnings.append(
            "Multiple exact invoice combinations were found."
        )

        result.decision_trace.extend(
            [
                "The combination matcher found multiple exact mathematical solutions.",
                "No exact combination was automatically selected.",
            ]
        )

        due_date_adjustment = self._evaluate_due_date_priority(
            result=result,
            combination_result=combination_result,
        )

        base_score += due_date_adjustment

        history_adjustment = self._combination_history_adjustment(
            historical_behavior=historical_behavior,
        )

        # Historical behavior can help describe the payment, but it
        # cannot resolve mathematical ambiguity.
        history_adjustment = min(history_adjustment, 1)
        base_score += history_adjustment

        if historical_behavior is not None:
            result.score_components.append(
                RuleScoreComponent(
                    rule_code="AMBIGUOUS_COMBINATION_HISTORY",
                    rule_name="Historical behavior support",
                    score_adjustment=history_adjustment,
                    passed=history_adjustment > 0,
                    explanation=(
                        "Historical behavior was considered, but it cannot "
                        "override multiple exact mathematical combinations."
                    ),
                )
            )

            result.decision_trace.append(
                self._history_trace(historical_behavior)
            )

        result.warnings.append(
            "Historical customer behavior cannot resolve exact-combination ambiguity."
        )

        result.decision_trace.append(
            "Manual review is required because multiple exact combinations remain."
        )

        return self._finalize(
            result=result,
            base_score=base_score,
            auto_apply_allowed=False,
            review_required=True,
            strategy="ambiguous_combination",
        )

    def _evaluate_no_match(
        self,
        result: BusinessRuleResult,
        combination_result: CombinationMatchResult,
    ) -> BusinessRuleResult:
        result.score_components.append(
            RuleScoreComponent(
                rule_code="NO_EXACT_MATCH",
                rule_name="Exact-match requirement",
                score_adjustment=0,
                passed=False,
                explanation=(
                    "No exact single-invoice or multi-invoice match was found."
                ),
            )
        )

        result.warnings.append(
            "The payment does not have a supported exact invoice application."
        )

        result.decision_trace.extend(
            [
                f"Combination matcher returned '{combination_result.status}'.",
                "No exact application recommendation was created.",
                "The payment should remain unapplied until reviewed.",
            ]
        )

        return self._finalize(
            result=result,
            base_score=0,
            auto_apply_allowed=False,
            review_required=True,
            strategy="no_exact_match",
        )

    def _evaluate_due_date_priority(
        self,
        result: BusinessRuleResult,
        combination_result: CombinationMatchResult,
    ) -> int:
        adjustment = 0

        anchor_due_date = getattr(
            combination_result,
            "anchor_due_date",
            None,
        )

        matched_through_due_date = getattr(
            combination_result,
            "matched_through_due_date",
            None,
        )

        searched_buckets = getattr(
            combination_result,
            "searched_due_date_buckets",
            [],
        ) or []

        if anchor_due_date is None:
            result.score_components.append(
                RuleScoreComponent(
                    rule_code="NO_ANCHOR_DUE_DATE",
                    rule_name="Due-date priority availability",
                    score_adjustment=-5,
                    passed=False,
                    explanation=(
                        "The matcher did not provide an anchor due date."
                    ),
                )
            )

            result.warnings.append(
                "Due-date priority could not be fully verified."
            )

            return -5

        result.score_components.append(
            RuleScoreComponent(
                rule_code="ANCHOR_BUCKET_USED",
                rule_name="Anchor due-date priority",
                score_adjustment=5,
                passed=True,
                explanation=(
                    f"Invoices due {anchor_due_date.isoformat()} were "
                    "prioritized first."
                ),
            )
        )

        adjustment += 5

        result.passed_rules.append(
            f"The {anchor_due_date.isoformat()} due-date bucket was prioritized."
        )

        result.decision_trace.append(
            f"Anchor due date was set to {anchor_due_date.isoformat()}."
        )

        if searched_buckets:
            formatted_buckets = ", ".join(
                bucket.isoformat()
                for bucket in searched_buckets
            )

            result.decision_trace.append(
                f"Due-date buckets searched: {formatted_buckets}."
            )

        if (
            matched_through_due_date is not None
            and matched_through_due_date <= anchor_due_date
        ):
            result.score_components.append(
                RuleScoreComponent(
                    rule_code="NO_LATER_BUCKET_REQUIRED",
                    rule_name="Later bucket avoidance",
                    score_adjustment=5,
                    passed=True,
                    explanation=(
                        "The exact combination was found without requiring "
                        "a due-date bucket after the anchor date."
                    ),
                )
            )

            adjustment += 5

            result.passed_rules.append(
                "No later due-date bucket was required."
            )

        elif matched_through_due_date is not None:
            result.score_components.append(
                RuleScoreComponent(
                    rule_code="LATER_BUCKET_REQUIRED",
                    rule_name="Later bucket usage",
                    score_adjustment=0,
                    passed=True,
                    explanation=(
                        "Later due-date buckets were added only after the "
                        "anchor and older buckets were evaluated."
                    ),
                )
            )

            result.decision_trace.append(
                "A later due-date bucket was required to produce an exact match."
            )

        return adjustment

    @staticmethod
    def _single_invoice_history_adjustment(
        historical_behavior: HistoricalBehaviorProfile | None,
    ) -> int:
        if historical_behavior is None:
            return 0

        if historical_behavior.commonly_combines_invoices is False:
            return 1

        if historical_behavior.commonly_combines_invoices is True:
            return -1

        return 0

    @staticmethod
    def _combination_history_adjustment(
        historical_behavior: HistoricalBehaviorProfile | None,
    ) -> int:
        if historical_behavior is None:
            return 0

        if historical_behavior.commonly_combines_invoices is True:
            return 2

        if historical_behavior.commonly_combines_invoices is False:
            return -2

        return 0

    @staticmethod
    def _single_history_explanation(
        historical_behavior: HistoricalBehaviorProfile | None,
        adjustment: int,
    ) -> str:
        if historical_behavior is None:
            return "No historical behavior was available."

        if adjustment > 0:
            return (
                "The customer's historical behavior modestly supports "
                "single-invoice payments."
            )

        return (
            "The customer's historical behavior more commonly includes "
            "multi-invoice payments."
        )

    @staticmethod
    def _combination_history_explanation(
        historical_behavior: HistoricalBehaviorProfile,
        adjustment: int,
    ) -> str:
        ratio = historical_behavior.multiple_payment_ratio

        percentage = (
            float(ratio) * 100
            if ratio is not None
            else 0
        )

        if adjustment > 0:
            return (
                f"Historical payment groups support combined-invoice "
                f"payments at approximately {percentage:.1f}%."
            )

        if adjustment < 0:
            return (
                f"Historical behavior does not strongly support combined-invoice "
                f"payments; the measured ratio is approximately {percentage:.1f}%."
            )

        return (
            "Historical behavior was neutral for this recommendation."
        )

    @staticmethod
    def _history_trace(
        historical_behavior: HistoricalBehaviorProfile,
    ) -> str:
        ratio = historical_behavior.multiple_payment_ratio

        percentage = (
            float(ratio) * 100
            if ratio is not None
            else 0
        )

        return (
            "Historical profile: "
            f"{historical_behavior.sample_size} payment group(s), "
            f"{percentage:.1f}% multi-invoice ratio, "
            f"confidence '{historical_behavior.confidence_level}'."
        )

    @staticmethod
    def _finalize(
        result: BusinessRuleResult,
        base_score: int,
        auto_apply_allowed: bool,
        review_required: bool,
        strategy: str,
    ) -> BusinessRuleResult:
        final_score = max(
            0,
            min(100, int(base_score)),
        )

        result.base_score = max(
            0,
            min(100, int(base_score)),
        )

        result.final_score = final_score
        result.auto_apply_allowed = auto_apply_allowed
        result.review_required = review_required
        result.selected_strategy = strategy

        return result