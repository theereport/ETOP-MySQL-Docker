# ETOP 0.7.0 Wave 2 Increment 4C Release Status

Release date: 2026-08-06  
Baseline: exact installed Increment 4B lineage  
Release type: controlled source overlay with exact preflight, rollback, and
privacy-safe verification

## Outcome

Increment 4C converts two visibly present but incomplete workspaces into
bounded operational workflows:

1. Report Builder now completes persisted catalog, design, validation, save,
   read-only preview, capped CSV export, and non-parameterized recurring
   schedule work against ETOP's real APIs.
2. Automation Service now validates definitions, calculates schedules with
   timezone and weekday consistency, claims runs durably, fails closed after
   interruption/failure, quarantines invalid legacy definitions, and exposes
   health/diagnostic state.

No Lockbox rule, customer authority, allocation, approval, posting, export
authority, or ERP-write behavior changed.

## Module status after 4C

| Module/capability | Status | Demonstrable boundary | Remaining gap |
| --- | --- | --- | --- |
| Lockbox | Working / protected | Upload/process, governed preparation, transaction review, current-open invoice customer search, explicit approval, reviewed export, training evidence; all retained privacy-safe verifiers. | Real workstation OCR/ERP evidence and operational batch counts must be checked locally; no automated approval or ERP write. |
| Report Builder | Working with limits | Persisted catalog/CRUD, definition validation, parameters, read-only preview, capped CSV export, saved non-parameterized schedules. | Direct XLSX and parameterized schedules unavailable; no dedicated governed Reporting CAP/PSS artifact yet. |
| Automation Center/Service | Working with governed limits | Local CRUD/history, validation, manual/daily/weekly/monthly schedules, durable single-run claim, recovery/quarantine, CSV/XLSX/PDF generation, health. | Custom cron, cancellation, automatic replay, immutable definition-version/authority, adapter allowlists, retention/archive, and compensating actions unresolved. Script and email/folder actions remain blocked unless explicitly delegated by the Product Owner. |
| SQL Studio | Working with limitations | Read-only validate/execute/export, saved queries/history, local SQL assistance boundary. | Existing lint debt and no retained end-to-end SQL regression suite; row limits require Product Owner confirmation. |
| Customer Intelligence | Partial | Customer/invoice search, summary, credit, aging, sales, activity, and current-open ownership lookup. | Documents/Notes/Relationships shells and nonfunctional recommendation actions remain; scoring ownership is unresolved. |
| Priority Review | Technically working / governance-blocked | Read-only ranked customer queue and account evidence. | Current hardcoded thresholds, weights, labels, and tie ordering are not approved policy in this release. |
| Document Intelligence | Partial | Lockbox is proven; generic upload/job/process/result/review/learning routes exist. | Template, Training, AP, and broader AI surfaces contain planned/browser-only foundations and must not be presented as durable completion. |
| AI Assistant / SOP Search | Dependency-bound | Real local Ollama and indexed-document routes with sources exist. | Local models, documents, vector store, and complete pinned dependencies are deployment prerequisites and were unavailable in sanitized verification. |
| Platform Center | Partial / duplicated | Federated search and browser-local tasks/notifications/timeline. | Duplicate implementation/store and synthetic local-only records require consolidation and durable authority. |
| Project Tracker | Unavailable | Navigation already marks the module Coming Soon. | No operational workflow in this release. |

## Completed improvement register

| Priority | Improvement | Result |
| ---: | --- | --- |
| 1 | Repair Report Builder execution/export contract | Completed with existing `/sql/execute` and `/sql/export`; nonexistent report routes removed from the active workflow. |
| 1 | Complete Save → Run → Preview → Export → Schedule flow | Completed for persisted, non-parameterized saved reports and capped direct CSV, including abort/generation protection against stale in-flight previews. |
| 1 | Make unsupported reporting capabilities explicit | Completed for direct XLSX, parameterized schedules, and server row cap. |
| 1 | Validate Automation before activation/execution | Completed for core schedule/source/report/script/delivery evidence. |
| 1 | Prevent duplicate/interrupted Automation replay | Durable claim and fail-closed recovery completed; retry/reactivation remains operator-owned. |
| 1 | Correct timezone/weekday/due ordering | Completed with timezone normalization, Sunday-first mapping, and UTC-instant comparisons. |
| 2 | Expose Automation health and quarantine | Completed through definition health plus scheduler/recovery diagnostics. |
| 2 | Restore active-source lint boundary | Completed; 177 duplicate-tree parser failures removed while 14 known active-source errors remain visible. |
| 2 | Protect operational data from agent/release artifacts | Completed for this release; no operational Lockbox JSON, PDF, DB, export, credential, or cache enters the overlay. |

## Deferred improvement register

| Priority | Deferred item | Why it is deferred |
| ---: | --- | --- |
| 1 | Approve or replace Priority Review policy | Thresholds/weights/tie rules require Product Owner and governance authority. |
| 1 | Complete Python dependency manifest | Versions must be derived from the accepted workstation runtime, not guessed in an overlay. |
| 1 | Workstation integration verification | Real Madden, Ollama, OCR, Outlook, filesystem delivery, and Windows PowerShell are unavailable in sanitized CI. |
| 2 | Reporting governance artifact | Blueprint has no dedicated governed Reporting CAP/PSS record yet. |
| 2 | Automation authority/version/retention contracts | Requires schema migration and governance decisions. |
| 2 | Consolidate duplicate/stale source trees | Broad deletion carries overwrite risk and needs a separate reviewed cleanup increment. |
| 2 | Resolve 14 active-source lint errors | Existing debt is isolated and unchanged; no broad unrelated rewrite in 4C. |
| 3 | Frontend code splitting | Production build passes but retains the existing >500 kB main-chunk warning. |

## Verification boundary

- Report workflow deterministic verifier: passed.
- Automation Service focused standard-library tests: 12 passed.
- Changed TypeScript/JavaScript targeted lint: passed with zero errors/warnings.
- Production TypeScript/Vite build: passed, 108 modules; main JavaScript bundle
  556.11 kB with the existing >500 kB warning.
- Retained privacy-safe Lockbox gates: 15 Python and 11 browser/runtime
  verifiers passed before packaging.
- Full backend discovery: 199 discovered, 193 passed, and the same six
  environment-only FastAPI import errors as baseline; no executed test failed.
- Full active-source lint: exactly 14 pre-existing errors, with no error in a
  changed runtime path. The prior 177 duplicate-tree parser failures are gone.
- The full accepted workstation backend boundary must still be rerun by the
  included verifier because sanitized CI does not contain the installed
  FastAPI/runtime environment.

## Demonstration sequence

1. Open Report Builder, create or select a report, and save the definition.
2. Enter any required parameter values and run a read-only preview.
3. Download the controlled CSV and show the live server row-cap message.
4. On a saved report without parameters, create a recurring CSV/XLSX schedule.
5. Open Automation Center to show the same persisted schedule, next run, and
   history/health state.
6. Show Lockbox separately as the protected production-proof workflow; do not
   imply that 4C changed its accounting decisions or authority.

## Installation and rollback posture

The 4C package installs only over recognized Increment 4B hashes, stops if the
backend is running, verifies every payload hash/path, creates an exact rollback
snapshot, copies only listed paths, and verifies installed bytes. Rollback
requires the installed 4C hashes, restores every replaced path byte-for-byte,
and removes only paths explicitly created by 4C. Runtime databases and
operational state are not part of source rollback.
