# ETOP Sprint 4A — Platform Core (v0.6)

This is an additive patch for the current ETOP React/Vite + FastAPI project.

## Includes

- Global enterprise search overlay
- Platform Registry v2
- Shared intelligence UI primitives
- Universal entity workspace shell
- Compatible `PlatformCenter`, notifications, tasks, and timeline exports
- FastAPI platform-core endpoints
- Safe installer that backs up files before copying

## Install

Open PowerShell:

```powershell
cd C:\Users\Josh.Corbit\vite-project
powershell.exe -ExecutionPolicy Bypass -File ".\install_sprint4a.ps1"
```

Then verify:

```powershell
npm.cmd run build
cd backend
.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

Frontend:

```powershell
cd C:\Users\Josh.Corbit\vite-project
npm.cmd run dev -- --host 127.0.0.1
```

Platform API checks:

- http://127.0.0.1:8000/api/v1/platform/health
- http://127.0.0.1:8000/api/v1/platform/registry
- http://127.0.0.1:8000/api/v1/platform/search?q=customer

## Rollback

The installer creates:

```text
.sprint4a-backup\<timestamp>\
```

Restore the backed-up files if needed.
