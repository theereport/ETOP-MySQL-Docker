# ETOP Launcher

The ETOP Launcher starts and monitors the local Enterprise Tire Operating
Platform development environment running out of `D:\ETOP`.

## Included

- `ETOP_Launcher.pyw` — desktop launcher application
- `Start_ETOP_Launcher.bat` — starts the launcher without requiring PowerShell
- `Run_ETOP_Launcher_Debug.bat` — starts the launcher with a visible console for troubleshooting
- `Create_Desktop_Shortcut.ps1` — creates an ETOP Launcher shortcut on the desktop

## Installation

This folder already lives at:

`D:\ETOP\ETOP-Launcher`

Double-click `Start_ETOP_Launcher.bat` to run it directly, or create a desktop
shortcut by right-clicking PowerShell and running:

```powershell
powershell.exe -ExecutionPolicy Bypass -File "D:\ETOP\ETOP-Launcher\Create_Desktop_Shortcut.ps1"
```

## What the launcher starts

### Backend

Working folder:

`D:\ETOP\backend`

Command:

```text
.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

### Frontend

Working folder:

`D:\ETOP`

Command:

```text
npm.cmd run dev -- --host 127.0.0.1 --port 5173
```

## Status checks

The launcher checks:

- Frontend: `http://127.0.0.1:5173/`
- Backend/API readiness: `http://127.0.0.1:8000/health`
- MaddenCo/MySQL readiness: derived from the launcher-safe `/health` response
- Ollama: `http://127.0.0.1:11434/api/tags`
- Knowledge-base readiness: derived from the launcher-safe `/health` response

Protected application routes such as `/api/v1/modules`, `/sql/connection`, and
`/knowledge/status` remain authenticated and are not used as launcher probes.

## Behavior

- **Start All** starts backend and frontend.
- **Stop All** stops only services started by this launcher.
- **Restart** stops and starts the managed services.
- **Open ETOP** opens the frontend.
- **ETOP Dev** opens a secondary dev instance at `http://127.0.0.1:5174/`
  (frontend) and `http://127.0.0.1:8001/docs` (backend). This launcher does
  not start or health-check that instance - it must already be running
  separately (e.g. a second checkout or branch) for the button to show
  anything.
- **API Docs** opens FastAPI Swagger documentation.
- The launcher can optionally start `ollama serve` when Ollama is unavailable.
- ETOP opens automatically once the frontend responds.

## Port allocation across ETOP instances

To avoid the port collisions this launcher used to run into with other local
ETOP checkouts:

| Instance | Frontend | Backend/API |
| --- | --- | --- |
| `D:\ETOP` (this launcher, main) | 5173 | 8000 |
| `D:\ETOP` dev/secondary instance | 5174 | 8001 |
| `C:\Users\Josh.Corbit\vite-project` (old) | 5175 | 8003 |

## Requirements

The launcher itself uses only Python's standard library. No new Python packages
are required.

The ETOP project must still contain:

- `package.json`
- `backend\main.py`
- `backend\.venv\Scripts\python.exe`

All three already exist at `D:\ETOP`.

## Troubleshooting

If the project moves, update the Project folder field inside the launcher.

If the launcher cannot find Python, edit `Start_ETOP_Launcher.bat` and update
the `PYTHONW_EXE` and `PYTHON_EXE` paths.
