# Phase 4 — Cash Application Intelligence Engine

This package is additive and builds on the working Document Intelligence and
Phase 3 customer/aging resolution code.

## Processing sequence

```text
Matched customer
    ↓
TMCUST aging snapshot
    ↓
Total-balance and bucket-combination matching
    ↓
Payment intent analysis
    ↓
Invoice candidate filtering
    ↓
Controlled invoice combination matching
    ↓
Historical behavior scoring
    ↓
Recommended application or review queue
```

## Added components

- `PaymentIntentAnalyzer`
- `InvoiceCandidateBuilder`
- `PaymentBehaviorRepository`
- `CashApplicationIntelligenceService`
- Confidence-based recommendation output
- Confirmation endpoint for customer behavior learning

## Install

Extract this ZIP over:

```text
C:\Users\Josh.Corbit\vite-project
```

No new Python packages are required beyond the prior phases.

## Register the router

Read:

```text
backend/modules/document_intelligence/cash_application/INTEGRATION_SNIPPET.md
```

## Test

```text
GET /api/v1/documents/cash-application/health
```

## Confirmation endpoint

After a user confirms or rejects a proposed application:

```text
POST /api/v1/documents/cash-application/confirm
```

Example body:

```json
{
  "customer_number": "820328",
  "check_amount": 5200.00,
  "intent_type": "aging_bucket_combination",
  "pattern_key": "CURRENT DUE|PAST DUE 30",
  "was_successful": true
}
```

The system stores repeated customer behavior in the existing Document
Intelligence SQLite database.

## Important dependency

The invoice candidate builder expects each `OpenInvoice` record to contain an
`aging_bucket`. Once the real open-AR table is confirmed, map its aging value
to one of:

- FUTURE DUE
- CURRENT DUE
- PAST DUE 30
- PAST DUE 60
- PAST DUE 90
- PAST DUE 120

The aliases in `candidate_builder.py` can be extended if Madden stores these
values differently.
