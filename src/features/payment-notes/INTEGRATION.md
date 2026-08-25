# R73 Payment Notes frontend integration

Rebase baseline: `ETOP-R72-FULL-SOURCE-20260822T145120Z-9188fe44.zip`
(SHA-256 `b6c85a104d78a8fb72dac91e8adfec3cddd7a0539cac645f04fc87fb5e90181c`).

This feature is intentionally isolated to `src/features/payment-notes/**`.
The integration owner must register it in the shared shell only after the R73
backend router and default-deny permission mapping are present.

## Frontend export

```tsx
import PaymentNotesWorkspace from './features/payment-notes'
```

Recommended shell identity:

- module title: `Payment Notes`
- module ID: `payment_notes`
- capability/group: warehouse and Accounts Receivable reconciliation
- status: `Ready` only after the backend contract and browser qualification pass

Render the workspace when the shared shell's selected module is `Payment Notes`.
Do not reuse the existing Cash Application screen; R73 records bank-to-Payment-
Notes reconciliation recommendations and local human review only.

## Backend dependency

The feature expects the authenticated, default-deny backend module at
`/api/v1/payment-notes` with:

- `GET /route-references/status`
- `GET /route-references`
- `POST /route-references/upload` (`file`, `version_label`, and
  `idempotency_key` multipart; CSV or XLSX)
- `POST /route-references/{reference_id}/activate` (`idempotency_key` JSON)
- `GET /runs?limit&offset`
- `POST /runs` (`file`, `date_from`, `date_to`, `idempotency_key` multipart)
- `GET /runs/{run_id}`
- `POST /runs/{run_id}/items/{item_id}/reviews`

`api.ts` validates the backend response envelopes at runtime and adapts the
flat `RunDetail` plus nested `item.match` evidence into presentation-only view
models. It derives counts from the returned bank items and deposits, never
manufactures a confidence score, and re-fetches the run after each review so
all projections remain consistent.

The adapter requires the backend's candidate-population total, display cap,
completeness flag, cross-run reuse evidence, and bounded read-only ERP query
provenance. Truncated candidate populations remain visible and cannot be
accepted through the review form. UI labels distinguish arithmetic balance
from a completed local review and never present either state as AR approval or
cash application.

The shared security registry and backend route policy must add module ID
`payment_notes` with default deny. The frontend deliberately does not implement
its own authorization rule.

## Authority boundary

All R73 endpoints are local evidence/review operations. ERP access remains
read-only. The workspace has no controls to update `WHSIGPAY`, `WHSIGIMG`, AR,
cash application, or bank records.
