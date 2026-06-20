# SoriMemo Environment Layout

This workspace currently keeps development code in `/home/scs_dev/velora` and keeps
production runtime code separate under `/opt/sorimemo-prod` for new deployments.

## Development

Development source and scripts stay in this workspace:

- `velora-backend/`
- `velora-frontend/`
- `velora-train/`
- `ops/dev_schema.sql`
- `ops/setup_dev_db.sh`
- `ops/run_dev_backend.sh`

The development database password is generated locally at:

- `ops/generated-dev-db-password.txt`

This file is ignored by Git and must not be committed.

## Production Operations

Production deployment, recovery, and backup helpers are grouped under:

- `ops/prod/`
- `docs/prod/`
- `backups/prod/`

Important production files:

- `ops/prod/rebuild_prod.sh`
- `ops/prod/backup_prod.sh`
- `ops/prod/prod_schema.sql`
- `ops/prod/nginx/`
- `ops/prod/scripts/`
- `docs/prod/RECOVERY_RUNBOOK_KO.md`

Production-generated secrets are stored locally under:

- `ops/prod/secrets/`

This directory is ignored by Git and should remain private.

## Production Runtime

Actual production runtime code and services should remain outside this
development workspace:

- Production root: `/opt/sorimemo-prod`
- Production API service: `sorimemo-prod-api.service`
- Production API port: `127.0.0.1:8010`
- Production web server: `nginx`

Production changes should be applied as a controlled migration from the
development workspace into `/opt/sorimemo-prod`.

## GitHub Guidance

For the new development repository, include source code, development scripts,
and non-secret operational templates only. Do not commit:

- `backups/`
- `ops/generated-*-password.txt`
- `ops/**/generated-*-password.txt`
- `ops/prod/secrets/`
- `.env` files
- uploaded audio, dumps, or runtime logs
