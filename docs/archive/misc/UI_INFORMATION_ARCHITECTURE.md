# ETOP UI Information Architecture

## Design Rule

Navigation answers: **What work is the user trying to do?**

Technical services remain shared behind the scenes. They do not become the
primary way a user has to understand the platform.

## Primary Navigation

| Area | Purpose | Workspaces |
| --- | --- | --- |
| Overview | Start work and understand current priorities | Home |
| Workspaces | Complete operational work | Customers, Cash Application, Lockbox, Documents, Automation |
| Tools | Analyze, build, and ask | Reports, SQL Studio, Knowledge Base, AI Assistant |
| System | Govern and improve platform behavior | Document AI Studio |

## Document Boundaries

### Lockbox

A focused PNC workflow:

1. Upload the lockbox PDF.
2. Process transactions and allocations.
3. Review exceptions.
4. Export the reviewed workbook.
5. Compare the approved workbook and save training.

### Documents

Daily document work only:

- overview and recent activity;
- document explorer;
- upload;
- review queue;
- processing history;
- accounts payable documents.

### Document AI Studio

Administrative and improvement work:

- parser quality;
- learning review;
- profile building;
- saved profiles;
- output templates;
- parser management.

## Compatibility Rules

- Existing document components and API calls remain the implementation source.
- The shell changes entry points and presentation, not backend contracts.
- Lockbox, document operations, and AI Studio each mount the same document
  service layer with a different focused starting context.
- Module names used by the dashboard, command search, and platform registry must
  match the shell module names exactly.
