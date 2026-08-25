# Agent 4 Independent Baseline Audit

Audit date: 2026-08-05

Role: independent verification and integration gate

Baseline commit: `10075b683d59ac8fc8292f350577fe316f7a8353`

Source archive: `ETOP-Cloud-Development-20260805-232339.zip`

Source archive SHA-256: `f74756f394e691c08336080920f8e41ceb7b878319280ce74d71d3edcdc60f21`

The baseline commit is the uploaded Increment 4B project after 19 tracked operational Lockbox result/versioned-extraction JSON files were removed from the agent mirror. No application, governance, or Lockbox logic was changed during this audit.

## Executive result

Increment 4B's retained privacy-safe Lockbox boundary passes in this container: all 15 Python verifiers and all 11 browser/runtime verifiers pass. The frontend production build also passes. The baseline is not yet a reproducible integrated release because the Python dependency declaration is incomplete, Report Builder calls two nonexistent backend routes, and multiple stale duplicate source/package trees remain tracked. The initial sanitized mirror accidentally omitted the safe `backend/data/database.py` source together with local data; integration restored the exact uploaded source file after byte-level verification.

## Baseline command evidence

| Check | Command | Result |
|---|---|---|
| Git identity | `git rev-parse HEAD` | PASS — exact `10075b683d59ac8fc8292f350577fe316f7a8353` |
| Frontend dependencies | `NPM_CONFIG_CACHE=/tmp/etop-agent4-npm-cache npm ci` | PASS. The default `/root/.npm` cache is not writable in this container, so a task-local cache was required. |
| Production build | `npm run build` | PASS — TypeScript/Vite built 106 modules; output JS 539.95 kB. Existing Vite warning: the main chunk exceeds 500 kB. |
| Baseline lint | `npm run lint` | FAIL — 177 parser errors because `eslint .` traverses both the root TypeScript project and tracked `backend/src` without a unique `tsconfigRootDir`. |
| Root-only lint isolation | Run the same ESLint config against a temporary root-only source copy | FAIL — exactly 14 existing errors: 6 in `SqlWorkspace.tsx`, 3 in `DocumentViewer.tsx`, and 1 each in `client.ts`, `EnterpriseDataGrid.tsx`, `DatabaseExplorer.tsx`, `AIStudio.tsx`, and `useLearningData.ts`. |
| Backend discovery | `python -m unittest discover -s backend -p 'test_*.py' -v` | CONSTRAINED — 187 discovered: 181 passed and 6 import errors caused by missing FastAPI in this container. No executed test failed. |
| Python Lockbox gate | `for f in verification/verify-lockbox-*.py; do python "$f"; done` | PASS — 15/15. |
| Browser/runtime Lockbox gate | `for f in verification/verify-lockbox-*.mjs; do node "$f"; done` | PASS — 11/11. |
| Privacy extension scan | Search outside `.git`/`node_modules` for PDF, DB, SQLite, XLS/XLSX, CSV, logs, `.env`, certificates, and private keys | REVIEW — only `data/modules/document_intelligence/document_intelligence.db` remains in the sanitized worktree; it is ignored/untracked, 24,576 bytes, and has two empty business tables. It is excluded from the release payload. |

The six Python import errors are `_FailedTest.etop_platform`, `_FailedTest.modules.customer_360`, `_FailedTest.modules.document_intelligence`, `test_etop_platform_search`, `test_fastapi_lifecycle`, and `test_lockbox_control_projection`. The environment lacks FastAPI, pytest, httpx, SQLAlchemy, mysql-connector, and pytesseract. `backend/requirements-phase3.txt` declares only pytesseract and Pillow even though the application imports FastAPI, mysql-connector, python-dotenv, requests, pypdf, python-docx, openpyxl, and reportlab.

## Module status matrix

| Module | Status | Concrete evidence | Release consequence |
|---|---|---|---|
| Customer Intelligence | **Incomplete** | `src/features/customer360/Customer360.tsx` uses the real `/api/v1/customers` search/summary path and includes exact currently-open 8/9-digit invoice ownership lookup. The Documents, Notes, and Relationships tabs explicitly render a “workspace shell” for a future repository; generated recommendation buttons have no action handler. | Keep search, summary, credit, aging, sales, and activity as demonstrable. Hide or clearly defer the three shell tabs and nonfunctional recommendation actions. Frontend health/recommendation scoring also needs governed ownership before it can drive decisions. |
| Priority Review | **Working, governance-blocked** | `backend/customer_risk.py` executes live read-only Madden queries. `backend/customer_risk_service.py` hardcodes thresholds, weights, labels, score formula, and tie ordering for Critical/High/Elevated priority. | Technically functional, but the Agent Operating Contract reserves the definition, weights, and tie-breaking of “high risk” for Product Owner approval. Do not promote the current numbers as approved policy without that decision record. |
| Lockbox | **Working** | Production build passes; 181 executed backend tests pass; 15 Python and 11 browser/runtime 4B verifiers pass. The gate covers the 8/9-digit invoice contract, PNC site compatibility, invoice-versus-PO disambiguation, residuals, signed credits, distinct current service charges, invoice customer search, source-backed decisions, and governed review UI. | Protect as a no-regression boundary. Real OCR/customer-ERP integration and operational batch counts cannot be reproduced in the sanitized agent mirror and must still be checked on the installed workstation. |
| Reporting | **Broken** | `src/components/ReportBuilder/ReportBuilder.tsx` POSTs to `/api/v1/reports/execute` and `/api/v1/reports/export`. `backend/modules/reports/api.py` exposes only list/get/create/update/delete routes; no execute or export backend route exists. | Create/save/catalog may work if the database layer is present, but the required Save → Run → Preview → Export flow cannot complete. Scheduling a report is therefore not a verified end-to-end workflow. |
| Automation Center | **Incomplete** | Backend code contains CRUD, execution history, a 30-second scheduler, daily/weekly/monthly timezone scheduling, read-only SQL/report/script execution, CSV/XLSX/PDF generation, and folder/Outlook delivery. The uploaded SQLite schema source is present after the integration sanitization correction, but no retained scheduler/API/service tests exist. Schema/UI accept `custom`, while `calculate_next_run` raises “Custom cron schedules are not enabled yet.” | Substantial implementation exists, but runtime/persistence/scheduling are not independently reproduced at baseline. Disable or remove Custom until implemented, and add deterministic scheduler, timezone, restart, delivery, and failure-state tests before release claims. |
| SQL Studio | **Working with limitations** | `backend/sql_workspace.py`, `backend/core/sql_validator.py`, and the shared read-only database layer implement validate/execute/export/saved/history flows; SQL AI is local-Ollama based. Production build passes. The active SQL UI accounts for 7 of the 14 root-only lint errors, and no direct SQL Studio regression suite was found. | Demonstrable as a read-only tool after live database verification. Resolve active lint issues and add validator/execution/export tests. Current query limits should be confirmed against the Product Owner's expected 100,000-row/timeout behavior. |
| AI / SOP Search | **Incomplete / environment-dependent** | `backend/main.py` includes knowledge status, reindex, search, and chat routes using local documents, SQLite vector storage, and local Ollama with source citations. The sanitized mirror contains neither the runtime knowledge store/documents nor a reproducible dependency declaration, and Ollama is unavailable here. | The code path is real but cannot be installed or verified from this package alone. Treat local model/documents as explicit deployment prerequisites and retain fail-closed/cited behavior. |
| Document Intelligence | **Incomplete** | Generic document upload/job/process/result/review/learning routes exist, and Lockbox is a proven sub-capability. `TemplateStudio.tsx` says backend integration is planned; `TrainingStudio.tsx` says its backend phase will store profiles; `APDashboard.tsx` presents a future foundation; `AIStudio.tsx` contains planned datasets and a disabled replay foundation. | Demonstrate Lockbox and any verified generic intake/review paths only. Hide or label unfinished Template, Training, AP, and AI surfaces; browser-only training profiles are not durable enterprise state. |
| Platform Center | **Duplicated and incomplete** | The active `src/platform/PlatformCenter.tsx` performs federated search, but notifications/tasks/timeline come from static defaults persisted only in localStorage. A second implementation exists at `src/platform/components/PlatformCenter.tsx` with a second store at `src/platform/services/platformStore.ts`. | Search can be retained after integration tests. Static synthetic tasks/notifications/timeline violate the no-decorative-functionality rule and should not be presented as enterprise records. Consolidate to one implementation and durable authority. |

## Release blockers and risks

### Blockers

1. **Report execution/export routes are absent.** The active frontend calls `/api/v1/reports/execute` and `/api/v1/reports/export`, but the backend exposes neither route.
2. **Python dependencies are not reproducible.** The only requirements file covers OCR phase dependencies, not the application runtime and test stack.

### High risks

1. **Operational data entered the uploaded source ZIP.** Baseline commit `10075b6` removes 19 tracked files and 293,061 lines from `backend/modules/document_intelligence/lockbox_results`, including versioned extractions. Those deletions must be preserved. The maintained ZIP sanitizers now exclude directory names `lockbox_results`/`lockbox_exports` and DB/PDF/etc. extensions, but any ad hoc ZIP workflow must use an equally broad recursive denylist.
2. **Duplicate frontend project:** 100 files are paired between `src` and `backend/src`; 78 are byte-identical and 22 are divergent. Eight current root files have no `backend/src` counterpart. This causes the baseline lint parser failure and makes stale overwrite/package selection likely.
3. **Duplicate backend root:** `backend/backend` contains 18 duplicate top-level Python files; `main.py`, `customer_match.py`, `customer_match_service.py`, and `test_customer_match_service.py` have diverged from the active backend root.
4. **Conflicting integration records:** root `INTEGRATION_MANIFEST.md` is the current 4B record (1,176 lines), while `backend/INTEGRATION_MANIFEST.md` is a different July 30 manifest (142 lines).
5. **Stale overlay payload:** all 17 `sprint4a_payload` files already exist in the working tree; nine differ from their active targets, including Platform Center and platform routing. It is a latent stale-overwrite source.
6. **Priority Review policy lineage is absent.** Hardcoded risk thresholds/weights/tie rules conflict with the explicit Product Owner decision boundary unless separately approved.

### Lower risks / observations

- The ignored/untracked `data/modules/document_intelligence/document_intelligence.db` worktree file has two empty business tables (`customer_payment_behavior` and `payer_customer_mapping`). It is not part of the release; a source-controlled schema/migration is preferable to shipping a mutable SQLite file.
- The main frontend bundle is already above Vite's 500 kB warning threshold.
- Runtime/test dependencies should be version-pinned and split into application, OCR, and development/test sets.

## Shared-file integration hotspots

The 22 divergent frontend mirrors are:

`App.tsx`, `DesktopShell.css`, `api/customers.ts`, `components/ReportBuilder/ReportBuilder.css`, `components/ReportBuilder/ReportBuilder.tsx`, `features/customer360/Customer360.tsx`, `features/customer360/types.ts`, `features/enterprise-dashboard/EnterpriseDashboard.css`, `features/enterprise-dashboard/EnterpriseDashboard.tsx`, `modules/document-intelligence/DocumentIntelligence.css`, `modules/document-intelligence/DocumentIntelligence.tsx`, `modules/document-intelligence/api.ts`, `modules/document-intelligence/components/LockboxAutomationCenter.tsx`, `modules/document-intelligence/components/LockboxReviewWorkspace.tsx`, `modules/document-intelligence/components/lockboxRecommendation.ts`, `modules/document-intelligence/hooks/useDocumentData.ts`, `modules/document-intelligence/types.ts`, `platform/PlatformCenter.css`, `platform/PlatformCenter.tsx`, `platform/registry.ts`, `platform/registry/modules.ts`, and `platform/search.ts`.

Eight current root-only frontend files are the SQL editor and seven Lockbox preparation/allocation helpers. These are especially vulnerable if a package or merge accidentally promotes `backend/src` as authoritative.

## Protected Increment 4B regression gate

Run this gate after all agents are integrated and before packaging:

```bash
NPM_CONFIG_CACHE=/tmp/etop-release-npm-cache npm ci
npm run build
npm run lint
python -m unittest discover -s backend -p 'test_*.py' -v
for verifier in verification/verify-lockbox-*.py; do
  python "$verifier"
done
for verifier in verification/verify-lockbox-*.mjs; do
  node "$verifier"
done
```

Acceptance criteria:

- Production build remains successful.
- Lint introduces no new errors. After the integration ESLint boundary correction, the known root debt is exactly 14 errors; the release target should be zero or an explicitly governed unchanged debt count.
- In this container, no executed backend test regresses from 181 passed; the six FastAPI import errors must remain classified as environment-only until dependencies are installed. In the complete 4B runtime used to seal Increment 4B, rerun the documented 224/224 backend boundary.
- All 15 Python and 11 browser/runtime Lockbox verifiers pass.
- No change admits 10-digit invoices, allows POs into allocation, relaxes current-open customer ownership, reuses a service-charge identity, bypasses human approval, changes posting/export authority, or writes to Madden/ERP.
- Run package privacy scans after archive creation, not only against the working tree. No operational PDF, extraction/result JSON, database, export, credential, log, cache, or customer/check evidence may be present.
- On the installed workstation, rerun real database/Ollama/PNC OCR integration checks separately; sanitized CI cannot substitute for those system-of-record boundaries.

## Independent disposition

The baseline is a valid source for controlled integration only after preserving the Lockbox privacy deletion and restoring the exact safe database-schema source accidentally omitted by the broad sanitizer. It is not yet release-ready. Integration must correct the absent Reporting execute/export contract, make dependency limitations explicit, and avoid merging from any stale mirror/payload tree. Increment 4B's 26 retained Lockbox verifiers are the protected floor for every subsequent candidate.
