# ETOP 0.6.6 Release Handoff

## Baseline

- Source: `ETOP-Integrated-Agent-1-4-Current-20260730-0.6.5.zip`
- Source SHA-256:
  `8d00a134fa149e3a109db8889514b2d34fb224c821cba5006a5802ab84adba88`
- Governing artifacts: Complete Blueprint and Agent Operating Contract

## Purpose and completed workflow

This release makes ERP and allocation preparation part of PNC lockbox
processing:

`Process PNC PDF → OCR/extract all transactions → resolve ERP customer for each
transaction → hydrate ERP master data → retrieve/evaluate open invoices →
prepare and save allocation rows → calculate remaining exceptions → open the
saved exception queue → human corrects or approves`

Preparation never approves or posts a transaction.

The allocation rule now evaluates complete exact-due-date groups before broad
EOM or aging-bucket combinations. A matching group returns the actual invoices
and a due-date-specific explanation.

## Changed files

Runtime:

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
- `ETOP-Blueprint/PACKAGE_INDEX.md`
- `INTEGRATION_MANIFEST.md`
- `INSTALL_INTEGRATED_RELEASE.md`
- `Install-ETOP-Integrated-Release.ps1`
- `RELEASE_HANDOFF_0.6.6.md`
- `verification/verify-lockbox-due-date.mjs`

No shared shell, navigation, `src/App.tsx`, backend route, `backend/main.py`, or
`SqlEditor.tsx` change is required.

## Runtime behavior

- The PNC Process action remains active until all transactions finish ERP and
  allocation preparation.
- Prepared customer identity and allocation rows are saved through the
  existing local lockbox review endpoint.
- Older saved OCR results are upgraded through the same batch preparation when
  first reopened; OCR is not rerun.
- The complete recommendation envelope is cached locally by job to prevent
  recalculation after leaving and reopening the workspace.
- Preparation failures continue to the next transaction and leave the failed
  item in review.
- The default automation-center and review-workspace queues show only
  unresolved transactions.
- Prepared/balanced items remain visible under **All transactions**.
- Saved corrections and approvals replace the stale recommendation with a
  saved-result marker instead of forcing another analysis.

## Validation

- TypeScript production build: passed
- Vite production bundle: passed, 90 modules transformed
- Targeted ESLint for all changed TypeScript/TSX files: passed
- Full-project ESLint: 14 pre-existing errors, unchanged from the documented
  0.6.5 baseline; none are in the 0.6.6 changed files
- Exact due-date regression:
  six July 10 invoices totaling $1,129.36: passed
- `can_auto_approve` remains false in the regression result
- Archive exclusion, merge-marker, source-difference, and integrity checks:
  required before release

The production build used Josh's existing local `SqlEditor.tsx` only as the
known build dependency. The file is intentionally excluded from this release
and was not modified.

## Preserved decisions and assumptions

- ERP access remains read-only.
- OCR remains evidence; verified ERP values remain authoritative.
- ERP invoice numbers contain exactly 9 or 10 digits.
- `9999999999` remains the no-remittance placeholder.
- The existing one-cent arithmetic tolerance is unchanged.
- A complete exact-due-date group outranks a generalized aging-bucket
  combination.
- Prepared/balanced does not mean approved.
- No ERP posting or straight-through approval authority was added.
- The existing cash-application endpoint is expected to return open-invoice
  details containing invoice number, due date, and current/open amount.

## Verification for Josh

1. Extract the release outside `C:\Users\Josh.Corbit\vite-project`.
2. Run the guarded installer against the 0.6.5 local baseline.
3. Restart the backend and frontend.
4. Process a PNC lockbox and confirm the Process button advances through OCR
   and **Preparing ERP & Allocations** before the result queue appears.
5. Confirm **Exceptions only** is the default review view.
6. Close and reopen Lockbox Automation, then open a prepared transaction and
   confirm it does not rerun ERP/allocation preparation.
7. Test the $1,129.36 example. Confirm six July 10 invoices appear, the August
   invoices do not, and the explanation identifies the July 10 due date.
8. Confirm a prepared item is not marked Approved and no ERP posting occurs.
