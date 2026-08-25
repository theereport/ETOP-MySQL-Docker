# ETOP 0.6.9 Release Handoff

## Baseline

- Source: `ETOP-Integrated-Agent-1-4-Current-20260730-0.6.8.zip`
- Source SHA-256:
  `2084304ce34fcda5b242fd3c20a40c1539ad2f661d67b2d05f63cfd73303a7c8`
- Governing artifacts: Complete Blueprint and Agent Operating Contract

## Purpose and completed workflow

This release turns the prepared Lockbox allocation into the human review draft
and corrects the business effect of ERP negative-debit credits:

`Open prepared review → reconcile signed ERP invoice facts → edit apply amount
or remove row → add verified ERP invoice or blank row → validate credit signs
and balance → save correction or approve`

## Changed files

Runtime:

- `src/modules/document-intelligence/components/LockboxReviewWorkspace.tsx`
- `src/modules/document-intelligence/components/lockboxAllocationRules.ts`
- `src/modules/document-intelligence/components/lockboxPreparation.ts`
- `src/modules/document-intelligence/components/lockboxRecommendation.ts`

Governance, release, and verification:

- `CHANGELOG.md`
- `ETOP-Blueprint/10_Architecture_Decision_Records/ADR-001_Lockbox_Preparation_and_Due_Date_Priority.md`
- `ETOP-Blueprint/BLUEPRINT_PACKAGE_MANIFEST.md`
- `INTEGRATION_MANIFEST.md`
- `INSTALL_INTEGRATED_RELEASE.md`
- `Install-ETOP-Integrated-Release.ps1`
- `RELEASE_HANDOFF_0.6.9.md`
- `verification/verify-lockbox-credit-editing.mjs`

No application shell, navigation, `src/App.tsx`, backend route,
`backend/main.py`, balance tolerance, approval authority, ERP write behavior,
or `SqlEditor.tsx` change is required.

## Runtime behavior

- Editable Invoice Allocation is the reviewer's active draft.
- Apply amounts are editable in place.
- Rows can be removed directly from the prepared allocation.
- The reviewer can add any remaining open invoice for the verified ERP
  customer or add a blank row for controlled manual entry.
- Original OCR allocations remain separately preserved.
- ERP open-invoice detail supplies transaction sign, open amount, due date, and
  aging information for the editor.
- A raw ERP `Debit` with a negative source amount is displayed as a Credit,
  annotated with the raw source type, and applied with a negative sign.
- Suggested total and difference are recalculated after sign reconciliation.
- Existing prepared but not human-reviewed 0.6.8 drafts receive the corrected
  credit sign when opened.
- Human-corrected or approved records are never silently rewritten; an
  incorrect positive credit sign is highlighted and must be corrected before
  another save.

## Quality and authority boundaries

- ERP remains the read-only source for customer and open-invoice facts.
- ETOP preserves the raw transaction type and derives business effect from the
  signed amount.
- Draft changes require Save Correction or Approve Transaction.
- Prepared, balanced, corrected, approved, and posted remain distinct states.
- No automatic approval or ERP posting was added.
- The existing one-cent balance tolerance is unchanged.

## Validation

- TypeScript production build: passed
- Vite production bundle: passed, 90 modules transformed
- Targeted ESLint for all changed runtime TypeScript/TSX files: passed
- Full-project ESLint: 14 existing unrelated errors, unchanged from 0.6.8;
  none are in 0.6.9 changed files
- Existing Lockbox bulk-resolution regression: passed
- Existing four-worker / single-writer regression: passed
- Existing 27-of-125 resume regression: passed
- Existing six-invoice July 10 / $1,129.36 regression: passed
- Existing customer-aware allocation regression: passed
- New negative-debit credit/editing regression: passed
  - invoice `431063896`;
  - raw ERP type `Debit`;
  - source amount `-$916.00`;
  - effective type `Credit`;
  - open and proposed apply amount `-$916.00`;
  - recommendation total and difference recalculated; and
  - automatic approval remains false.

The production build used a temporary compatibility stub for the intentionally
excluded local `SqlEditor.tsx`. The stub is not included in this release, and
the user's existing SQL editor remains untouched.

## Verification for Josh

1. Install 0.6.9 over the local 0.6.8 baseline.
2. Restart the backend and frontend.
3. Reopen the prepared customer 431664 transaction.
4. Confirm invoice 431063896 displays as Credit and `-$916.00`.
5. Confirm the row explains that ERP supplied Debit with a negative source
   amount.
6. Edit an apply amount, delete an invoice, add another ERP open invoice, and
   add a blank row.
7. Confirm Draft Total and Draft Difference update immediately.
8. Confirm a positive amount on a credit is blocked from save.
9. Save the correction, leave the workspace, and reopen it.
10. Confirm the saved reviewed rows persist and the original OCR rows remain
    available as the parser-original evidence.
11. Confirm no transaction is approved automatically and no ERP posting
    occurs.
