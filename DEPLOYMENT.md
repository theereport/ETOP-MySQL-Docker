# Docker deployment

Runs the backend, its own MySQL database (`etop`), and Ollama as a
self-contained stack. The frontend is deployed separately (a static SPA that
talks to the backend over HTTP - see `src/api/client.ts`'s `VITE_API_BASE_URL`).

## First-time setup

1. Copy the env template and fill in real values:
   ```bash
   cp backend/.env.docker.example backend/.env
   ```
   At minimum you must set: the real external MaddenCo ERP `MYSQL_*`
   credentials, `ETOP_DB_PASSWORD` (a password for the app's own MySQL
   user - `docker-compose.yml` seeds the `etop-db` container with it),
   `ETOP_APP_URL` (your real frontend origin), and
   `ETOP_SESSION_SIGNING_SECRET` (≥32 random characters - generate with
   `python -c "import secrets; print(secrets.token_urlsafe(32))"`).

2. Give the bind-mounted data directories ownership matching the
   container's fixed non-root user (UID/GID 1000, see the `Dockerfile`):
   ```bash
   sudo chown -R 1000:1000 data backend/data \
       backend/modules/document_intelligence/lockbox_results \
       backend/modules/document_intelligence/lockbox_exports
   touch backend/sql_workspace.db && sudo chown 1000:1000 backend/sql_workspace.db
   ```

3. Generate `backend/.env.compose` - a `$`-escaped copy of `backend/.env`.
   **Do this every time you edit `backend/.env`.** Docker Compose applies
   `$VAR` interpolation to every value it reads from an env file (both the
   project `--env-file` and any service's `env_file:`), so a literal `$` in
   a real password/secret gets silently treated as the start of a variable
   reference and truncated - this actually happened when this stack was
   first verified (a password got silently cut down to a few characters).
   `backend/.env` itself must stay plain/unescaped for local, non-Docker
   runs (`python-dotenv` does no such interpolation) - `.env.compose` is
   purely a Docker-side derivative, gitignored, never hand-edited:
   ```bash
   sed 's/\$/$$/g' backend/.env > backend/.env.compose
   ```

4. **Always pass `--env-file backend/.env.compose`** to `docker compose`
   invocations - Compose's own `${VAR}` substitution (used in
   `docker-compose.yml` for the `etop-db` service's init variables) only
   reads from whichever env file you tell it to use, and the app's real env
   file lives at `backend/.env`, not the repo root where Compose looks by
   default:
   ```bash
   docker compose --env-file backend/.env.compose build
   docker compose --env-file backend/.env.compose up -d
   ```

5. Pull the three Ollama models the app uses (hardcoded model names, not
   configurable except `SQL_AI_MODEL`):
   ```bash
   docker compose exec ollama ollama pull qwen2.5-coder:7b
   docker compose exec ollama ollama pull gemma3:12b
   docker compose exec ollama ollama pull nomic-embed-text
   ```

6. Confirm it's up:
   ```bash
   curl http://localhost:8000/health
   ```
   `backend_ready` should be `true`. `madden_database_ready` reflects the
   external ERP connection specifically - `false` there means the `MYSQL_*`
   credentials/host in `backend/.env` need attention, not a Docker problem.

## Day-to-day

```bash
docker compose --env-file backend/.env.compose up -d       # start
docker compose --env-file backend/.env.compose logs -f backend
docker compose --env-file backend/.env.compose down         # stop (data persists - see volumes below)
```

Regenerate `backend/.env.compose` (step 3 above) any time you change
`backend/.env`.

## What's persisted, and where

| Host path | Container path | Contents |
|---|---|---|
| `./data` | `/app/data` | Uploaded documents, OCR results, vector store, training data - the repo-root `data/` tree `core/config.py`'s `data_root` resolves to |
| `./backend/data` | `/app/backend/data` | Automation run outputs |
| `./backend/modules/document_intelligence/lockbox_results` | same | Lockbox parser results |
| `./backend/modules/document_intelligence/lockbox_exports` | same | Lockbox PNC export workbooks |
| `./backend/sql_workspace.db` | same | SQL Workspace saved queries/history - the one feature intentionally left on SQLite, not MySQL |
| `etop-db-data` (named volume) | MySQL's `/var/lib/mysql` | The app's own `etop` schema - all business data (workflow, financial close, accounts payable, document intelligence metadata, lockbox preparation, etc.) |
| `ollama-data` (named volume) | Ollama's `/root/.ollama` | Downloaded models |

Everything else in the container is stateless and rebuilt from source on
every `docker compose build`.

## Known limitation: PowerShell/Outlook automations won't run in this container

`modules/automations/service.py` supports a `source_type == "powershell"`
automation kind, including an email-delivery path that generates a script
doing `New-Object -ComObject Outlook.Application` - Windows COM automation
against a locally-installed Outlook client. This cannot function on Linux
under any circumstances (no COM subsystem, no Outlook), regardless of
whether PowerShell Core (`pwsh`) is installed in the image. No attempt has
been made to work around this - if PowerShell-type automations (especially
Outlook email delivery) are actually used, they need to keep running on a
Windows host, or be migrated to an SMTP-based delivery path, as a separate
piece of work.

## Rebuilding after a code change

```bash
docker compose --env-file backend/.env.compose build backend
docker compose --env-file backend/.env.compose up -d backend
```

Dependency changes require editing `backend/requirements.txt` (production)
or `backend/requirements-dev.txt` (adds test tooling on top) - both are
derived from `backend/.venv`'s `pip freeze`; keep them in sync when you add
a package locally.
