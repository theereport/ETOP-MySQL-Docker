# ETOP 0.7.0 Step 5 — Read-Only ERP Evidence Gateway

## Outcome

Step 5 connects current, bounded ERP evidence to the accepted Credit and AP
workspaces without adding ERP writes or financial execution authority.

## Runtime contracts

- `GET /api/v1/erp-evidence/status`
- `GET /api/v1/erp-evidence/credit/customers/{customer_number}`
- `GET /api/v1/erp-evidence/accounts-payable/mapping-readiness`
- `GET /api/v1/erp-evidence/accounts-payable/invoice-search`
- `GET /api/v1/erp-evidence/accounts-payable/invoice-evidence`
- `GET /api/v1/erp-evidence/accounts-payable/invoices/{ap_invoice_id}`

Credit uses `TMCUST`, `TMAROP`, and `TMCUST.CUNUMENT`. AP uses `PMVEND`,
`PMHD`, `PMDT`, `PMGLDS`, `PTHD`, `PTDT`, and `PTPY` from the Product
Owner-supplied DTA273 source record.

## Guardrails

- Exact identity, parameterized SQL, fixed projections, deterministic order,
  and fixed row caps.
- No AP ERP query when the local invoice lacks numeric vendor number or invoice
  number; the separate direct-discovery route remains available in that state.
- Vendor name/number and exact invoice discovery are bounded, parameterized,
  candidate-only, and require human selection before exact evidence retrieval.
- No sensitive vendor bank, routing, tax-ID, contact, phone, email, or address
  selection.
- No inference of undocumented AP status codes, open/paid state, executed
  payment, or three-way match.
- No recommendation, Decision, approval, payment, posting, order action,
  notification, export, external transfer, or ERP write.

## Verification

- Nine backend contract/repository tests cover Credit evidence, AP evidence and
  minimization, direct discovery, ambiguous exact invoice results, empty-search
  rejection, parameter binding, row caps, and the local missing-identity gate.
- Frontend TypeScript compilation and production Vite build pass.
- The release verifier compiles the gateway, runs the contract tests, runs
  zero-warning focused lint, builds the frontend, scans gateway SQL for
  mutation statements, and verifies registered OpenAPI routes when the backend
  is running.
