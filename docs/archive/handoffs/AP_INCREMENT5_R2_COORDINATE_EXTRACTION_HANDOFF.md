# AP Increment 5 R2 Coordinate-Aware Invoice Extraction Handoff

**Release:** ETOP 0.7.0 AP Increment 5 R2  
**Date:** August 9, 2026  
**Protected predecessor:** Exact AP Increment 5 R1 final  
**Source records:** SRC-009; SRC-011  
**Decision:** ADR-016 v0.3

## Outcome

R2 corrects vendor invoices whose native PDF text stores labels and values as
separate positioned fragments. It adds field-specific coordinate pairing,
remittance issuer inference, recipient/customer exclusions, totals-box
interpretation, blank-label protection, corroborating observations, and honest
native-text/OCR/field-readiness status.

The correction does not import or reprocess any invoice during installation.
Every prior original, hash, processing run, review, correction, and AP evidence
revision remains unchanged.

## Governed release identity

- ZIP: `ETOP-0.7.0-AP5-R2-Coordinate-Aware-Invoice-Extraction-20260809.zip`
- Helper: `ETOP-Run-AP5-R2-Coordinate-Aware-Invoice-Extraction.ps1`
- Install source state: exact `R1Final` only
- Idempotent state: exact `AP5R2Final` only
- Rollback target: exact `R1Final` only
- Snapshot root: sibling `<project-name>.etop-rollback` directory

The helper pins the exact ZIP name and SHA-256, validates the archive before
extraction, and invokes Windows PowerShell 5.1. The installer stops when the
project is not the exact protected predecessor, when ETOP ports are active, or
when any package/source/operational integrity gate fails.

## Installation

1. Place the ZIP and helper together in your Windows `Downloads` directory.
2. Stop ETOP frontend and backend processes.
3. From Windows PowerShell 5.1, run
   `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\ETOP-Run-AP5-R2-Coordinate-Aware-Invoice-Extraction.ps1`.
   Pass `-ProjectRoot` only when the canonical existing ETOP project is not
   `%USERPROFILE%\vite-project`.
4. Retain the exact snapshot path and rollback command printed by the installer.

An exact R2 rerun copies no source files; it repeats integrity and isolated
verification only.

## Post-install professional UAT

1. Start ETOP normally and open **Vendor Invoice Dataset & OCR**.
2. Select the preserved UAT invoice; do not upload a duplicate.
3. Choose **Append reprocess run**.
4. Confirm the new run reports processor v3, parser 2.0.0/rules v2, extraction
   v2, **Native PDF text**, and **OCR not needed**.
5. Confirm thirteen-field coverage and the three-key-field readiness message.
   A blank purchase-order label must remain without value, recipient/customer
   text must not become vendor identity/number, and an inferred remittance
   issuer must remain marked analytical and reviewable.
6. Compare every candidate field to the PDF. Correct a value or explicitly
   **Mark unavailable** when the source does not support it, record reviewer and
   notes, and save **Extraction evidence reviewed** only after completing that
   comparison.
7. Synchronize the exact reviewed current extraction only if it is appropriate
   for the AP evidence projection.

The previous failed/partial parser run and its prior review remain retrievable.
Review of the previous run never authorizes synchronization of the new run.

## Recovery

Use only the explicit R2 snapshot and rollback command printed by this install.
Rollback validates the snapshot release identity, manifest, individual backup
hashes, and exact current R2 state before changing source. It removes only
R2-new source paths, restores R1 predecessor bytes atomically, verifies exact
`R1Final`, and leaves runtime evidence untouched.

Never choose a snapshot by recency and never use an earlier R1 recovery snapshot
as the R2 rollback source.

## Explicit boundaries

- No database, upload, PDF/image, extraction JSON, review, export, credential,
  environment file, operational Lockbox output, or ERP/GL state is packaged.
- No backend module is imported against the live project by the installer or
  verifier.
- No external AI/OCR service receives a document.
- No vendor master, match, coding, approval, payment, posting, export, ERP write,
  straight-through threshold, or financial authority is created.
