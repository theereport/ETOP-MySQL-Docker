# Lockbox Review

The manual review workspace for PNC lockbox transactions — a separate code
path from the automated `lockbox_preparation` pipeline. A reviewer resolves
the paying customer, corrects or builds the invoice allocation draft against
live ERP open A/R, and saves a disposition (`corrected`, `held`, `approved`)
before export. Every save remains a human disposition; this module never
posts to the ERP.

## Contracts

- `GET /api/v1/documents/jobs/{job_id}/lockbox/review`
- `PUT /api/v1/documents/jobs/{job_id}/lockbox/review/{transaction_id}`
- `GET /api/v1/documents/jobs/{job_id}/lockbox/review/{transaction_id}/customer-notes`
- `POST /api/v1/documents/jobs/{job_id}/lockbox/review/{transaction_id}/customer-notes`
- `GET /api/v1/documents/jobs/{job_id}/lockbox/reviewed-export`
- `POST /api/v1/documents/jobs/{job_id}/lockbox/review-queue-export`

Enterprise-customer linkage used by this workspace is served from the
`customer_match` router, not from here:

- `GET /api/v1/customer-match/linked-customers/{customer_number}`
- `POST /api/v1/customer-match/linked-customers/{customer_number}/link`
- `DELETE /api/v1/customer-match/linked-customers/{customer_number}/link`

## Capabilities

- Editable ERP open-item allocation draft, reconciled live against current
  ERP open A/R (`TMAROP`) as the reviewer works, with due-date and aging-
  bucket bulk-apply shortcuts and a full-text open-item search/picker.
- Statement/aging summary — a read-only mini table (statement date, future,
  current, 01-30, 31-60, over-61, due-now) pulled from the existing
  `customer_360` TMCUST aging fields once a customer resolves.
- **Enterprise customer linking**, from two merged sources:
  - *ERP* — `TMCUST.CUNUMENT` ties an account to a shared enterprise number.
  - *Manual* — a reviewer can link two customers with no CUNUMENT
    relationship at all, or extend an existing ERP-linked group with an
    additional non-ERP member (`source: "erp" | "manual" | "mixed"` in the
    linked-customers response). See `../resolution/manual_enterprise_group_repository.py`.
  - The reviewer toggles left/right through every linked account and adds
    open invoices from any of them into the same allocation draft, so one
    check can be applied across multiple enterprise accounts. Allocation
    rows carry the owning `customer_number` and the table groups rows by
    customer with a divider whenever more than one is present, pulling
    each row's Open Amount/Invoice Date/Due Date/Aging from whichever
    account's open-item evidence it actually belongs to.
- **Misc G/L Entry** — a bounded write-off (currently the single reason
  `Service Charge ADJ`, GL `3880`, server-derived and validated - never
  client-trusted) with reviewer-entered location, department, and amount.
  The amount is subtracted from `check_amount - allocation_total` when
  computing `difference`/`balanced`, so a waived service charge can close
  the remaining gap on a check without a matching invoice allocation row.
  It round-trips on save/reload and exports to its own `misc_gl` workbook
  tab (Check #, Customer #, GL Code, Location, Department, Amount) —
  kept off the main allocation-detail sheet since these rows never post
  against a TMAROP open item.
- Append-only, per-customer notes (separate from the per-transaction
  `notes`/`override_reason` review fields).
- Reviewed and review-queue Excel export, including a `Customer Number`
  column (U) on the reviewed export's detail sheet.

## Decisions this module does not invent

- No ERP write. A save is a local review disposition; applying it in
  MaddenCo remains a separate, human, out-of-band action.
- No automatic reason/GL mapping beyond the single explicit
  `MISC_GL_REASON_CODES` entry maintained in `service.py` — a client-
  submitted GL code is never trusted or persisted as-is.
- No implicit trust that a manually-linked pair of customers is
  financially related beyond "a reviewer said so" — the manual-link
  table is reviewer evidence, not ERP truth, and is always disclosed via
  `source` in the API response.
