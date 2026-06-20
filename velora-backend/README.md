# SoriMemo Backend

FastAPI backend for SoriMemo voice upload, quality checks, trained Normal/MCI/AD model inference, and non-medical risk guidance for 안심소리 기억케어.

## Model Configuration

By default the API loads the trained VGG16 `.h5` model and metadata from these locations, in order:

- `../velora-train/normal_mci_ad_task_ALL_best.h5`
- `../velora-train/normal_mci_ad_task-ALL_best.h5`
- `../normal_mci_ad_task_ALL_best.h5`
- `../normal_mci_ad_task-ALL_best.h5`

The metadata file is discovered with the same naming pattern using `_metadata.json`.
You can override the discovered paths:

```bash
export SORIMEMO_COGNITIVE_MODEL_PATH=/data/models/normal_mci_ad_task-ALL_best.h5
export SORIMEMO_COGNITIVE_METADATA_PATH=/data/models/normal_mci_ad_task-ALL_metadata.json
export SORIMEMO_COGNITIVE_MODEL_SAMPLE_RATE=48000
export SORIMEMO_COGNITIVE_MODEL_SECONDS=30
export SORIMEMO_FORCE_CPU=true
```

The metadata class order is used for model output interpretation. `Normal`, `MCI`, and `AD` are returned to the API as probabilities.
`SORIMEMO_FORCE_CPU` defaults to `true`, so inference runs without requiring a GPU or CUDA runtime.
Existing `VELORA_*` variables are still read as fallback during the migration.

## Run

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

For production, run FastAPI behind an HTTPS reverse proxy and expose only HTTPS to users. Internal proxy hops such as `127.0.0.1:8010` can remain private loopback HTTP.

## Admin & CORS Configuration

User signup and login return a bearer token. Protected user APIs require:

- `Authorization: Bearer <access_token>`

Set a stable signing secret in production:

```bash
export SORIMEMO_AUTH_SECRET_KEY='replace-with-a-long-random-user-token-secret'
export SORIMEMO_AUTH_TOKEN_TTL_SECONDS=86400
```

If `SORIMEMO_AUTH_SECRET_KEY` is not set, tokens are signed with a temporary process-local secret and become invalid after server restart.

Password reset endpoints:

- `POST /api/auth/password-reset/request`: issue a short-lived reset code.
- `POST /api/auth/password-reset/confirm`: set a new password with the reset code.

Until outbound email is connected, reset codes can be returned by the API for controlled operation:

```bash
export SORIMEMO_PASSWORD_RESET_TTL_SECONDS=1800
export SORIMEMO_PASSWORD_RESET_EXPOSE_TOKEN=true
```

Set `SORIMEMO_PASSWORD_RESET_EXPOSE_TOKEN=false` after connecting email delivery.

The admin dashboard API is protected by a bearer token. Admin login accepts either:

- a database user with `role` set to `admin` or `operator`, `status='active'`, and a valid `password_hash`
- explicit environment credentials:

```bash
export SORIMEMO_ADMIN_USERNAME=admin@example.com
export SORIMEMO_ADMIN_PASSWORD='change-this-password'
export SORIMEMO_ADMIN_SECRET_KEY='replace-with-a-long-random-secret'
export SORIMEMO_ADMIN_TOKEN_TTL_SECONDS=28800
```

For production, prefer `SORIMEMO_ADMIN_PASSWORD_HASH` over `SORIMEMO_ADMIN_PASSWORD`.
Set `SORIMEMO_ADMIN_SECRET_KEY` to a stable secret, otherwise admin tokens are invalidated on server restart.

Create or update a database-backed admin user:

```bash
export DATABASE_URL='postgresql+psycopg://user:password@host:5432/dbname'
export SORIMEMO_ADMIN_BOOTSTRAP_PASSWORD='replace-with-a-strong-password'
python scripts/upsert_admin_user.py --admin-id admin
```

CORS defaults to local Vite origins only. Override for deployed frontends:

```bash
export SORIMEMO_CORS_ORIGINS='https://your-frontend.example.com'
```

Use `SORIMEMO_CORS_ALLOW_ALL=true` only for isolated development.

## Retention & Deletion

Retention defaults:

```bash
export SORIMEMO_RESULT_RETENTION_DAYS=90
export SORIMEMO_AUDIO_RETENTION_DAYS=1
export SORIMEMO_VOICE_SAMPLE_RETENTION_DAYS=1
export SORIMEMO_DELETE_VOICE_SAMPLE_AFTER_ANALYSIS=true
```

After analysis, raw upload files, standardized WAV files, target temporary files, and child voice samples are deleted according to policy. Analysis results are retained as structured data until their retention period expires.

Deletion endpoints:

- `DELETE /api/auth/me/data`: revoke the current user's consents and delete their audio files, voice samples, and analysis results.
- `POST /api/admin/retention/cleanup`: admin-only cleanup for expired retention records.

## Main Flow

- `POST /api/upload/audio`: upload or receive smartphone-recorded audio.
- `POST /api/analysis/jobs/start/{file_id}`: enqueue speaker extraction, trained model inference, and risk message generation.
- `GET /api/analysis/jobs/{job_id}`: poll queued/processing/completed/failed analysis job status.
- `GET /api/results/{analysis_id}`: return cognitive status, risk level, probabilities, and guidance.
- `GET /api/results/history`: return the current user's saved analysis history.
- `DELETE /api/results/{analysis_id}`: delete one analysis history item for the current user.
- `GET /api/analysis/model-status`: verify model configuration.

## Quality & Model Validation

`GET /api/analysis/model-status` returns the model load state, inference flags, and active audio quality thresholds.

Run lightweight local validation before deployment:

```bash
python scripts/run_quality_validation.py
```

This generates synthetic speech-like audio, runs the audio quality gate, computes confidence scoring, extracts transcript-derived language markers, and writes `../test_data/quality_validation_results.json`.

Run API-level validation against a live backend and `test_data/manifest.json`:

```bash
python scripts/run_inference_validation.py --base-url https://your-frontend.example.com
```
