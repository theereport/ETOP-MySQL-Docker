from datetime import date
from decimal import Decimal

from modules.document_intelligence.business_objects.models import OpenInvoice
from modules.document_intelligence.services.combination_matcher import CombinationMatcher


def make_invoice(number: str, amount: str) -> OpenInvoice:
    return OpenInvoice(
        customer_number="123",
        invoice_number=number,
        invoice_count=1,
        invoice_date=date(2026, 7, 1),
        due_date=date(2026, 7, 10),
        original_amount=Decimal(amount),
        open_amount=Decimal(amount),
        open_memo_amount=Decimal("0"),
        discountable_amount=Decimal("0"),
        cash_discount=Decimal("0"),
        debit_credit="D",
        transaction_type="I",
        selling_store=1,
        reference_number=None,
        adjustment_reason=None,
        aging_bucket="Past Due 1-30",
        days_past_due=13,
    )


def test_exact_combination() -> None:
    result = CombinationMatcher().match(
        customer_number="123",
        payment_amount=Decimal("1250.00"),
        open_invoices=[
            make_invoice("11001", "350.00"),
            make_invoice("11002", "275.00"),
            make_invoice("11003", "625.00"),
        ],
    )
    assert result.status == "exact_combination_match"
    assert set(result.recommended_invoice_numbers) == {"11001", "11002", "11003"}
