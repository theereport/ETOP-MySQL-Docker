# R72 — Potential New Customers

R72 extends the existing Credit Risk Workspace with governed K&M credit-application intake.

## API

- `GET /api/v1/credit-risk/potential-customers`
- `POST /api/v1/credit-risk/potential-customers/upload`
- `GET /api/v1/credit-risk/potential-customers/{id}`
- `GET /api/v1/credit-risk/potential-customers/{id}/document`
- `PUT /api/v1/credit-risk/potential-customers/{id}/review`

The upload endpoint accepts the exact two-page K&M Tire Credit Application PDF in R72.1. OCR is local. The source PDF and its SHA-256 are persisted locally. MaddenCo access remains read-only.

## MaddenCo readiness

The current mapping contract covers direct application fields such as CUNAME, CUADDRESS4, CUPHONE, CUEMAIL, CUFEDID, CUCONTACT, CUOFFICER, CUCRTYPBUS, CUPOREQIRE, and CUCSTID plus K&M setup fields such as CUNUMBER, CUROUTECD, CUPRICECD, CUTERMS, CUCLASS, CUTYPE, CUSITE, CUSTORENUM, CUSALESMAN, CUCRLIMIT, and CUBILTOCST.

Field-width violations and unresolved business-code translations are surfaced rather than silently truncated or guessed.

## Existing-customer evidence

Potential-customer matching checks available applicant identifiers against read-only TMCUST evidence. Returned candidates show the matched factors and confidence. R72 never makes an automatic duplicate/customer-creation decision.

## Current boundary

This increment prepares and reviews a Potential Customer only. It does not create, update, merge, or otherwise write a MaddenCo customer record.

## R72.2 parser refinement

The governed K&M V1 parser emits the complete application header schema on every parse. A visible field left empty by the applicant is recorded as `blank`; it is not treated as missing or as a negative answer. `unreadable` and `not_detected` are separate evidence states. Shipping and billing addresses are preserved as street, city, state, and ZIP components. Yes/No controls, including Purchase Order Required, prior K&M relationship, Sales Tax Exempt, Weblink enrollment, and statement-email enrollment, preserve `null` for a blank/undetermined selection; blank is never coerced to `No`.
