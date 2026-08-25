$ErrorActionPreference = "Stop"
$mainPath = Join-Path $PSScriptRoot "backend\main.py"

if (-not (Test-Path $mainPath)) {
    throw "Could not find backend\main.py. Extract this package into the vite-project root first."
}

$content = Get-Content $mainPath -Raw

if ($content -notmatch "from decimal import Decimal") {
    $content = $content.Replace("from datetime import date, datetime", "from datetime import date, datetime`r`nfrom decimal import Decimal")
}
$backupPath = "$mainPath.matching-engine-backup"
Copy-Item $mainPath $backupPath -Force

$importBlock = @'
from modules.document_intelligence.integrations.history_repository import HistoryRepository
from modules.document_intelligence.services import (
    AIExplainer,
    HistoricalBehaviorEngine,
    RecommendationEngine,
)
'@

if ($content -notmatch "HistoryRepository") {
    $anchor = "from modules.document_intelligence.integrations.receivables_repository import (`r`n    ReceivablesRepository,`r`n)"
    if ($content.Contains($anchor)) {
        $content = $content.Replace($anchor, "$anchor`r`n$importBlock")
    }
    else {
        $content = "$importBlock`r`n$content"
    }
}

$serviceBlock = @'

history_repository = HistoryRepository(database=madden_database)
historical_behavior_engine = HistoricalBehaviorEngine()
recommendation_engine = RecommendationEngine()
ai_explainer = AIExplainer()
'@

if ($content -notmatch "recommendation_engine = RecommendationEngine") {
    $anchor = @'
receivables_repository = ReceivablesRepository(
    database=madden_database,
)
'@
    if ($content.Contains($anchor)) {
        $content = $content.Replace($anchor, "$anchor$serviceBlock")
    }
    else {
        throw "Could not locate receivables_repository initialization in backend\main.py. Use MAIN_INTEGRATION_SNIPPET.py manually."
    }
}

$endpointBlock = @'

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
'@

if ($content -notmatch "cash-application-recommendation") {
    $apiMarker = "# ---------------------------------------------------------`r`n# API endpoints`r`n# ---------------------------------------------------------"
    if ($content.Contains($apiMarker)) {
        $content = $content.Replace($apiMarker, "$apiMarker$endpointBlock")
    }
    else {
        $content += $endpointBlock
    }
}

Set-Content -Path $mainPath -Value $content -Encoding UTF8
Write-Host "Matching engine installed successfully."
Write-Host "Backup created at: $backupPath"
Write-Host "Restart the backend and open http://127.0.0.1:8000/docs"
