# Add near the top of backend/main.py:
from decimal import Decimal
from modules.document_intelligence.integrations.history_repository import HistoryRepository
from modules.document_intelligence.services import (
    AIExplainer,
    HistoricalBehaviorEngine,
    RecommendationEngine,
)

# Add near receivables_repository initialization:
history_repository = HistoryRepository(database=madden_database)
historical_behavior_engine = HistoricalBehaviorEngine()
recommendation_engine = RecommendationEngine()
ai_explainer = AIExplainer()

# Add under the existing invoice-match test endpoint:
@app.get("/api/test/cash-application-recommendation/{customer_number}")
def test_cash_application_recommendation(
    customer_number: str,
    payment_amount: Decimal,
    invoice_number: str | None = None,
    aging_as_of_date: date | None = None,
    include_history: bool = True,
) -> dict:
    effective_aging_date = aging_as_of_date or date.today()
    invoices = receivables_repository.get_open_invoices(
        customer_number=customer_number,
        aging_as_of_date=effective_aging_date,
    )

    behavior = None
    if include_history:
        signals = history_repository.get_invoice_history_signals(customer_number)
        behavior = historical_behavior_engine.analyze(customer_number, signals)

    recommendation = recommendation_engine.recommend(
        customer_number=customer_number,
        payment_amount=payment_amount,
        open_invoices=invoices,
        supplied_invoice_numbers=[invoice_number] if invoice_number else [],
        historical_behavior=behavior,
    )

    return {
        "recommendation": recommendation.model_dump(),
        "explanation": ai_explainer.explain(recommendation),
    }
