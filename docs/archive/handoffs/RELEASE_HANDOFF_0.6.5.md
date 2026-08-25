# ETOP 0.6.5 Release Handoff

## Baseline

- Source: `ETOP-Integrated-Agent-1-4-Current-20260730-0.6.4.zip`
- Source SHA-256:
  `140f0eda50e1df749c4139daeb940e984e82838843a84b2c30004b078bd4a418`
- Governing artifacts: Complete Blueprint and Agent Operating Contract

## Purpose and completed workflow

This targeted release moves ERP and allocation analysis ahead of the Lockbox
Review workspace:

`Select transaction → validate 9- or 10-digit remittance invoice → resolve ERP
customer → hydrate authoritative customer master → retrieve open invoices →
rerun allocation analysis with the resolved customer → open review → human
accepts, corrects, or defers`

The preparation step does not approve, save, post, or automatically apply the
recommendation.

## Changed files

- `CHANGELOG.md`
- `INTEGRATION_MANIFEST.md`
- `INSTALL_INTEGRATED_RELEASE.md`
- `Install-ETOP-Integrated-Release.ps1`
- `RELEASE_HANDOFF_0.6.5.md`
- `src/modules/document-intelligence/DocumentIntelligence.css`
- `src/modules/document-intelligence/components/LockboxAutomationCenter.tsx`
- `src/modules/document-intelligence/components/LockboxReviewWorkspace.tsx`
- `src/modules/document-intelligence/components/lockboxPreparation.ts`
- `src/modules/document-intelligence/components/lockboxRecommendation.ts`

No shared shell, navigation, `src/App.tsx`, backend route, `backend/main.py`, or
`SqlEditor.tsx` change is required.

## Validation

- Production TypeScript/Vite build: passed, 88 modules transformed
- Targeted changed-file ESLint: passed
- The intentionally excluded `SqlEditor.tsx` was represented by a temporary
  build-only compatibility stub; the stub was removed before packaging
- Archive exclusion, merge-marker, and integrity verification: required before
  release

## Preserved decisions and assumptions

- ERP access remains read-only.
- OCR is evidence; verified ERP customer-master data remains authoritative for
  customer identity.
- ERP invoices contain exactly 9 or 10 digits.
- `9999999999` remains the controlled no-remittance placeholder and is never
  treated as ERP invoice evidence.
- A prepared recommendation remains separate from the reviewer decision.
- No allocation is silently applied and no transaction is silently approved.
- Existing confidence thresholds, balancing tolerance, and approval authority
  were not changed.
- Preparation results are reused only for the active lockbox session. Saving a
  review invalidates the cached preparation so a later entry uses current
  evidence.

## Verification for Josh

1. Open a processed lockbox and click **Prepare & Open Review Workspace**.
2. Confirm the button displays **Preparing ERP Match & Allocations** before the
   review workspace opens.
3. For a visible 9- or 10-digit remittance invoice, confirm the review opens
   with the ERP customer number, name, phone, street, city, state, and ZIP
   already populated.
4. Confirm the first visible Cash Application result is the final
   customer-resolved recommendation, rather than a temporary
   `No Invoice Match` result.
5. Confirm **Invoice Allocation Detail** shows invoice, open amount, suggested
   apply amount, aging, and confidence in a taller table.
6. Click **Expand Allocation Detail** and confirm the allocation view becomes
   near full screen without changing browser zoom.
7. Select another transaction from the left queue and confirm it displays
   `preparing` before the visible review changes.
8. Confirm **Apply Recommendation** remains a human action and that no approval
   or ERP posting occurs automatically.
