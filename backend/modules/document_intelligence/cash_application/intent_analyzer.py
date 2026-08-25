from __future__ import annotations

from decimal import Decimal

from .models import HistoricalPaymentPattern, PaymentIntent
from ..business_objects.models import AgingMatchResult, CustomerAgingSnapshot


class PaymentIntentAnalyzer:
    def analyze(
        self,
        check_amount: Decimal,
        aging: CustomerAgingSnapshot,
        aging_match: AgingMatchResult,
        historical_pattern: HistoricalPaymentPattern | None = None,
    ) -> PaymentIntent:
        if aging_match.status == "exact":
            if aging_match.method == "total_balance_due":
                return PaymentIntent(
                    intent_type="full_balance",
                    confidence=1.0,
                    matched_bucket_names=["TOTAL BALANCE DUE"],
                    explanation=[
                        "Check amount exactly matches the customer's total EOM balance."
                    ],
                )

            if aging_match.method == "aging_bucket_combination":
                bucket_names = [
                    bucket.bucket_name for bucket in aging_match.matched_buckets
                ]
                return PaymentIntent(
                    intent_type="aging_bucket_combination",
                    confidence=aging_match.confidence,
                    matched_bucket_names=bucket_names,
                    explanation=[
                        "Check amount exactly matches a unique combination of EOM aging buckets."
                    ],
                )

        if historical_pattern and historical_pattern.confidence >= 0.90:
            return PaymentIntent(
                intent_type="historical_pattern",
                confidence=historical_pattern.confidence,
                explanation=[
                    f"Customer has a confirmed historical pattern: {historical_pattern.pattern_type}.",
                    f"Observed {historical_pattern.observation_count} times.",
                ],
            )

        return PaymentIntent(
            intent_type="oldest_first",
            confidence=0.55,
            explanation=[
                "No exact total-balance or aging-bucket match was found.",
                "Oldest-first is the controlled fallback before broad combination matching.",
            ],
        )
