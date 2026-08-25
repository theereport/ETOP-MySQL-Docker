# Enterprise AI Workbench Architecture Guide

## Governing principle

A module must be independently upgradeable, disableable, testable, and recoverable without taking down unrelated platform functions.

## Platform structure

- Platform Core
- Shared Services
- Business Modules
- Frontend Shell
- Documentation
- Tests

## Module rules

1. Modules communicate through stable APIs, service contracts, shared schemas, or events.
2. A module must not import another module's private implementation.
3. Each module owns its database tables and migrations.
4. Optional module failure must not stop platform startup.
5. Public APIs are versioned.
6. Existing routes remain available during staged migration.
7. Accounting and document outputs require deterministic validation.
