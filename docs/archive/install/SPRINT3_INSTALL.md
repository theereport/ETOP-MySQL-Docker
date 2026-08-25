# ETOP Sprint 3 Installation

Merge the package into the root of the current `vite-project`.

## Verify frontend

```powershell
cd C:\Users\Josh.Corbit\vite-project
npm.cmd install
npm.cmd run build
```

## Verify backend

```powershell
cd C:\Users\Josh.Corbit\vite-project\backend
.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

Open `http://127.0.0.1:8000/api/v1/platform/health` to verify the new platform API.

## New controls
- `Ctrl+K`: Enterprise Search
- Circular arrow: Enterprise Timeline
- Check mark: My Tasks
- Diamond/bell control: Notifications

Tasks and notification read status are initially stored in browser local storage.
