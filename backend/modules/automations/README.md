# ETOP Automation Service Implementation

This package is the existing backend implementation of `PSS-006 — Automation
Service`. It supports local manual and scheduled report, read-only SQL,
PowerShell, and Python runs. It does not grant business authority, write to the
ERP, or make custom cron schedules available.

## Governed runtime behavior

- Active definitions are validated before persistence. Scheduled times,
  Sunday-first weekday values, monthly dates, IANA timezones, script files,
  saved-report bindings, and email-recipient requirements fail explicitly.
- Common Windows timezone names are normalized to IANA names. The `tzdata`
  dependency supplies the timezone database on Windows.
- Due timestamps are compared as absolute instants rather than as ISO text, so
  UTC offsets and daylight-saving changes do not reorder schedules.
- A durable `running` execution row is the cross-thread/process execution
  claim. A second claim for the same automation is rejected.
- A backend restart marks an unfinished run failed and places its automation in
  `error`. It is not replayed automatically because a script or delivery may
  already have produced a partial external effect.
- A runtime failure also places the definition in `error` and clears its next
  schedule. An operator must review the execution and explicitly reactivate or
  retry it.
- Editing, deleting, or clearing history is rejected while a durable execution
  is running.
- `/api/v1/automations/health` exposes service, scheduler, definition,
  validation, running, recovery, quarantine, and failure state without
  exposing credentials.

## Boundaries and current gaps

- `manual`, `daily`, `weekly`, and `monthly` schedules are implemented.
  `custom`/cron remains unavailable and cannot be activated.
- Restart recovery is fail-closed rather than automatic retry. ETOP cannot
  prove whether an arbitrary external script is idempotent, so the operator
  owns the retry decision.
- The current database schema does not retain a structured immutable
  definition version or authority grant on each run. Adding those PSS-006
  contracts requires a governed database migration and integration-owner
  review.
- Idle definitions and completed history still use the existing hard-delete
  endpoints. A governed retention period and retire/archive command have not
  been approved, so this increment prevents deletion only while work is
  running and records the broader retention behavior as unresolved.
- Cancellation, credentials, approval grants, adapter allowlists, and
  compensating actions remain outside this increment. No UI should represent
  those commands as available.

## Verification

Run the standard-library regression suite from the project root:

```text
python -m unittest -v backend.test_automation_service_governance
```

The tests use an isolated temporary SQLite database and contain no operational
data.
