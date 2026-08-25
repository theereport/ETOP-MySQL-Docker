from __future__ import annotations

from calendar import monthrange
from datetime import date


class InvoiceAgingCalculator:
    """
    Assigns an invoice aging bucket using its due date.

    Rules:
    - A due date before the aging date is past due.
    - Past-due buckets are based on actual days past due.
    - A due date from the aging date through the next monthly due-date
      cycle is Current.
    - A due date after the next monthly due-date cycle is Future.
    """

    def get_bucket(
        self,
        due_date: date | None,
        aging_as_of_date: date,
    ) -> str:
        if due_date is None:
            return "Unknown"

        days_past_due = (
            aging_as_of_date - due_date
        ).days

        # Due today or before today.
        if days_past_due > 0:
            if days_past_due <= 30:
                return "Past Due 1-30"

            if days_past_due <= 60:
                return "Past Due 31-60"

            if days_past_due <= 90:
                return "Past Due 61-90"

            if days_past_due <= 120:
                return "Past Due 91-120"

            return "Past Due 121+"

        # Determine the next monthly due-date cycle using the invoice's
        # due day. For normal Madden terms, this will commonly be the 10th.
        next_due_cycle = self._next_monthly_due_date(
            aging_as_of_date=aging_as_of_date,
            due_day=due_date.day,
        )

        if due_date <= next_due_cycle:
            return "Current"

        return "Future"

    @staticmethod
    def _next_monthly_due_date(
        aging_as_of_date: date,
        due_day: int,
    ) -> date:
        """
        Finds the next occurrence of the invoice's monthly due day.

        Example:
            Aging date: July 23
            Due day: 10
            Result: August 10
        """

        year = aging_as_of_date.year
        month = aging_as_of_date.month

        current_month_last_day = monthrange(
            year,
            month,
        )[1]

        current_cycle = date(
            year,
            month,
            min(due_day, current_month_last_day),
        )

        if aging_as_of_date <= current_cycle:
            return current_cycle

        if month == 12:
            next_year = year + 1
            next_month = 1
        else:
            next_year = year
            next_month = month + 1

        next_month_last_day = monthrange(
            next_year,
            next_month,
        )[1]

        return date(
            next_year,
            next_month,
            min(due_day, next_month_last_day),
        )