# Agent 4 — Customer Risk Review

## Outcome

Selecting **Review customers above credit thresholds** on the dashboard now
opens Customer Intelligence in a live priority-review mode. The left panel is
filled with the highest-risk customers first, and the top account opens
automatically.

## Review criteria

The live queue includes customers with:

- credit utilization at or above 75%; or
- a balance in the 60-, 90-, or 120-day aging buckets.

Priority is calculated deterministically from credit utilization, past-due
concentration, and severe aging. The local AI does not decide which customers
are included or how they are ranked.

## Files changed

- `src/App.tsx`
- `src/features/enterprise-dashboard/EnterpriseDashboard.tsx`
- `src/features/customer360/Customer360.tsx`
- `src/features/customer360/Customer360.css`
- `src/features/customer360/types.ts`
- `src/features/customer360/api.ts`
- `src/api/customers.ts`
- `backend/main.py`
- `backend/customer_risk.py`
- `backend/customer_risk_service.py`
- `backend/test_customer_risk_service.py`

## Run

Restart the backend so the new route is registered:

```powershell
cd C:\Users\Josh.Corbit\vite-project\backend
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

Start the frontend:

```powershell
cd C:\Users\Josh.Corbit\vite-project
npm.cmd run dev -- --host 127.0.0.1
```

The priority queue uses the Madden connection already configured for Customer
Intelligence. If that database server is unreachable, ETOP will show the
connection error instead of substituting sample customers.
