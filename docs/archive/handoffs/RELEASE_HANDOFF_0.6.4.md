# ETOP 0.6.4 Release Handoff

## Baseline

- Source: `ETOP-Integrated-Agent-1-4-Current-20260730.zip`
- Source SHA-256:
  `480e75e34aa348b37d05b107af7feb452fcb75e69cbadc26bde2046207e3dbcb`
- Governing artifacts: Complete Blueprint and Agent Operating Contract

## Purpose and completed workflow

This targeted release corrects Lockbox Review recovery and makes verified ERP
invoice ownership authoritative for customer identity:

`Select/re-upload PDF → reopen saved result → open transaction → validate a
9- or 10-digit invoice → resolve ERP customer → hydrate ERP customer master →
load open-invoice recommendation → review/save`

## Changed files

- `CHANGELOG.md`
- `INTEGRATION_MANIFEST.md`
- `INSTALL_INTEGRATED_RELEASE.md`
- `Install-ETOP-Integrated-Release.ps1`
- `RELEASE_HANDOFF_0.6.4.md`
- `backend/customer_match.py`
- `backend/customer_match_service.py`
- `backend/test_customer_match_service.py`
- `src/modules/document-intelligence/DocumentIntelligence.css`
- `src/modules/document-intelligence/components/LockboxAutomationCenter.tsx`
- `src/modules/document-intelligence/components/LockboxReviewWorkspace.tsx`
- `src/modules/document-intelligence/components/lockboxRecommendation.ts`

No shared shell, navigation, `src/App.tsx`, `backend/main.py`, or
`SqlEditor.tsx` change is required.

## Validation

- Production TypeScript/Vite build: passed
- Targeted changed-file ESLint: passed
- Included backend Python compilation: passed
- Pure deterministic backend risk/matching checks: 6 passed
- Archive exclusion and integrity verification: required before release

The packaging runtime did not contain FastAPI or pytest, so HTTP router tests
were not executed here.

## Preserved decisions and assumptions

- ERP access remains read-only.
- The original PDF, OCR evidence, original allocations, and reviewer authority
  remain preserved.
- Exact ERP invoice ownership has priority over OCR identity fields.
- OCR identity remains the working evidence only when ERP invoice validation
  cannot resolve a customer.
- ERP invoices contain exactly 9 or 10 digits.
- `9999999999` remains the controlled no-remittance placeholder and is never
  treated as ERP invoice evidence.
- Existing confidence thresholds and approval authority were not changed.

## Verification for Josh

1. Select `7.29.26P.pdf` from the existing-job list and confirm the saved
   review opens without running OCR again, even if its generic status says
   `uploaded`.
2. Open a transaction with a visible 9- or 10-digit invoice and confirm ERP
   validation starts automatically.
3. Confirm the verified customer number, name, phone, street, city, state, and
   ZIP replace OCR identity values.
4. Confirm `SPENCERVILLE, IN` appears as City `SPENCERVILLE` and State `IN`,
   not as Address Line 2, and ZIP `46788-` displays as `46788`.
5. Confirm invalid 8- or 11-digit OCR values are highlighted and not sent to
   ERP matching.
6. Confirm the review scrollbars are clearly visible at normal browser zoom.
