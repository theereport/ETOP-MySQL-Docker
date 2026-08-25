# ETOP Customer Intelligence – Sprint 1

## Included
- Customer Intelligence workspace replacing the existing Customer 360 screen
- Explainable deterministic Health Score
- Transparent recommendation rules
- Financial and sales tabs
- Unified activity timeline shell
- Documents, Notes, and Relationships workspace shells
- Local Ollama summary endpoint

## Copy into your project
Copy these changed files over the matching paths:
- `src/features/customer360/Customer360.tsx`
- `src/features/customer360/Customer360.css`
- `src/features/customer360/intelligence.ts`
- `src/features/customer360/types.ts`
- `src/features/customer360/api.ts`
- `src/api/customers.ts`
- `backend/main.py` (the archive stores this as `main.py` because of the source package layout)

## Run
Backend:
```powershell
cd C:\Users\Josh.Corbit\vite-project\backend
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

Frontend:
```powershell
cd C:\Users\Josh.Corbit\vite-project
npm.cmd run dev -- --host 127.0.0.1
```

## Test
1. Open Customer 360 from the navigation.
2. Search for a known active customer.
3. Verify Health, Financial, Sales, and Timeline data.
4. Click **Generate summary** while Ollama is running.

## Important
The health score and recommendations are calculated in TypeScript from verified values returned by the existing customer API. Ollama only creates the narrative explanation and does not calculate balances or scores.
