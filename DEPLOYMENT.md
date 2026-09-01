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

## Optional: GPU passthrough for Ollama

Ollama's chat (`gemma3:12b`) and embedding (`nomic-embed-text`) inference run
on CPU by default. On a host with a compatible NVIDIA GPU, passthrough makes
those noticeably faster. This is opt-in via a separate override file
(`docker-compose.gpu.yml`) rather than being on by default, because the GPU
device reservation makes `docker compose up` hard-fail on any host where the
setup below isn't complete - it does not gracefully fall back to CPU.

GPU passthrough is host-specific: it uses whichever machine actually runs
`docker compose up`, not a fixed/remote GPU. Each host needs this done
separately - the compose file doesn't carry the GPU with it.

Requirements on the host:
- An NVIDIA GPU with a current driver installed.
- The [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
  installed and configured for Docker (`nvidia-ctk runtime configure
  --runtime=docker` followed by a Docker daemon restart, on a native Linux
  Docker host).
- On Windows via Docker Desktop specifically: the WSL2 backend (not
  Hyper-V/linuxkit) is required for GPU passthrough at all - check with
  `docker info` (`Kernel Version` should *not* say `linuxkit`) - plus Docker
  Desktop's "Use the WSL 2 based engine" and GPU support settings enabled.

Once that's done, start (or restart) the stack with both compose files:
```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml --env-file backend/.env.compose up -d
```

Verify Ollama can see the GPU:
```bash
docker compose exec ollama nvidia-smi
```

## TLS

The `reverse-proxy` service (nginx) terminates TLS on 443 and redirects 80 ->
443; the `backend` service's own port is bound to `127.0.0.1:8000` only
(local debugging), not published to the network - the proxy is the real
public entry point.

On first start with no certificate present, the proxy generates a
**self-signed placeholder** certificate into `./nginx/certs/` (gitignored -
never commit it) and logs that it did so. This is fine for local/no-domain
use, but a browser will show a certificate warning, and it is not suitable
for real external use.

Once a domain is assigned on the real deployment server, replace the
placeholder with a real certificate:
1. Get a certificate for your domain (Let's Encrypt via certbot, or an
   org-issued cert + key).
2. Overwrite `./nginx/certs/server.crt` and `./nginx/certs/server.key` with
   the real certificate and key (same filenames).
3. `docker compose --env-file backend/.env.compose restart reverse-proxy`
   (the entrypoint only generates a cert when the files are missing, so it
   won't overwrite what you just placed there).

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

## Backups and restore

The `backup` service in `docker-compose.yml` runs `backend/scripts/backup_mysql.sh`
once at startup and then every 24 hours, writing a gzipped `mysqldump` of the
`etop` schema to `./backups/etop-<UTC timestamp>.sql.gz` and deleting dumps
older than `BACKUP_RETENTION_DAYS` (default 14). `./backups/` is a plain host
directory (gitignored - never commit a real dump) - copy it somewhere off-host
periodically (it's just files, so any normal method works).

Run a backup on demand:
```bash
docker compose --env-file backend/.env.compose exec backup sh /scripts/backup_mysql.sh
```

Restore a dump into the running `etop-db` container:
```bash
gunzip < backups/etop-<timestamp>.sql.gz | \
  docker compose --env-file backend/.env.compose exec -T etop-db \
  mysql -u "$ETOP_DB_USER" -p"$ETOP_DB_PASSWORD" "$ETOP_DB_NAME"
```
(Use the real `ETOP_DB_USER`/`ETOP_DB_PASSWORD`/`ETOP_DB_NAME` values from
`backend/.env`.) This restores into whatever database already exists -
tables are re-created via `CREATE TABLE` in the dump, so restore into an
empty schema if you're recovering from data loss rather than just testing
the dump.

## Schema migrations (Alembic)

Every table was originally created by each module's own
`metadata.create_all(checkfirst=True)` call (see `backend/data/mysql.py`) -
that call can add a brand-new table but can never `ALTER` an existing one.
Alembic is now layered on top for anything beyond a new table, and the live
database is already stamped at a baseline revision representing "everything
before this point was created outside Alembic's control" - `create_all`
still runs the same as before and remains how new tables get created.

For a schema change from here on:
```bash
docker compose --env-file backend/.env.compose exec backend python -m alembic revision --autogenerate -m "describe the change"
```
Then **review the generated file** before applying it -
`backend/alembic/versions/<rev>_baseline_schema_as_created_by_metadata_.py`'s
docstring explains why: many `CheckConstraint`s were declared without an
explicit name, so MySQL auto-assigned names like `sometable_chk_3`, and
Alembic can't correlate those back to the unnamed Python-side constraint. It
will re-propose dropping and recreating every one of them as noise on every
autogenerate diff - discard those `chk_N` drop/create pairs and keep only
the change you actually intended. Then apply it:
```bash
docker compose --env-file backend/.env.compose exec backend python -m alembic upgrade head
```
Check the current/pending state at any time with `alembic current` /
`alembic history`.

## AP ERP ledger refresh - native workaround (this dev machine only)

On this machine, triggering the AP open-ledger refresh (Report Builder /
Accounts Payable's "Refresh") from inside Docker is unreliable - it either
takes several minutes or gets killed outright ("Interrupted by backend
restart"). Confirmed 2026-09-01: Docker Desktop's Hyper-V backend here
doesn't reliably route container traffic through the Barracuda VPN
client's split-tunnel route to the MaddenCo ERP server, while a native
(non-Docker) connection reaches the same server in a few seconds. This is
specific to this machine's Docker backend, not a code issue, and is not
expected on the real Linux deployment target.

Until that's addressed (switching Docker Desktop to the WSL2 backend is
the likely fix, but is a bigger system change - deferred for now), run the
refresh natively instead:
```bash
bash backend/scripts/refresh_erp_ledger_native.sh
```
This temporarily publishes `etop-db`'s port to `127.0.0.1:3307` (via
`docker-compose.native-refresh.yml`), runs the refresh from
`backend/.venv` directly against the live Dockerized database, and reverts
the port automatically when done - including on failure (it's wrapped in a
cleanup trap). Requires `backend/.venv` to already be set up.

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
