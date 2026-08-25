# ETOP 0.6.7 Release Handoff

## Baseline

- Source: `ETOP-Integrated-Agent-1-4-Current-20260730-0.6.6.zip`
- Source SHA-256:
  `6a56e3255b6c83b500d4555fdfd18407c0e359b0ab899692571dbd0c7242cc85`
- Governing artifacts: Complete Blueprint and Agent Operating Contract

## Purpose and completed workflow

This release corrects partial PNC preparation:

`Reuse saved OCR → compare preparation records to every OCR transaction →
preserve completed checks → resume missing checks → checkpoint each result →
record isolated failures → verify full coverage → calculate exception queue →
enable review and reviewed export`

Rerunning OCR is not required to recover incomplete ERP customer and
allocation preparation.

## Changed files

Runtime:

- `src/modules/document-intelligence/api.ts`
- `src/modules/document-intelligence/components/LockboxAutomationCenter.tsx`
- `src/modules/document-intelligence/components/LockboxReviewWorkspace.tsx`
- `src/modules/document-intelligence/components/lockboxAllocationRules.ts`
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
- `RELEASE_HANDOFF_0.6.7.md`
- `verification/verify-lockbox-customer-aware.mjs`
- `verification/verify-lockbox-due-date.mjs`
- `verification/verify-lockbox-resume.mjs`

The optional abort signal added to the existing document API review-save call
is backward compatible. No shared shell, navigation, `src/App.tsx`, backend
route, `backend/main.py`, customer matching rule, allocation rule, or
`SqlEditor.tsx` change is required.

## Runtime behavior

- A preparation cache is complete only when it covers every transaction in the
  current OCR review, excluding transactions with an existing durable human
  correction or approval.
- Existing 0.6.6 cache records are preserved and remain readable.
- Reopening a 27-of-125 result resumes at transaction 28.
- The preparation record is checkpointed after each transaction.
- Preparation and save operations use bounded technical timeouts.
- A transaction failure is stored as an explicit failed preparation, remains
  in review, and does not abort later transactions.
- The review count, transaction review table, and reviewed export remain
  unavailable until all transactions have a terminal preparation record.
- The primary incomplete-state action is **Resume ERP & Allocations
  (completed/total)**.
- Manual ERP customer selection automatically invokes the same customer-aware
  due-date allocation pipeline used by batch processing.
- Recommendation Refresh also uses that shared pipeline. A generic EOM-aging
  match is converted into actual invoice rows when one exact due-date group
  equals the check.
- Due-date grouping now reads the actual read-only ERP open-invoice rows. It
  does not assume the generic recommendation response embeds due dates and
  open balances.
- Preparation never approves a transaction or writes to ERP.

## Validation

- TypeScript production build: passed
- Vite production bundle: passed, 92 modules transformed
- Targeted ESLint for all changed TypeScript/TSX files: passed
- Full-project ESLint: 14 existing unrelated errors, unchanged from 0.6.6;
  none are in 0.6.7 changed files
- 27-of-125 resumable batch regression: passed
- Individual failure isolation and continuation through transaction 125:
  passed
- Existing six-invoice July 10 / $1,129.36 allocation regression: passed
- Direct ERP open-invoice retrieval and grouping for the same example: passed
- Customer 520459 manual-selection orchestration through the shared due-date
  evaluator: passed
- Archive exclusion, merge-marker, source-difference, and integrity checks:
  passed

The production build used Josh's existing local `SqlEditor.tsx` only as the
known build dependency. The file remains intentionally excluded and was not
modified.

## Preserved decisions and assumptions

- OCR results are reused and remain separate from ERP/allocation preparation.
- ERP access remains read-only.
- Verified ERP data remains authoritative over OCR identity.
- Failed preparation is an exception, not a completed match.
- Prepared/balanced remains separate from approved.
- No ERP posting or straight-through approval authority was added.
- The 9- or 10-digit invoice rule, no-remittance placeholder, one-cent
  tolerance, and exact due-date priority remain unchanged.

## Verification for Josh

1. Install 0.6.7 over the local 0.6.6 baseline.
2. Restart the backend and frontend.
3. Select the previously processed 125-transaction PNC lockbox.
4. Click **Resume ERP & Allocations (27/125)**.
5. Confirm preparation starts at the first missing transaction and progresses
   to 125 of 125 without rerunning OCR.
6. Confirm the review count and exception queue appear only after 125 of 125
   transactions are checked.
7. Close and reopen the module; confirm completed preparation is reused.
8. Confirm any ERP/preparation errors remain visible in review and do not
   prevent later transactions from being prepared.
9. Select customer 520459 on the $1,129.36 check and confirm ETOP
   automatically returns the six invoices due 7/10/26; confirm the 8/10/26
   invoices are excluded.
10. Confirm no transaction is marked Approved automatically and no ERP posting
   occurs.
