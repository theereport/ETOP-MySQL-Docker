# Enterprise Framework Phase 1

Copy `src/api` and `src/components/enterprise` into the matching Vite project folders. Replace `src/features/customer360/api.ts` with the included file.

Optional `.env` entry:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1
```

Validate with:

```bat
cd /d C:\Users\Josh.Corbit\vite-project
npm.cmd run build
```

This adds a shared API client, SummaryCard, CustomerHeader, and EnterpriseDataGrid. The next phase uses them for the Customer 360 Invoices tab and invoice detail drawer.
