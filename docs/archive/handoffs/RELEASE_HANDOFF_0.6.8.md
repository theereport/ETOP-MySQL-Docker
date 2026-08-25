# ETOP 0.6.8 Release Handoff

## Baseline

- Source: `ETOP-Integrated-Agent-1-4-Current-20260730-0.6.7.zip`
- Source SHA-256:
  `a642c95e1fdd3d42c2e0b6c45baaa9d60a11bb3bcb261c32195e8369ef467a6a`
- Governing artifacts: Complete Blueprint and Agent Operating Contract

## Purpose and completed workflow

This release improves large PNC lockbox preparation without weakening the
0.6.7 completion and recovery contract:

`Reuse OCR → collect unique valid invoices → bulk-read invoice owners →
prepare transactions with four bounded read workers → reuse customer/open-AR
reads → serialize durable review writes → checkpoint each transaction →
verify full coverage → expose the true exception queue`

## Changed files

Runtime:

- `backend/customer_match.py`
- `src/modules/document-intelligence/api.ts`
- `src/modules/document-intelligence/types.ts`
- `src/modules/document-intelligence/components/LockboxAutomationCenter.tsx`
- `src/modules/document-intelligence/components/lockboxPreparation.ts`
- `src/modules/document-intelligence/components/lockboxProcessing.ts`
- `src/modules/document-intelligence/components/lockboxRecommendation.ts`

Governance, release, and verification:

- `CHANGELOG.md`
- `ETOP-Blueprint/10_Architecture_Decision_Records/ADR-001_Lockbox_Preparation_and_Due_Date_Priority.md`
- `ETOP-Blueprint/BLUEPRINT_PACKAGE_MANIFEST.md`
- `INTEGRATION_MANIFEST.md`
- `INSTALL_INTEGRATED_RELEASE.md`
- `Install-ETOP-Integrated-Release.ps1`
- `RELEASE_HANDOFF_0.6.8.md`
- `verification/verify-lockbox-bulk-resolution.mjs`
- `verification/verify-lockbox-performance.mjs`
- `verification/verify-lockbox-resume.mjs`

No application shell, navigation, `src/App.tsx`, `backend/main.py`,
`LockboxReviewWorkspace.tsx`, allocation rule, balancing tolerance, or
`SqlEditor.tsx` change is required.

## Runtime behavior

- One bulk endpoint resolves up to 500 invoice owners per request; the
  frontend uses chunks of 250.
- Bulk results preserve every ERP owner found for each invoice.
- A bulk result selects a customer only when one unique owner remains.
- Missing or ambiguous owner evidence uses the existing transaction-level
  resolver.
- Four read-only transaction preparations run concurrently by default.
- Customer-master reads are shared by customer number.
- Open-invoice reads are shared by customer number and effective aging date.
- Review saves run sequentially and retain transaction-level failure handling.
- Each terminal prepared result is checkpointed as its own IndexedDB record.
- Existing version 1/2 browser caches remain readable and migrate forward.
- If IndexedDB is unavailable, ETOP retains the existing local-storage
  compatibility fallback.
- The exception count, review queue, and reviewed export remain gated until
  every transaction has a terminal preparation record or prior durable human
  decision.

## Quality and authority boundaries

- Invoice ownership remains the first identity authority.
- Ambiguity is never resolved merely to improve speed.
- Customer and invoice data remain read-only ERP facts.
- Exact due-date allocation still requires one unique complete due-date group.
- The $1,129.36 regression still returns the six 7/10/26 invoices and excludes
  8/10/26 invoices.
- `prepared` and `balanced` remain separate from `approved`.
- No ERP posting or automatic approval was added.

## Validation

- TypeScript production build: passed
- Vite production bundle: passed, 90 modules transformed
- Targeted ESLint for all changed TypeScript/TSX files: passed
- Full-project ESLint: 14 existing unrelated errors, unchanged from 0.6.7;
  none are in 0.6.8 changed files
- Python compilation for updated backend customer matching: passed
- Six pure deterministic backend customer-risk/matching checks: passed
- Four-worker / single-writer regression: passed
- Bulk invoice-owner and ambiguity-fallback regression: passed
- 27-of-125 resume and transaction-64 failure-isolation regression: passed
- Six-invoice July 10 / $1,129.36 regression: passed
- Customer 520459 shared allocation-path regression: passed

The production build used a temporary compatibility stub for the intentionally
excluded local `SqlEditor.tsx`. The stub is not included in this release, and
the user's existing SQL editor remains untouched.

## Open follow-on

The 0.6.8 coordinator still runs in the ETOP browser session. The next larger
architecture step is a durable backend lockbox job that continues through
frontend navigation or browser closure and exposes progress through a polling
API. That step requires the full local Document Intelligence backend packages,
which remain intentionally excluded from this sanitized integration package.
It is not required to receive the 0.6.8 bulk-query, cache, concurrency, and
checkpoint improvements.

## Verification for Josh

1. Install 0.6.8 over the local 0.6.7 baseline.
2. Restart the backend and frontend.
3. Open the same 125-transaction PNC lockbox.
4. Resume preparation without rerunning OCR.
5. Confirm progress reaches 125 of 125 and the final exception count appears
   only afterward.
6. Compare elapsed preparation time with 0.6.7.
7. Leave and reopen Lockbox Automation; confirm completed transactions do not
   recalculate.
8. Confirm any ambiguous invoice owner remains in review.
9. Confirm customer 520459 and the $1,129.36 check return all six 7/10/26
   invoices and exclude 8/10/26 invoices.
10. Confirm no transaction is marked Approved automatically and no ERP write
    occurs.
