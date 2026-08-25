# Accounts Payable Intelligence Increments 1–2 frontend integration

Baseline: Git commit `d37d3dd` (ETOP 0.7.0 Credit Risk Increment 1 over
verified 4C + 4D-001).

This feature is intentionally module-local. The integration owner must apply the
shared-shell changes below after integrating the Accounts Payable backend router.

## 1. `src/App.tsx`

Add this import beside the other feature imports:

```tsx
import AccountsPayableWorkspace from './features/accounts-payable'
```

Add this entry after `Credit Risk` in the local `modules` array:

```tsx
{
  title: 'Accounts Payable',
  shortTitle: 'Accounts Payable',
  description:
    'Review imported vendor-invoice evidence, OCR coverage, exceptions, and duplicate candidates.',
  hint: 'Invoice intelligence',
  icon: '▧',
  status: 'Ready',
  group: 'Workspaces',
},
```

Add this render branch after `Credit Risk`:

```tsx
{selectedModule === 'Accounts Payable' && (
  <AccountsPayableWorkspace />
)}
```

Do not replace the existing Document Intelligence `APDashboard`. It remains a
document-intake view. This feature is the dedicated cross-document AP capability
workspace and consumes the new governed API projection.

## 2. `src/platform/registry.ts`

Add this entry after `credit-risk` in `platformModules`:

```tsx
{
  id: 'accounts-payable',
  title: 'Accounts Payable',
  shortTitle: 'Accounts Payable',
  description:
    'Imported vendor-invoice evidence, OCR review, exceptions, and duplicate candidates.',
  icon: '▧',
  group: 'Operations',
  version: '0.1.0',
  status: 'Ready',
  capabilities: ['search', 'timeline'],
  keywords: [
    'accounts payable',
    'ap invoice',
    'vendor invoice',
    'ocr review',
    'duplicate invoice',
    'exception review',
  ],
},
```

Do not add `recommendations`, `ai`, `approval`, or `automation` capabilities in
Increment 1.

## 3. `src/platform/registry/modules.ts`

Add this module-search seed after `credit-risk`:

```tsx
{
  id: 'accounts-payable',
  type: 'module',
  title: 'Accounts Payable',
  subtitle: 'Imported invoice evidence, OCR review, exceptions, and duplicate candidates',
  icon: '▧',
  module: 'Accounts Payable',
  keywords: [
    'accounts payable',
    'ap invoice',
    'vendor invoice',
    'ocr',
    'duplicate',
    'exception',
  ],
},
```

The more generic search seed for Document Operations remains unchanged.

## 4. Backend registration

Register the backend router under `/api/v1/accounts-payable` without changing
Document Intelligence routes. The frontend requires:

- `GET /api/v1/accounts-payable/overview`
- `GET /api/v1/accounts-payable/invoices`
- `GET /api/v1/accounts-payable/invoices/{ap_invoice_id}`
- `POST /api/v1/accounts-payable/sync`
- `POST /api/v1/accounts-payable/sync/document-jobs/{job_id}`
- `POST /api/v1/accounts-payable/invoices/{ap_invoice_id}/control-cases`
- `GET /api/v1/accounts-payable/control-cases`
- `GET /api/v1/accounts-payable/control-cases/{control_case_id}`
- `POST /api/v1/accounts-payable/control-cases/{control_case_id}/reviews`

The list route must support `query`, `status`, `exception`, `duplicate`, `limit`,
and `offset`. The virtual status `ocr_review` powers the OCR Processing view.

## 5. Verification

From the project root, run:

```powershell
node verification/verify-accounts-payable-workspace.mjs
node verification/verify-accounts-payable-controls.mjs
npx eslint src/features/accounts-payable --max-warnings=0
npm.cmd run build
```

The workspace is an evidence and review surface only. Document/extraction review
status must never be presented as AP invoice approval or payment authorization.

Increment 2 adds working Approval Center and Payment Controls views. Both are
evidence-readiness surfaces only. They must display unavailable identity,
authority, ERP payable/vendor, approval-tier, and payment-rail gates and must
not expose Approve, Pay, posting, or ERP mutation controls.

## Step 5 ERP evidence integration

The ERP Evidence view uses:

- `GET /api/v1/erp-evidence/accounts-payable/mapping-readiness`
- `GET /api/v1/erp-evidence/accounts-payable/invoice-search`
- `GET /api/v1/erp-evidence/accounts-payable/invoice-evidence`
- `GET /api/v1/erp-evidence/accounts-payable/invoices/{ap_invoice_id}`

The selected `ap_invoice_id` is first resolved through the existing local AP
invoice service. ERP lookup requires that evidence to contain both a numeric
vendor number and invoice number. The gateway performs exact, bounded reads of
the Product Owner-confirmed DTA273 mapping.

The direct-discovery path does not require a local invoice. Vendor number is
exact; vendor name returns at most 25 PMVEND candidates; invoice number is
exact; and PMHD discovery returns at most 50 distinct vendor/invoice
identities. A professional explicitly selects the intended result before the
exact evidence packet is retrieved. Candidate discovery never updates OCR or
creates a local match.

The same read-only gateway also exposes governed Vendor Spend Q&A:

- `GET /api/v1/erp-evidence/accounts-payable/vendor-spend-readiness`
- `GET /api/v1/erp-evidence/accounts-payable/vendor-spend-question?question=...`

Only three fixed question forms are admitted: signed total spend, highest
vendor for one bounded period, and highest vendor for each ordered calendar
month in a selected year. The monthly form runs twelve fixed parameterized
`PMGDTEINV` rankings in one consistent read-only snapshot and renders January
through December, including explicit no-evidence months. Question text never
becomes SQL, every ranking is bounded, and mapping readiness lists only the
explicit governed AP evidence tables and fields.

`PMHD` is displayed as posted invoice history. `PTHD`, `PTDT`, and `PTPY` are
displayed as input evidence. Raw codes remain uninterpreted; PO/receiver fields
are references rather than a three-way-match result. The view must not present
any fact as open, approved, payable, paid, matched, or executed unless a future
authoritative source contract explicitly proves that state.

## Step 6 AP Vendor Invoice Dataset & OCR

The Accounts Payable workspace now includes a module-local
`vendor_invoice_capture` view backed by existing Document Intelligence routes:

- `POST /api/v1/documents/vendor-invoices/upload`
- `GET /api/v1/documents/vendor-invoices/jobs`
- `GET /api/v1/documents/jobs/{job_id}/result`
- `POST /api/v1/documents/jobs/{job_id}/process`
- `GET /api/v1/documents/jobs/{job_id}/runs`
- `GET /api/v1/documents/jobs/{job_id}/review`
- `PUT /api/v1/documents/jobs/{job_id}/review`
- `GET /api/v1/documents/jobs/{job_id}/file`
- `POST /api/v1/accounts-payable/sync/document-jobs/{job_id}`

The view preserves and displays SHA-256 source identity, latest-success result,
immutable run history, parser/OCR versions, field provenance and ambiguity,
and review/correction state bound to the displayed processing run. It then
uses the exact selected-job AP sync endpoint; no second AP document store or
parser exists. Vendor-invoice list responses include `total`, `limit`, and
`offset`, and the view can load older pages without losing the current
selection to a stale detail response.

`expected_processing_run_id` must be sent when this workflow saves review. A
409 means the extraction advanced and the user must reload before reviewing.
Only a matching current `approved` extraction review enables the UI sync
control. That label means extraction evidence reviewed, never AP invoice
approval, payment authorization, posting, or ERP fact.

The browser receives `stored_file_name`, never the internal repository path.
Original access stays on the registered file endpoint. Current document routes
are intended for the localhost-only proof-of-concept deployment; authenticated
document-access policy remains deferred.

Focused verification:

```powershell
$env:PYTHONPATH = "backend"
python -m unittest -v backend.test_vendor_invoice_capture
python -m unittest -v backend.test_pnc_lockbox_parser
node verification/verify-ap-vendor-invoice-capture.mjs
npx eslint src/features/accounts-payable src/modules/document-intelligence/components/DocumentViewer.tsx src/modules/document-intelligence/components/DocumentResultView.tsx src/modules/document-intelligence/components/APDashboard.tsx src/modules/document-intelligence/components/AIStudio.tsx src/modules/document-intelligence/api.ts src/modules/document-intelligence/types.ts --max-warnings=0
npm.cmd run build
```
