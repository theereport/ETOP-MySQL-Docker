from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from pydantic import BaseModel, Field

from ..business_objects.models import OpenInvoice


class CombinationMatch(BaseModel):
    invoice_numbers: list[str]
    invoice_count: int
    total_amount: Decimal
    confidence_score: int = Field(ge=0, le=100)
    match_type: str = "exact_combination"
    reasons: list[str] = Field(default_factory=list)


class CombinationMatchResult(BaseModel):
    customer_number: str
    payment_amount: Decimal
    status: str
    confidence_score: int = Field(ge=0, le=100)

    matches: list[CombinationMatch] = Field(default_factory=list)
    recommended_invoice_numbers: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)

    searched_invoice_count: int = 0
    truncated: bool = False

    # Due-date prioritization diagnostics
    anchor_due_date: date | None = None
    matched_through_due_date: date | None = None
    searched_due_date_buckets: list[date] = Field(default_factory=list)


@dataclass(frozen=True)
class _Candidate:
    invoice: OpenInvoice
    cents: int
    due_date: date | None


class CombinationMatcher:
    """
    Find exact multi-invoice combinations without using an LLM.

    Payment application priority:

    1. Invoices due on the 10th of the payment month.
       Example: payment received before 8/1 uses 7/10 as the anchor.

    2. Invoices older than the anchor due date, adding the oldest
       due-date bucket first.

    3. Invoices newer than the anchor due date, adding the earliest
       later bucket first.

    4. Invoices with no due date are searched last.
    """

    def __init__(
        self,
        max_invoices_searched: int = 200,
        max_combination_size: int = 100,
        max_results: int = 100,
    ) -> None:
        self.max_invoices_searched = max_invoices_searched
        self.max_combination_size = max_combination_size
        self.max_results = max_results

    def match(
        self,
        customer_number: str,
        payment_amount: Decimal,
        payment_date: date,
        open_invoices: Iterable[OpenInvoice],
    ) -> CombinationMatchResult:
        normalized_payment_date = self._coerce_date(payment_date)

        if normalized_payment_date is None:
            return CombinationMatchResult(
                customer_number=customer_number,
                payment_amount=self._money(payment_amount),
                status="invalid_payment_date",
                confidence_score=0,
                reasons=[
                    "A valid payment received date is required for due-date-priority matching."
                ],
            )

        target = self._to_cents(payment_amount)

        if target <= 0:
            return CombinationMatchResult(
                customer_number=customer_number,
                payment_amount=self._money(payment_amount),
                status="invalid_payment_amount",
                confidence_score=0,
                reasons=[
                    "Payment amount must be greater than zero."
                ],
            )

        anchor_due_date = self._determine_anchor_due_date(
            payment_date=normalized_payment_date,
        )

        usable: list[_Candidate] = []

        for invoice in open_invoices:
            invoice_cents = self._to_cents(
                invoice.open_amount
            )

            if invoice_cents <= 0:
                continue

            if invoice_cents > target:
                continue

            usable.append(
                _Candidate(
                    invoice=invoice,
                    cents=invoice_cents,
                    due_date=self._coerce_date(
                        getattr(
                            invoice,
                            "due_date",
                            None,
                        )
                    ),
                )
            )

        # Establish the required payment-application priority before
        # applying the configured invoice search limit.
        usable = self._order_candidates_by_priority(
            candidates=usable,
            anchor_due_date=anchor_due_date,
        )

        truncated = (
            len(usable)
            > self.max_invoices_searched
        )

        usable = usable[
            : self.max_invoices_searched
        ]

        if not usable:
            return CombinationMatchResult(
                customer_number=customer_number,
                payment_amount=self._money(
                    payment_amount
                ),
                status="no_usable_open_invoices",
                confidence_score=0,
                searched_invoice_count=0,
                truncated=truncated,
                anchor_due_date=anchor_due_date,
                reasons=[
                    "No eligible positive open invoices were available for combination matching."
                ],
            )

        candidate_pools = (
            self._build_progressive_candidate_pools(
                candidates=usable,
                anchor_due_date=anchor_due_date,
            )
        )

        selected_raw_matches: list[
            list[_Candidate]
        ] = []

        selected_pool: list[_Candidate] = []
        searched_due_date_buckets: list[
            date
        ] = []

        # Search progressively and stop at the first bucket range
        # that produces one or more exact combinations.
        for candidate_pool in candidate_pools:
            raw_matches = self._search_pool(
                candidates=candidate_pool,
                target=target,
            )

            if raw_matches:
                selected_raw_matches = raw_matches
                selected_pool = candidate_pool

                searched_due_date_buckets = (
                    self._get_due_date_buckets(
                        candidate_pool
                    )
                )

                break

        if not selected_raw_matches:
            return CombinationMatchResult(
                customer_number=customer_number,
                payment_amount=self._money(
                    payment_amount
                ),
                status="no_exact_combination",
                confidence_score=0,
                searched_invoice_count=len(
                    usable
                ),
                truncated=truncated,
                anchor_due_date=anchor_due_date,
                searched_due_date_buckets=(
                    self._get_due_date_buckets(
                        usable
                    )
                ),
                reasons=[
                    "No exact multi-invoice combination was found within the configured search limits.",
                    (
                        f"Invoices due {anchor_due_date.isoformat()} "
                        "were searched first, followed by older buckets "
                        "and then later due-date buckets."
                    ),
                ],
            )

        unique_matches = (
            self._deduplicate_matches(
                selected_raw_matches
            )
        )

        ranked_matches = (
            self._rank_matches(
                matches=unique_matches,
                ordered_candidates=selected_pool,
                anchor_due_date=anchor_due_date,
            )
        )

        matched_through_due_date = (
            self._determine_matched_through_date(
                candidates=selected_pool,
                anchor_due_date=anchor_due_date,
            )
        )

        matches = self._build_match_models(
            ranked_matches=ranked_matches,
            payment_amount=payment_amount,
            anchor_due_date=anchor_due_date,
            matched_through_due_date=(
                matched_through_due_date
            ),
        )

        if len(matches) == 1:
            best = matches[0]

            return CombinationMatchResult(
                customer_number=customer_number,
                payment_amount=self._money(
                    payment_amount
                ),
                status="exact_combination_match",
                confidence_score=(
                    best.confidence_score
                ),
                matches=matches,
                recommended_invoice_numbers=(
                    best.invoice_numbers
                ),
                searched_invoice_count=len(
                    selected_pool
                ),
                truncated=truncated,
                anchor_due_date=anchor_due_date,
                matched_through_due_date=(
                    matched_through_due_date
                ),
                searched_due_date_buckets=(
                    searched_due_date_buckets
                ),
                reasons=[
                    "One exact invoice combination was found.",
                    (
                        f"Invoices due {anchor_due_date.isoformat()} "
                        "were prioritized first."
                    ),
                    (
                        "Older due-date buckets were considered from "
                        "oldest to newest before later buckets were added."
                    ),
                ],
            )

        return CombinationMatchResult(
            customer_number=customer_number,
            payment_amount=self._money(
                payment_amount
            ),
            status=(
                "ambiguous_exact_combinations"
            ),
            confidence_score=70,
            matches=matches,
            recommended_invoice_numbers=[],
            searched_invoice_count=len(
                selected_pool
            ),
            truncated=truncated,
            anchor_due_date=anchor_due_date,
            matched_through_due_date=(
                matched_through_due_date
            ),
            searched_due_date_buckets=(
                searched_due_date_buckets
            ),
            reasons=[
                "Multiple exact invoice combinations were found within the earliest eligible due-date range.",
                (
                    f"Invoices due {anchor_due_date.isoformat()} "
                    "were prioritized first."
                ),
                (
                    "Older due-date buckets were added beginning with "
                    "the oldest bucket. Later buckets were considered "
                    "only after the anchor and older buckets."
                ),
                (
                    "The matches are ranked by the fewest skipped "
                    "higher-priority invoices."
                ),
                (
                    "No combination is auto-selected because more "
                    "than one exact result remains."
                ),
            ],
        )

    @staticmethod
    def _determine_anchor_due_date(
        payment_date: date,
    ) -> date:
        """
        The anchor is the 10th of the payment received month.

        Examples:

        Payment received 2026-07-31:
            anchor = 2026-07-10

        Payment received 2026-08-01:
            anchor = 2026-08-10
        """
        return date(
            payment_date.year,
            payment_date.month,
            10,
        )

    def _order_candidates_by_priority(
        self,
        candidates: list[_Candidate],
        anchor_due_date: date,
    ) -> list[_Candidate]:
        anchor_candidates = sorted(
            [
                candidate
                for candidate in candidates
                if (
                    candidate.due_date
                    == anchor_due_date
                )
            ],
            key=self._candidate_tiebreaker,
        )

        older_candidates = sorted(
            [
                candidate
                for candidate in candidates
                if (
                    candidate.due_date
                    is not None
                    and candidate.due_date
                    < anchor_due_date
                )
            ],
            key=lambda candidate: (
                candidate.due_date,
                self._candidate_tiebreaker(
                    candidate
                ),
            ),
        )

        newer_candidates = sorted(
            [
                candidate
                for candidate in candidates
                if (
                    candidate.due_date
                    is not None
                    and candidate.due_date
                    > anchor_due_date
                )
            ],
            key=lambda candidate: (
                candidate.due_date,
                self._candidate_tiebreaker(
                    candidate
                ),
            ),
        )

        missing_due_date = sorted(
            [
                candidate
                for candidate in candidates
                if candidate.due_date is None
            ],
            key=self._candidate_tiebreaker,
        )

        return (
            anchor_candidates
            + older_candidates
            + newer_candidates
            + missing_due_date
        )

    def _build_progressive_candidate_pools(
        self,
        candidates: list[_Candidate],
        anchor_due_date: date,
    ) -> list[list[_Candidate]]:
        """
        Build candidate pools in this order:

        1. Anchor bucket only.
        2. Anchor plus the oldest older bucket.
        3. Add each remaining older bucket in ascending date order.
        4. Add each newer bucket in ascending date order.
        5. Add invoices without due dates last.
        """
        anchor_candidates = [
            candidate
            for candidate in candidates
            if (
                candidate.due_date
                == anchor_due_date
            )
        ]

        older_due_dates = sorted(
            {
                candidate.due_date
                for candidate in candidates
                if (
                    candidate.due_date
                    is not None
                    and candidate.due_date
                    < anchor_due_date
                )
            }
        )

        newer_due_dates = sorted(
            {
                candidate.due_date
                for candidate in candidates
                if (
                    candidate.due_date
                    is not None
                    and candidate.due_date
                    > anchor_due_date
                )
            }
        )

        no_due_date_candidates = [
            candidate
            for candidate in candidates
            if candidate.due_date is None
        ]

        pools: list[list[_Candidate]] = []
        current_pool: list[_Candidate] = []

        # First: the payment month's 10th bucket.
        current_pool.extend(
            anchor_candidates
        )

        if current_pool:
            pools.append(
                list(current_pool)
            )

        # Second: older buckets, beginning with the oldest.
        for due_date_value in older_due_dates:
            current_pool.extend(
                candidate
                for candidate in candidates
                if (
                    candidate.due_date
                    == due_date_value
                )
            )

            pools.append(
                list(current_pool)
            )

        # Third: later buckets, beginning with the earliest
        # date after the anchor.
        for due_date_value in newer_due_dates:
            current_pool.extend(
                candidate
                for candidate in candidates
                if (
                    candidate.due_date
                    == due_date_value
                )
            )

            pools.append(
                list(current_pool)
            )

        # Last: records for which no due date is available.
        if no_due_date_candidates:
            current_pool.extend(
                no_due_date_candidates
            )

            pools.append(
                list(current_pool)
            )

        # If every candidate lacked a due date, make sure there
        # is still one searchable pool.
        if not pools and candidates:
            pools.append(
                list(candidates)
            )

        return pools

    def _search_pool(
        self,
        candidates: list[_Candidate],
        target: int,
    ) -> list[list[_Candidate]]:
        suffix_sums = [
            0
        ] * (
            len(candidates) + 1
        )

        for index in range(
            len(candidates) - 1,
            -1,
            -1,
        ):
            suffix_sums[index] = (
                suffix_sums[index + 1]
                + candidates[index].cents
            )

        raw_matches: list[
            list[_Candidate]
        ] = []

        def search(
            index: int,
            remaining: int,
            chosen: list[_Candidate],
        ) -> None:
            if (
                len(raw_matches)
                >= self.max_results
            ):
                return

            if remaining == 0:
                if len(chosen) >= 2:
                    raw_matches.append(
                        list(chosen)
                    )
                return

            if index >= len(candidates):
                return

            if remaining < 0:
                return

            if (
                suffix_sums[index]
                < remaining
            ):
                return

            if (
                len(chosen)
                >= self.max_combination_size
            ):
                return

            candidate = candidates[index]

            # Include the candidate first because the candidate
            # list is already ordered according to payment priority.
            if candidate.cents <= remaining:
                chosen.append(candidate)

                search(
                    index=index + 1,
                    remaining=(
                        remaining
                        - candidate.cents
                    ),
                    chosen=chosen,
                )

                chosen.pop()

            # Then search without the candidate.
            search(
                index=index + 1,
                remaining=remaining,
                chosen=chosen,
            )

        search(
            index=0,
            remaining=target,
            chosen=[],
        )

        return raw_matches

    @staticmethod
    def _deduplicate_matches(
        matches: list[list[_Candidate]],
    ) -> list[list[_Candidate]]:
        unique: dict[
            tuple[str, ...],
            list[_Candidate],
        ] = {}

        for match in matches:
            key = tuple(
                sorted(
                    str(
                        candidate.invoice.invoice_number
                    )
                    for candidate in match
                )
            )

            unique.setdefault(
                key,
                match,
            )

        return list(
            unique.values()
        )

    def _rank_matches(
        self,
        matches: list[list[_Candidate]],
        ordered_candidates: list[_Candidate],
        anchor_due_date: date,
    ) -> list[list[_Candidate]]:
        priority_positions = {
            str(
                candidate.invoice.invoice_number
            ): index
            for index, candidate
            in enumerate(
                ordered_candidates
            )
        }

        def rank_key(
            group: list[_Candidate],
        ) -> tuple:
            selected_numbers = {
                str(
                    candidate.invoice.invoice_number
                )
                for candidate in group
            }

            selected_positions = sorted(
                priority_positions[number]
                for number
                in selected_numbers
                if number
                in priority_positions
            )

            if selected_positions:
                last_selected_position = (
                    selected_positions[-1]
                )

                skipped_priority_count = sum(
                    1
                    for index, candidate
                    in enumerate(
                        ordered_candidates
                    )
                    if (
                        index
                        < last_selected_position
                        and str(
                            candidate.invoice.invoice_number
                        )
                        not in selected_numbers
                    )
                )
            else:
                skipped_priority_count = len(
                    ordered_candidates
                )

            anchor_count = sum(
                1
                for candidate in group
                if (
                    candidate.due_date
                    == anchor_due_date
                )
            )

            newer_count = sum(
                1
                for candidate in group
                if (
                    candidate.due_date
                    is not None
                    and candidate.due_date
                    > anchor_due_date
                )
            )

            no_due_date_count = sum(
                1
                for candidate in group
                if candidate.due_date is None
            )

            invoice_numbers = tuple(
                sorted(
                    str(
                        candidate.invoice.invoice_number
                    )
                    for candidate in group
                )
            )

            return (
                skipped_priority_count,
                no_due_date_count,
                newer_count,
                -anchor_count,
                len(group),
                invoice_numbers,
            )

        return sorted(
            matches,
            key=rank_key,
        )

    def _build_match_models(
        self,
        ranked_matches: list[
            list[_Candidate]
        ],
        payment_amount: Decimal,
        anchor_due_date: date,
        matched_through_due_date: (
            date | None
        ),
    ) -> list[CombinationMatch]:
        matches: list[
            CombinationMatch
        ] = []

        for rank, group in enumerate(
            ranked_matches,
            start=1,
        ):
            count = len(group)

            # Keep exact mathematical matches strong, but reduce the
            # confidence for unusually large invoice groups.
            score = max(
                70,
                97
                - max(
                    0,
                    count - 2,
                )
                * 2,
            )

            # The first result is the strongest due-date-priority
            # result, but it remains a manual-review item if more
            # than one exact combination exists.
            if rank == 1:
                score = min(
                    95,
                    score + 3,
                )

            reasons = [
                (
                    f"The {count} open invoices total exactly "
                    "to the payment amount."
                ),
                (
                    "The combination was found using deterministic "
                    "cent-based matching."
                ),
                (
                    f"Invoices due {anchor_due_date.isoformat()} "
                    "were prioritized first."
                ),
                (
                    "Older due-date buckets were considered beginning "
                    "with the oldest bucket."
                ),
            ]

            if matched_through_due_date is not None:
                reasons.append(
                    (
                        "The earliest candidate range producing an "
                        "exact match extended through due date "
                        f"{matched_through_due_date.isoformat()}."
                    )
                )

            if rank == 1:
                reasons.append(
                    (
                        "This is the highest-ranked exact combination "
                        "based on due-date payment priority."
                    )
                )

            matches.append(
                CombinationMatch(
                    invoice_numbers=[
                        str(
                            candidate.invoice.invoice_number
                        )
                        for candidate in group
                    ],
                    invoice_count=count,
                    total_amount=self._money(
                        payment_amount
                    ),
                    confidence_score=score,
                    reasons=reasons,
                )
            )

        return matches

    @staticmethod
    def _get_due_date_buckets(
        candidates: list[_Candidate],
    ) -> list[date]:
        return sorted(
            {
                candidate.due_date
                for candidate in candidates
                if candidate.due_date
                is not None
            }
        )

    @staticmethod
    def _determine_matched_through_date(
        candidates: list[_Candidate],
        anchor_due_date: date,
    ) -> date | None:
        due_dates = [
            candidate.due_date
            for candidate in candidates
            if candidate.due_date
            is not None
        ]

        if not due_dates:
            return None

        newer_dates = [
            due_date_value
            for due_date_value in due_dates
            if (
                due_date_value
                > anchor_due_date
            )
        ]

        if newer_dates:
            return max(
                newer_dates
            )

        # When the search stopped within the anchor/older range,
        # return the anchor because it was the first bucket searched.
        if anchor_due_date in due_dates:
            return anchor_due_date

        return max(
            due_dates
        )

    @staticmethod
    def _candidate_tiebreaker(
        candidate: _Candidate,
    ) -> tuple:
        return (
            -candidate.cents,
            str(
                candidate.invoice.invoice_number
            ),
        )

    @staticmethod
    def _coerce_date(
        value: object,
    ) -> date | None:
        if value is None:
            return None

        if isinstance(
            value,
            datetime,
        ):
            return value.date()

        if isinstance(
            value,
            date,
        ):
            return value

        value_text = str(
            value
        ).strip()

        if not value_text:
            return None

        common_formats = (
            "%Y-%m-%d",
            "%Y%m%d",
            "%m/%d/%Y",
            "%m/%d/%y",
        )

        for date_format in common_formats:
            try:
                return datetime.strptime(
                    value_text,
                    date_format,
                ).date()
            except ValueError:
                continue

        return None

    @staticmethod
    def _money(
        value: object,
    ) -> Decimal:
        return Decimal(
            str(value or 0)
        ).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    @classmethod
    def _to_cents(
        cls,
        value: object,
    ) -> int:
        return int(
            cls._money(value)
            * 100
        )