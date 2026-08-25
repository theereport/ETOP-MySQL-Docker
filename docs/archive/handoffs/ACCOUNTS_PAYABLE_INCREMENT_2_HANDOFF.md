# ETOP 0.7.0 Accounts Payable Increment 2 Handoff

## Install position

Install only after the Credit Risk Increment 3 package verifies successfully.

## Delivered

- Approval Center for evidence-readiness cases and dispositions.
- Payment Controls for payment-preparation evidence and segregation readiness.
- Immutable cases bound to exact AP invoice source revisions and hashes.
- Deterministic document, duplicate, exception, evidence-currency, and
  operator-supplied separation checks.
- Append-only assigned-reviewer dispositions and reconstructable history.
- Explicit unavailable ERP, authentication, approval, and payment authority.

## Not delivered

No authenticated identity, approval matrix, invoice approval, vendor-master or
ERP payable validation, payment authorization, bank/payment integration,
posting, export, notification, vendor communication, AI action, or ERP write.

## Verification

Run the packaged installer and verifier with ETOP stopped. The verifier checks
the exact Credit Risk Increment 3 prerequisite, controlled hashes, Python
compilation, AP and retained Credit Risk contracts, workflow verification, and
operational-data exclusion.
