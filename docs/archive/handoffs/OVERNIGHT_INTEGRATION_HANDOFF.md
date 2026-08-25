# ETOP Overnight Security, AP Q&A, and Test-Environment Handoff

**Date:** August 13, 2026  
**Status:** Unsealed isolated evaluation candidate  
**Accepted R6 source binding:** `ebc8ac664305b2895c005ea15181c52265776f914e0aebfca6044922fa9095e4`  
**Retained Lockbox overlay binding:** `cc039d8debe3099a370748d3156248f90862bc1b0c3397e4ba8d5bedd01a3059`

## Integrated scope

- Security & Access extends the existing Workflow Foundation identity, role,
  session, assignment, and hash-chained audit implementation.
- Administrators with both Workflow Coordinator role and explicit Security &
  Access permission may create or revoke expiring one-time invitations,
  suspend/reactivate accounts, and replace a user's versioned module profile.
- Every current Ready UI module is toggleable. Navigation is filtered in the
  browser, and all 174 current FastAPI routes are independently mapped and
  enforced by default-deny backend middleware.
- The AP Vendor Spend Q&A supports total spend, one-period highest vendor, and
  ordered January–December highest-vendor questions over fixed parameterized
  PMGLDS queries in one read-only consistent snapshot. PTDT readiness completes
  the seven governed AP evidence categories. Arbitrary SQL is not exposed.
- The Windows test lifecycle creates a separate application instance on ports
  5174/8001 with independent source, application databases, uploads, results,
  jobs, caches, logs, evidence, identity namespace, CORS, invite base URL, and
  ephemeral session secret. It requires a copied snapshot and a proven direct
  SELECT-only ERP identity.
- Retained Lockbox evaluation behavior remains present; no Security or AP
  implementation file edits were made inside Lockbox source paths.

## Integrated verification in the construction workspace

- 456 backend tests passed when each test file ran in a fresh Python process.
- Security focused suites: 15 Workflow tests and 5 HTTP/CORS/cookie/enforcement
  tests passed.
- AP focused suites: 32 Vendor Spend and 10 ERP Evidence Gateway tests passed.
- Nine combined static/frontend verifiers passed: Security origin/registry,
  Workflow Foundation, AP Vendor Spend, ERP Evidence Gateway, and the five
  retained Lockbox evaluation verifiers.
- TypeScript and Vite production build passed with 152 modules. The existing
  large-chunk advisory remains non-blocking.
- The test-environment package verifier passed 13 PowerShell files, 4 Python
  files, 2 JSON files, and all 17 exact dependency pins. Vite configuration and
  privilege-parser probes also passed.

The full backend sweep also exposed two unchanged predecessor failures:
`test_customer_360_module.py` references `TestClient` and `app` without importing
them, and `test_fastapi_lifecycle.py` expects a kernel lifecycle that the exact
accepted baseline does not start. Both fail identically on the retained
combined baseline; neither file was changed by this candidate.

## Installation-site gates still required

- Run the lifecycle on Windows with PowerShell Core 7.5 or later; PowerShell is
  not installed in the Linux construction workspace.
- Validate the dedicated ERP account and schema at startup. The account must
  expose only direct `USAGE`, `SELECT`, and optionally `SHOW VIEW` grants, with
  no roles, dynamic privileges, grant option, or write/DDL authority.
- Confirm `ETOP_AP_PMGDTEINV_NUMERIC_ENCODING` when PMGDTEINV is numeric. AP
  calendar questions fail closed without a confirmed governed encoding.
- Complete the human presentation flow: bootstrap administrator, invitation
  create/revoke/redeem, module on/off and direct-API denial, AP monthly Q&A,
  representative Lockbox regression, evidence review, stop, and rollback.

## Authority boundary

This candidate is not accepted R6, a 4F merge, UAT, pilot, production, or a
live release. It grants no ERP write, financial execution, automatic approval,
posting, payment, cash-application, credit decision, or operational authority.
Passing the isolated tests may create a deterministic review bundle, but live
installation still requires a separate explicit Product Owner decision.
