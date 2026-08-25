from datetime import date
from decimal import Decimal

from backend.modules.document_intelligence.business_objects.models import (
    CustomerAgingSnapshot,
    OpenInvoice,
)
from backend.modules.document_intelligence.cash_application.service import (
    CashApplicationIntelligenceService,
)


def test_bucket_intent_and_invoice_resolution(tmp_path):
    aging = CustomerAgingSnapshot(
        customer_number="100",
        future_due=Decimal("1000.00"),
        current_due=Decimal("3000.00"),
        past_due_30=Decimal("1284.00"),
        total_balance_due=Decimal("5784.00"),
    )

    invoices = [
        OpenInvoice(
            customer_number="100",
            invoice_number="A",
            invoice_date=date(2026, 6, 1),
            original_amount=Decimal("3000.00"),
            open_amount=Decimal("3000.00"),
            aging_bucket="CURRENT DUE",
        ),
        OpenInvoice(
            customer_number="100",
            invoice_number="B",
            invoice_date=date(2026, 5, 1),
            original_amount=Decimal("1284.00"),
            open_amount=Decimal("1284.00"),
            aging_bucket="PAST DUE 30",
        ),
        OpenInvoice(
            customer_number="100",
            invoice_number="C",
            invoice_date=date(2026, 7, 1),
            original_amount=Decimal("1000.00"),
            open_amount=Decimal("1000.00"),
            aging_bucket="FUTURE DUE",
        ),
    ]

    service = CashApplicationIntelligenceService()
    result = service.resolve(
        customer_number="100",
        check_amount=Decimal("4284.00"),
        aging=aging,
        invoices=invoices,
    )

    assert result.payment_intent.intent_type == "aging_bucket_combination"
    assert result.allocation_result.status == "exact"
