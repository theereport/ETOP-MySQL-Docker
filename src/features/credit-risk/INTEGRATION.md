# Credit Risk Increments 1–3 frontend integration

Increment 3 is module-local. `CreditRiskWorkspace` now contains working
**Priority & Alerts**, **Customer Risk 360**, and **Credit-Line Intelligence**
views, so no additional shared
shell or navigation change is required over the integrated Increment 1
baseline.

The feature implementation is intentionally module-local. The integration owner must
make the shared-shell changes below after the backend router is integrated.

## 1. `src/App.tsx`

Add this import beside the other feature imports:

```tsx
import CreditRiskWorkspace from './features/credit-risk'
```

Add this entry immediately after the existing `Customer 360` entry in the local
`modules` array:

```tsx
{
  title: 'Credit Risk',
  shortTitle: 'Credit Risk',
  description:
    'Review source-grounded exposure, aging, payment evidence, and append-only manual assessments.',
  hint: 'Evidence & assessments',
  icon: '◫',
  status: 'Ready',
  group: 'Workspaces',
},
```

Add this render branch immediately after the existing `Customer 360` branch:

```tsx
{selectedModule === 'Credit Risk' && (
  <CreditRiskWorkspace />
)}
```

No customer route parameter is required. The workspace uses the existing shared
Customer 360 search contract internally.

## 2. `src/platform/registry.ts`

Add this entry immediately after `Customer 360` in `platformModules`:

```tsx
{
  id: 'credit-risk',
  title: 'Credit Risk',
  shortTitle: 'Credit Risk',
  description:
    'Source-grounded credit evidence and append-only manual risk assessments.',
  icon: '◫',
  group: 'Operations',
  version: '0.1.0',
  status: 'Ready',
  capabilities: ['search', 'timeline'],
  keywords: [
    'credit risk',
    'exposure',
    'manual rating',
    'assessment',
    'review date',
  ],
},
```

Do not add `recommendations` or `ai` capabilities in Increment 1.

## 3. `src/platform/registry/modules.ts`

Add this module-search seed after the customer entry:

```tsx
{
  id: 'credit-risk',
  type: 'module',
  title: 'Credit Risk',
  subtitle: 'Source-grounded evidence and append-only manual assessments',
  icon: '◫',
  module: 'Credit Risk',
  keywords: [
    'credit risk',
    'manual rating',
    'assessment',
    'exposure',
    'review date',
  ],
},
```

## 4. Verification

From the project root, run:

```powershell
node verification/verify-credit-risk-workflow.mjs
node verification/verify-credit-line-intelligence.mjs
npx eslint src/features/credit-risk --max-warnings=0
npm.cmd run build
```

The backend must expose:

- `GET /api/v1/credit-risk/bands`
- `GET /api/v1/credit-risk/priority-alerts`
- `GET /api/v1/credit-risk/customers/{customer_number}`
- `GET /api/v1/credit-risk/customers/{customer_number}/assessments`
- `POST /api/v1/credit-risk/customers/{customer_number}/assessments`
- `GET /api/v1/credit-risk/customers/{customer_number}/credit-line-intelligence`
- `GET /api/v1/credit-risk/customers/{customer_number}/credit-line-proposals`
- `POST /api/v1/credit-risk/customers/{customer_number}/credit-line-proposals`

The shared Customer 360 endpoint remains the only customer-search implementation.

The Priority & Alerts endpoint must remain assessed-customer-only, expose the
saved Product Owner draft-band attention flag/filter separately from approved
policy, retain assessment IDs and evidence hashes, degrade live over-line
evidence honestly, and keep broken-promise/NSF sources explicitly unavailable.

The Credit-Line Intelligence view must preserve the exact analytical formula,
unapproved-policy label, unavailable source gaps, append-only professional
proposal history, operator-supplied identity, and no-decision/no-ERP boundary.

## Step 5 ERP evidence integration

The ERP Evidence view reuses the normal customer search and selected Customer
Risk snapshot, then reads:

- `GET /api/v1/erp-evidence/credit/customers/{customer_number}`

The response exposes current `TMCUST` facts, bounded nonzero `TMAROP` rows, and
`TMCUST.CUNUMENT`-linked accounts. CUNUMENT is relationship evidence only, not
proof of all guarantors, parents, or related entities. The detailed-order,
unbilled-shipment, full payment-history, credit-line-history, unapplied-cash,
valid-credit, and secured-amount gaps must remain explicit.

The evidence packet may inform professional review but must never trigger or
imply a recommendation, Decision, approval, line/terms/order change,
hold/release, posting, export, notification, or ERP write.
