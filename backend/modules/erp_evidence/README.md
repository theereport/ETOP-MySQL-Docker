# ERP Evidence Gateway

Shared read-only gateway that reconciles ERP-sourced evidence (invoice
lookups, spend readiness) across Accounts Payable and Credit Risk.

- `router.py` — HTTP surface.
- `service.py` — `ERPEvidenceRepository`/`erp_evidence_repository`; depends
  on `accounts_payable`'s and `customer_360`'s public `service.py` singletons
  as its evidence sources (a legitimate service-contract dependency, not an
  internals reach-through — see Module Standards.md).
- `manifest.py` — registration entry point
  (`modules.erp_evidence.manifest.manifest`).
