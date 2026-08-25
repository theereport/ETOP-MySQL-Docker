from __future__ import annotations

from decimal import Decimal
from itertools import combinations

from ..business_objects.models import (
    AgingBucketMatch,
    AgingMatchResult,
    CustomerAgingSnapshot,
)


class AgingBucketMatcher:
    def __init__(
        self,
        tolerance: Decimal = Decimal("0.01"),
    ):
        self.tolerance = tolerance

    def match(
        self,
        check_amount: Decimal,
        aging: CustomerAgingSnapshot,
    ) -> AgingMatchResult:
        check_amount = self._money(check_amount)

        total_balance = self._money(
            aging.total_balance_due
        )

        # First: full balance match
        if self._matches(check_amount, total_balance):
            return AgingMatchResult(
                status="exact",
                method="total_balance_due",
                check_amount=check_amount,
                matched_total=total_balance,
                difference=self._money(
                    check_amount - total_balance
                ),
                matched_buckets=[
                    AgingBucketMatch(
                        bucket_name="TOTAL BALANCE DUE",
                        amount=total_balance,
                    )
                ],
                confidence=1.0,
            )

        buckets = [
            AgingBucketMatch(
                bucket_name="FUTURE DUE",
                amount=self._money(aging.future_due),
            ),
            AgingBucketMatch(
                bucket_name="CURRENT DUE",
                amount=self._money(aging.current_due),
            ),
            AgingBucketMatch(
                bucket_name="PAST DUE 30",
                amount=self._money(aging.past_due_30),
            ),
            AgingBucketMatch(
                bucket_name="PAST DUE 60",
                amount=self._money(aging.past_due_60),
            ),
            AgingBucketMatch(
                bucket_name="PAST DUE 90",
                amount=self._money(aging.past_due_90),
            ),
            AgingBucketMatch(
                bucket_name="PAST DUE 120",
                amount=self._money(aging.past_due_120),
            ),
        ]

        # Ignore zero-value buckets
        active_buckets = [
            bucket
            for bucket in buckets
            if abs(bucket.amount) > self.tolerance
        ]

        matches: list[list[AgingBucketMatch]] = []

        # Tests one bucket, then two, then three, etc.
        for size in range(1, len(active_buckets) + 1):
            for bucket_group in combinations(
                active_buckets,
                size,
            ):
                total = self._money(
                    sum(
                        (
                            bucket.amount
                            for bucket in bucket_group
                        ),
                        Decimal("0.00"),
                    )
                )

                if self._matches(check_amount, total):
                    matches.append(list(bucket_group))

        if len(matches) == 1:
            matched_buckets = matches[0]
            matched_total = self._money(
                sum(
                    (
                        bucket.amount
                        for bucket in matched_buckets
                    ),
                    Decimal("0.00"),
                )
            )

            return AgingMatchResult(
                status="exact",
                method="aging_bucket_combination",
                check_amount=check_amount,
                matched_total=matched_total,
                difference=self._money(
                    check_amount - matched_total
                ),
                matched_buckets=matched_buckets,
                alternate_matches=0,
                confidence=0.95,
            )

        if len(matches) > 1:
            first_match = matches[0]
            matched_total = self._money(
                sum(
                    (
                        bucket.amount
                        for bucket in first_match
                    ),
                    Decimal("0.00"),
                )
            )

            return AgingMatchResult(
                status="review_required",
                method="ambiguous_aging_bucket_combination",
                check_amount=check_amount,
                matched_total=matched_total,
                difference=self._money(
                    check_amount - matched_total
                ),
                matched_buckets=first_match,
                alternate_matches=len(matches),
                confidence=0.70,
                warnings=[
                    (
                        f"{len(matches)} different aging bucket "
                        "combinations match the check amount."
                    )
                ],
            )

        return AgingMatchResult(
            status="not_found",
            method="none",
            check_amount=check_amount,
            matched_total=Decimal("0.00"),
            difference=check_amount,
            confidence=0.0,
            warnings=[
                (
                    "The check amount does not match the total "
                    "balance or any exact aging bucket combination."
                )
            ],
        )

    def _matches(
        self,
        left: Decimal,
        right: Decimal,
    ) -> bool:
        return abs(left - right) <= self.tolerance

    @staticmethod
    def _money(value: Decimal) -> Decimal:
        return Decimal(value).quantize(
            Decimal("0.01")
        )