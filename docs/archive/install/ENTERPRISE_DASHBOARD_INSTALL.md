# ETOP Enterprise Dashboard — Sprint 1

This package replaces the original marketing-style home page with an operational Enterprise Command Center.

## Included

- Live local-platform status using the existing knowledge status state
- Quick actions into Customer Intelligence, SQL Studio, Reports, Automation, and AI
- Enterprise capability health cards
- ETOP AI morning brief panel
- Needs-attention work queue
- Recent platform activity timeline
- Core workspace launch center
- Responsive desktop/tablet layout

## Installation

Copy the contents of this package into:

```text
C:\Users\Josh.Corbit\vite-project
```

Allow Windows to merge folders and replace `src\App.tsx` when prompted.

Then run:

```powershell
cd C:\Users\Josh.Corbit\vite-project
npm.cmd run build
```

Start the application using your normal backend and frontend launchers.

## Important data note

The dashboard's system counts are live from the existing knowledge endpoints. The work queue, enterprise health descriptions, and recent platform activity are intentional Sprint 1 configured content—not yet database-driven operational metrics.

Sprint 2 can add a backend `/api/v1/dashboard/summary` endpoint for live credit, collections, sales, report execution, and automation alert metrics.
