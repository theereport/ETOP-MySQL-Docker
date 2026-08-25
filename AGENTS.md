# ETOP Repository Instructions

Before changing this project, read and comply with
`AGENT_OPERATING_CONTRACT.md`, `INTEGRATION_MANIFEST.md`, and the applicable
standards in `ETOP-Blueprint/`.

Non-negotiable rules:

- Identify the exact baseline before editing.
- Search for existing implementations before creating new ones.
- Do not replace shared files or another module's work wholesale.
- Keep ERP access read-only and operational data local.
- Do not add hardcoded, fake, or decorative functionality.
- Preserve state, evidence, provenance, and human decision authority.
- Validate the complete workflow and provide a changed-file handoff.
- Escalate unresolved business thresholds or approval authority instead of
  inventing them.

Shared files such as `src/App.tsx`, `backend/main.py`, platform registries,
shared APIs, navigation, and shared types require explicit integration review.
