# Credit Risk Intelligence — Increments 1–3 Backend

This module enables a credit professional to inspect current customer facts and
record a manual 1–10 risk assessment without creating an automated score,
approval, account hold, order release, credit-line change, posting, export, or
ERP write.

Increment 2 adds deterministic operational ordering for customers that already
have at least one saved manual assessment. It is a professional work queue, not
an automatic credit-risk score, recommendation, approval, notification, or
action.

Increment 3 adds source-grounded credit-line evidence, retains the existing
two-month annualized-sales amount as an unapproved analytical reference, and
stores append-only professional proposals with no decision or ERP effect.

## Contracts

- `GET /api/v1/credit-risk/bands`
- `GET /api/v1/credit-risk/priority-alerts`
- `GET /api/v1/credit-risk/customers/{customer_number}`
- `GET /api/v1/credit-risk/customers/{customer_number}/assessments`
- `POST /api/v1/credit-risk/customers/{customer_number}/assessments`
- `GET /api/v1/credit-risk/customers/{customer_number}/credit-line-intelligence`
- `GET /api/v1/credit-risk/customers/{customer_number}/credit-line-proposals`
- `POST /api/v1/credit-risk/customers/{customer_number}/credit-line-proposals`

The live customer endpoint reuses `modules.customer_360.service.customer_service`.
MaddenCo remains the read-only source for the available current customer facts.
The history endpoint is local-only so prior evidence remains available while the
ERP source is unavailable.

## Priority and alert boundary

- Portfolio coverage begins only from local append-only manual assessments.
  The response reports the assessed-customer count and states that unassessed
  customers are excluded; it does not scan or assign ratings to the ERP
  customer population.
- Draft high-risk-band attention is derived only from the latest saved Product
  Owner draft band snapshot for ratings 7–10 with meanings `High risk`, `Very
  high risk`, `Default likely`, or `Default or legal`. It retains the source
  assessment ID and SHA-256 and is not approved automatic policy.
- The stable operational order is review state (overdue, due today, scheduled),
  higher latest manual rating, deterioration between the latest two manual
  assessments, current partial exposure over line when live evidence is
  available, earlier next-review date, and customer number.
- No numeric weights or score are assigned. Draft-band attention is filterable
  but does not add a separate hidden weight or change the declared order.
- Current over-line evidence uses the live Customer 360 partial-exposure
  reference and keeps the existing full-exposure limitation visible. A live
  source failure produces `unavailable`, never zero, and retains assessment-
  derived review, rating, and deterioration signals.
- Broken-promise and NSF categories are returned as
  `unavailable_source_capability` and emit no alerts until governed sources are
  connected.
- Each priority item references the immutable latest/prior assessments and
  evidence hashes. The projection is generated on read and is not persisted as
  a Decision or Recommendation.

## Exposure boundary

The governed full formula is:

`open A/R + unbilled shipments + releasable orders - unapplied cash - valid credits - secured amounts`

Increment 1 has a governed Customer 360 fact for open A/R and an available but
unclassified ERP on-order aggregate. The API therefore returns `full_exposure`
as `null`, labels completeness `partial`, lists all five unavailable required
components, and presents Customer 360's `open A/R + max(on-order aggregate, 0)`
only as a partial operational reference.

## Credit-line intelligence boundary

The server reuses the shared Customer 360 result and verifies
`round_to_nearest_500((annualized_sales / 12) * 2)` before exposing the existing
reference. Missing sales remains unavailable and a conflicting shared result is
withheld as invalid. Full exposure, seasonality, related accounts, approved
policy, and authority remain explicit gaps.

Credit-line proposals are append-only and hash-verified. They retain the exact
current evidence and are classified as professional recommendations with
`approval_status: not_submitted_to_governed_approval`, `decision_effect: none`,
and `erp_write: false`.

Signed aging buckets are preserved. The service recomputes the bucket total
from future, current, 30, 60, 90, and 120-day values and does not consume the
legacy Customer 360 `total_aging` convenience value.

## Persistence and authority

- The Product Owner supplied band taxonomy is seeded idempotently as versioned
  local configuration with draft status.
- Assessments are append-only; SQLite triggers block update and delete.
- Every assessment retains its selected band, complete band configuration,
  exact customer/exposure/aging/payment snapshot, retrieval time, and canonical
  JSON SHA-256 integrity marker.
- Evidence integrity is verified whenever an assessment is read.
- Missing, null, nonnumeric, boolean, or nonfinite required credit/aging facts
  fail closed instead of becoming authoritative zero; incomplete or malformed
  last-payment evidence is classified as partial or degraded.
- Actor identity is explicitly `operator_supplied` and authority is
  `not_independently_verified`.
- A manual assessment has `decision_effect: none`.
- The request model rejects client-supplied evidence, authority, configuration,
  timestamp, and other undeclared fields.

## Blueprint trace

The implementation traces through SRC-002, CAP-CREDIT-001, DEC-CREDIT-001,
DEC-CREDIT-002, ADR-002, ADR-003, ADR-005, ERM-002, PKM-001, OBJ-008,
OBJ-009, ARCH-006 through ARCH-010, and
PSS-008.
DEC-CREDIT-001 governs only manual professional assessment; it does not grant
credit approval or execution authority. The authority matrix, complete exposure
sources, payment-history source, shared tamper-aware Audit Service, and policy-
promotion authority remain explicit gaps rather than prototype assumptions.
