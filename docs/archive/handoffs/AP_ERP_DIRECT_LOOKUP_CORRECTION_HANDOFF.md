# ETOP 0.7.0 Step 5 R1 — AP Direct ERP Lookup Correction

## Baseline

Exact installed Step 5 Read-Only ERP Evidence Gateway, outer package SHA-256
`A15E31BE3F0257414726A32DD8E78914E9274E405776BFF59DCFF44DB41626EB`.

## Corrected workflow

1. Open Accounts Payable → ERP Evidence.
2. Enter a Madden vendor name/number, exact invoice number, or both.
3. Review bounded vendor and posted-invoice candidates.
4. Explicitly select the intended vendor/invoice identity.
5. Inspect exact PMVEND, PMHD, PMDT, PMGLDS, PTHD, PTDT, and PTPY evidence
   with source coverage, warnings, governance, and SHA-256 integrity.
6. Optionally use the retained imported-invoice path when OCR-derived local
   evidence exists.

## Runtime contracts

- `GET /api/v1/erp-evidence/accounts-payable/invoice-search`
- `GET /api/v1/erp-evidence/accounts-payable/invoice-evidence`
- Retained: `GET /api/v1/erp-evidence/accounts-payable/invoices/{ap_invoice_id}`

## Safety

- Vendor name: bounded candidate discovery only, maximum 25.
- Posted invoice identities: maximum 50, exact invoice-number equality.
- Human selection required; `automatic_selection` remains false.
- Sensitive PMVEND banking, routing, tax-ID, contact, phone, email, and address
  fields are never selected.
- No local invoice fabrication, OCR mutation, ERP status interpretation,
  recommendation, Decision, approval, payment, posting, export, notification,
  or ERP write.

## Known coverage

The workstation diagnostic confirmed PMVEND, PMHD, PMDT, and PMGLDS. PTHD and
PTPY mapped keys were partial in the runtime schema. Their query failures remain
visible as degraded coverage and do not block the confirmed posted/vendor
evidence packet.

## Verification

- Nine direct/backend repository and service tests.
- GET-only OpenAPI route verification.
- SQL mutation-surface scan.
- Focused zero-warning lint.
- TypeScript/Vite production build.
- Retained Platform Foundation, Credit, AP, Lockbox, SQL-validator, Automation,
  and static verifier suites in the guarded Windows verifier.
