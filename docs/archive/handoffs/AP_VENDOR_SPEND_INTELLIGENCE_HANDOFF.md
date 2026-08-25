# ETOP 0.7.0 — Governed AP Vendor Spend Intelligence Handoff

## Outcome

The Accounts Payable workspace now includes a read-only **Vendor Spend Q&A**
surface for the three Product Owner question forms authorized by SRC-010 and ADR-017:

1. total vendor spend for division 3 for calendar year 2026 as a whole; and
2. highest-spend vendor for GL account 5050/division 3 (`account 5050-3`) for a
   calendar month/year or an explicitly requested ERP accounting year/period.
3. highest-spend vendor for `account 5050-3` for each calendar month in a
   selected year, returned as twelve ordered month rows.

The measure is always labeled **signed posted AP GL-distribution amount**. It is
`PMGLDS.PMGAMTINV` signed as stored, with positive, negative, and net amounts
shown separately. It is not cash paid, current open AP, approval, payment,
posting, or vendor performance.

## Protected baseline

This 1.1.0 repair was implemented against the exact R6 candidate, SHA-256:

`ebc8ac664305b2895c005ea15181c52265776f914e0aebfca6044922fa9095e4`

with the exact protected Lockbox overlay, SHA-256:

`cc039d8debe3099a370748d3156248f90862bc1b0c3397e4ba8d5bedd01a3059`

No baseline database, ERP row, OCR document, credential, or runtime artifact is
included in this workstream. No Lockbox source was changed.

## Runtime contracts

Both routes reuse the already registered read-only ERP Evidence router:

- `GET /api/v1/erp-evidence/accounts-payable/vendor-spend-readiness`
- `GET /api/v1/erp-evidence/accounts-payable/vendor-spend-question?question=...`

There is no POST, PUT, PATCH, DELETE, export, approval, payment, posting,
notification, source-correction, or ERP-write route.

The question endpoint uses `ap-vendor-spend-question-parser@1.1.0`, not an
external model. It admits fixed intents/slots and sends only validated values to
fixed selected-column, parameter-bound aggregate SQL. Question text is never
interpolated into SQL.

## Evidence and date rules

- Division is `PMGLDS.PMGNBGLDV`; account is `PMGLDS.PMGNBGL`.
- Calendar questions use half-open `PMGLDS.PMGDTEINV` ranges and display the
  exact start/end-exclusive bounds.
- Explicit ERP accounting questions use raw `PMGYR`/`PMGPR` and are never
  relabeled calendar or fiscal.
- Fiscal questions fail closed until an approved fiscal calendar exists.
- Native SQL date/datetime/timestamp columns are filtered directly.
- A numeric `PMGDTEINV` requires the approved environment setting
  `ETOP_AP_PMGDTEINV_NUMERIC_ENCODING=YYYYMMDD` or `MMDDYYYY`. Runtime numeric
  type metadata cannot prove the encoding, so an absent/invalid setting returns
  an unavailable mapping state before any financial row query.
- Ranking is by net signed amount descending, returns at most ten vendors, and
  gives equal displayed amounts the same rank.
- Monthly highest-vendor questions run exactly twelve fixed, parameterized,
  per-month rankings inside the same read-only consistent snapshot. The API and
  UI return January through December in order, preserve no-evidence months, and
  cap each month at ten displayed vendors with per-month tie completeness.
- Vendor groups with no `PMGAMTINV` values are excluded before ranking and
  completeness calculation, so they cannot outrank a real negative amount as a
  fabricated zero leader. Matching rows with no amounts never become a zero-spend answer or
  a vendor leader; partial missing-amount coverage is labeled partial.
- `ranking_complete` reports whether additional vendors exist.
  `leader_set_complete` separately reports whether the row cap could hide more
  rank-1 vendors. If it could, the answer says “at least” and treats the visible
  leader count as a lower bound.
- PMVEND appears in source references only after its minimized vendor-identity
  lookup actually succeeds; vendor-number ranking remains usable without names.
- Required financial mappings must use compatible exact numeric runtime types.
  Numeric date encodings reject approximate and undersized integers and require
  verified decimal precision of at least eight with scale zero.
- Total, ranking, and minimized vendor-name reads for one answer run inside one
  read-only consistent snapshot. Snapshot setup fails closed. The response
  timestamp is captured after retrieval and the UI explicitly labels snapshot
  consistency; responses with no financial query make no snapshot claim, and a
  failed snapshot query is labeled as failed rather than completed evidence.

## Version 1.1.0 repair files

- `backend/modules/erp_evidence/ap_spend_parser.py`
- `backend/modules/erp_evidence/ap_spend_schemas.py`
- `backend/modules/erp_evidence/ap_spend_service.py`
- `backend/modules/erp_evidence/repository.py`
- `backend/modules/erp_evidence/service.py`
- `backend/test_ap_vendor_spend_intelligence.py`
- `backend/test_erp_evidence_gateway.py`
- `src/features/accounts-payable/APVendorSpendIntelligence.tsx`
- `src/features/accounts-payable/AccountsPayableWorkspace.css`
- `src/features/accounts-payable/INTEGRATION.md`
- `src/features/accounts-payable/api.ts`
- `src/features/accounts-payable/types.ts`
- `verification/verify-ap-vendor-spend-intelligence.mjs`
- `verification/verify-erp-evidence-gateway.mjs`
- `ETOP-Blueprint/12_Governance/Source_Records/SRC-010_AP_Vendor_Spend_Intelligence_Source.md`
- `ETOP-Blueprint/10_Architecture_Decision_Records/ADR-017_Governed_AP_Vendor_Spend_Questions.md`
- `ETOP-Blueprint/04_Capabilities/CAP-AP-001_Accounts_Payable_Invoice_Intelligence.md`
- `ETOP-Blueprint/12_Governance/BLUEPRINT_TRACEABILITY_MATRIX.csv`
- `ETOP-Blueprint/12_Governance/BLUEPRINT_TRACEABILITY_MATRIX.md`
- `ETOP-Blueprint/CHANGELOG.md`
- `INTEGRATION_MANIFEST.md`
- `AP_VENDOR_SPEND_INTELLIGENCE_HANDOFF.md`

The OCR and Security workstreams may also touch shared AP frontend or governance
files; merge by preserving both navigation surfaces, contracts, source records,
ADRs, and trace rows. This repair did not touch Lockbox code, `src/App.tsx`,
`backend/main.py`, the shared router registry, package dependencies, database
migrations, or any runtime database.

## Verification completed

- Python compilation of the AP spend parser, schemas, service, repository, API,
  and focused tests: **pass**.
- `python -m unittest test_ap_vendor_spend_intelligence.py -v`: **32 tests
  pass**.
- `node verification/verify-ap-vendor-spend-intelligence.mjs`: **pass**.
- Retained `verify-accounts-payable-workspace.mjs` and
  `verify-erp-evidence-gateway.mjs`: **pass**.
- Focused ESLint over the AP spend panel and shared AP integration files with
  `--max-warnings=0`: **pass**.
- `npm run build`: **pass**, 140 modules transformed. Vite emitted the existing
  non-blocking large-chunk advisory.

The focused tests cover all three requested question forms, `5050-3`, calendar and raw ERP
accounting bases, numeric date-encoding safeguards, positive/negative/net
disclosure, mixed null/negative and empty-sum safeguards, bound parameters, row
caps, truncated rank-1 ties, exact queried sources, exact financial type gates,
unsafe numeric date types, multi-intent/account/date ambiguity, year-like account
isolation, twelve ordered fixed monthly queries within one snapshot, mapping
failure, fiscal/SQL-text rejection,
and no financial query on unsupported input.

FastAPI/OpenAPI startup and a live Madden ERP query were not executed in this
packaging runtime because the Python environment lacks the production FastAPI
and MySQL connector dependencies. The static verifier checks GET-only route
declarations and the SQL mutation surface. Run workstation integration and
retained regression suites after merging all parallel workstreams.

## Open governed gaps

- Product Owner confirmation of numeric `PMGDTEINV` encoding where applicable.
- Approved fiscal calendar, fiscal-year label, and adjustment-period behavior.
- Authoritative reversal/void treatment if management spend must differ from
  signed-as-stored netting.
- Currency and consolidation rules if PMGLDS contains more than one monetary
  basis.
- Confirmation of the production business timezone used to resolve “this
  month/year” at rollover; every response still exposes its concrete range.
- Live schema, query-plan/performance, and value-level reconciliation against
  MaddenCo ERP on the target workstation.

Vendor Invoice Dataset/OCR Parser work is intentionally excluded; it is owned
by the separate OCR agent and is not a dependency of these ERP aggregates.
