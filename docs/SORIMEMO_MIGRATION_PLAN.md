# SoriMemo Migration Plan

This migration keeps the public brand aligned first, then moves internal names in
controlled steps so the development server, PostgreSQL data, and nginx routes do
not break at the same time.

## Completed

- Public app name: `SoriMemo`
- Service name in Korean copy: `안심소리 기억케어`
- Browser title, home screen title, admin login label, API docs title, and consent
  policy copy updated.
- Frontend package metadata renamed to `sorimemo-frontend`.
- Backend package metadata renamed to `sorimemo-backend`.
- Validation script descriptions and generated dataset names updated where they do
  not affect existing runtime configuration.
- Backend configuration now prefers `SORIMEMO_*` environment variables and reads
  existing `VELORA_*` variables as fallback.
- Default temporary paths now use `/tmp/sorimemo_*` while legacy values can still
  be supplied through `VELORA_*`.
- Browser storage keys now use `sorimemo_*`; existing `velora_*` localStorage and
  sessionStorage keys are copied forward on app startup.
- Deployment templates now use SoriMemo names for nginx auth labels, future
  `/var/www/sorimemo` static roots, `/opt/sorimemo-prod` production roots, and
  `sorimemo-prod-api` service names.
- A development systemd template is available at
  `ops/dev/sorimemo-backend.service`.
- Root/PostgreSQL cutover instructions are documented in
  `docs/SORIMEMO_ROOT_STEPS_KO.md`.

## Next Steps

1. Apply root-level nginx/systemd changes from `docs/SORIMEMO_ROOT_STEPS_KO.md`.
2. Rename database/user names only after backup:
   `velora_dev`, `velora_prod`, and `velora_app` should be changed after backup,
   connection string updates, and verification.

## Keep Until Final Migration

- `VELORA_*` environment variables
- Existing PostgreSQL database/user names
- Existing workspace folder names
