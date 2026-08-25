# Tax Compliance — Increment 1 Backend

Read-only tax evidence workspace over MaddenCo (schema `DTA273`): a browsable
tax-authority rate reference (`TMTAX`), a browsable tax-exemption-code
reference (`TMTAXE`), and a deterministic check of whether a customer's
exemption code on file (`TMCUST.CUTAXEXCD`) matches a real exemption code in
`TMTAXE`. ETOP owns one local append-only record type: professional notes on
a customer's tax-compliance standing.

This module computes no tax-compliance risk score, rank, approval, or ERP
write. Every response is either a direct MaddenCo read or an explicit,
stated comparison over that read (code match, date-vs-today comparison),
never an inferred judgment.

## Contracts

- `GET /api/v1/tax-compliance/health`
- `GET /api/v1/tax-compliance/tax-authorities?state=&tax_type=&active_only=`
- `GET /api/v1/tax-compliance/tax-authorities/{tax_authority}/{state_code}`
- `GET /api/v1/tax-compliance/exemption-codes?state_code=&tax_type=&active_only=`
- `GET /api/v1/tax-compliance/exemption-codes/{exempt_code}`
- `GET /api/v1/tax-compliance/customers/{customer_number}/exemption-check`
- `POST /api/v1/tax-compliance/customers/exemption-check/batch`
- `GET /api/v1/tax-compliance/customers/{customer_number}/notes`
- `POST /api/v1/tax-compliance/customers/{customer_number}/notes`

## Evidence boundary

- **Tax authority reference** — `TMTAX`, keyed by `(TTAXAUTH, TTAXCODSTE)`.
  `rate_percent` and `max_tax_amount` are `TTAXRATPCT`/`TTAXAMTMAX` exactly
  as MaddenCo stores them (raw decimal fraction and dollar cap); this module
  performs no rate math or tax calculation.
- **Tax exemption code reference** — `TMTAXE`, keyed by
  `(TTXECODEXE, TTXECODSTE)`. `override_or_percent_code` is the raw
  `TTXEOORP` flag value; MaddenCo does not expose a decode table for it in
  this schema, so it is passed through unmodified rather than guessed at.
- **Customer exemption-code integrity check** — reads `TMCUST.CUNUMBER`,
  `CUNAME`, `CUSTATE`, `CUTAXEXCD`, `CUFETEXMPT`, and `CUDTETXEXP` directly
  (the same fields `customer_360`'s `get_customer` already selects for
  `CUTAXEXCD`/`CUFETEXMPT`; this module queries `TMCUST` itself rather than
  depending on `customer_360`). When `CUTAXEXCD` is non-blank, the service
  looks up every `TMTAXE` row sharing that code (across all
  `TTXECODSTE` states) and reports one of three explicit outcomes:
  `matched`, `no_matching_exemption_code_found`, or
  `no_exemption_code_on_customer`. A non-match is never silently treated as
  "not exempt" — it is reported as its own explicit status.
  `expiration_status` is a plain date comparison of `CUDTETXEXP` against
  today's date (`expired` / `current` / `no_expiration_date_on_file`), not a
  risk assessment.
- **Notes** — Local SQLite, append-only (update/delete blocked by trigger),
  each note carries an evidence snapshot and SHA-256 integrity marker over
  the customer's exemption-check evidence at the time the note was written,
  following the same pattern as `vendor_intelligence`/`credit_risk`.

## A schema finding worth flagging

While verifying `TMCUST` against the data dictionary, this module found
`TMCUST.CUDTETXEXP` ("Tax Exempt Cert Exp Date") — a real expiration-date
column that was not in the original task brief's list of known fields. It is
surfaced here as `exemption_certificate_expiration_date` because it is a
direct, real MaddenCo column, not an invented one. It does **not** close the
certificate-tracking gap described below: it is a single current value per
customer, not a document, not a history, and not per-jurisdiction.

## Decisions this module does not invent

- **Exemption certificate document / custody history.** `TMCUST` carries
  only one current exempt code and one current expiration date per
  customer. There is no table storing the scanned/imaged certificate
  itself, prior certificates, or per-jurisdiction certificates for a
  customer exempt in multiple states. This is why the local notes feature
  is this module's primary practical value today — certificate custody
  details belong there until a governed certificate table exists.
- **Jurisdiction nexus / registration tracking.** No table in the current
  schema records which jurisdictions the company or a customer has nexus
  or registration obligations in.
- **Tax compliance risk score.** No approved risk-weighting model is
  configured; this module reports deterministic matches and date
  comparisons only, never a score, rank, or recommendation.

## Blueprint trace

`ETOP-Blueprint/` does not exist in this repository, so there is no ADR/SRC
baseline to trace into. This module follows the architectural pattern
established by `backend/modules/credit_risk` and
`backend/modules/vendor_intelligence` as its de facto baseline instead.
