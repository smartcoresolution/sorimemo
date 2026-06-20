# VELORA Production Setup Log

Date: 2026-05-28
Server IP: 175.118.124.67
Production root: `/opt/velora-prod`
Development root: `/root/velora`

## 1. Web Server

Installed and configured Nginx for the production frontend.

Public URLs:

```text
http://175.118.124.67/
http://175.118.124.67:8080/
```

Nginx site config:

```text
/etc/nginx/sites-available/velora
/etc/nginx/sites-enabled/velora
```

Frontend web root:

```text
/var/www/velora
```

Nginx now listens on:

```text
80
8080
```

Firewall opened:

```text
80/tcp
443/tcp
8080/tcp
```

Verification:

```text
curl http://175.118.124.67/
curl http://175.118.124.67:8080/
```

Both returned HTTP 200 from Nginx.

## 2. Frontend Deployment

Production frontend path:

```text
/opt/velora-prod/frontend
```

Built frontend output copied to:

```text
/var/www/velora
```

Node.js issue fixed:

```text
Old version: Node v12.22.9
Required: Node 20 LTS
```

Node 20 was installed after removing conflicting old packages including `libnode-dev`.

## 3. API Server

Production backend path:

```text
/opt/velora-prod/backend
```

FastAPI runs through systemd:

```text
/etc/systemd/system/velora-prod-api.service
```

API environment file:

```text
/etc/velora-prod-api.env
```

API server bind address:

```text
127.0.0.1:8010
```

Nginx proxy:

```text
/api/*   -> http://127.0.0.1:8010/api/*
/healthz -> http://127.0.0.1:8010/healthz
```

Verification:

```text
http://175.118.124.67/healthz
http://175.118.124.67/api/analysis/model-status
```

Both returned successful responses.

Useful commands:

```bash
systemctl status velora-prod-api
systemctl restart velora-prod-api
journalctl -u velora-prod-api -f
```

## 4. Model Deployment

Production model files:

```text
/opt/velora-prod/models/normal_mci_ad_task-ALL_best.h5
/opt/velora-prod/models/normal_mci_ad_task-ALL_metadata.json
```

API model environment:

```text
VELORA_FORCE_CPU=true
VELORA_COGNITIVE_MODEL_PATH=/opt/velora-prod/models/normal_mci_ad_task-ALL_best.h5
VELORA_COGNITIVE_METADATA_PATH=/opt/velora-prod/models/normal_mci_ad_task-ALL_metadata.json
```

Model status confirmed:

```text
available: true
runtime: CPU
classes: AD / MCI / Normal
```

## 5. CPU Inference

Backend inference was changed to run without GPU.

Key behavior:

```text
VELORA_FORCE_CPU=true
CUDA_VISIBLE_DEVICES=-1
TensorFlow GPU devices hidden at runtime
```

Updated file:

```text
/opt/velora-prod/backend/app/services/cognitive_model.py
/root/velora/velora-backend/app/services/cognitive_model.py
```

## 6. FLAC Audio Support

The backend was updated so `.flac` files can be processed without `ffmpeg`.

If `ffmpeg` is not available, fallback conversion uses:

```text
librosa
soundfile
```

Standard analysis WAV format:

```text
sample rate: 16000 Hz
channels: mono
sample format: PCM 16-bit
```

Updated file:

```text
app/services/audio_processor.py
```

Tested file:

```text
velora-train/dataset_test/sample_dataset/CERAD-K/sample-cerad-k-ad-000/sample-cerad-k-ad-000_F.flac
```

Direct model inference result:

```text
prediction: AD
risk_score: 97.45
Normal: 0.023652
MCI: 0.004078
AD: 0.972270
```

Note:

```text
The sample file is 3 seconds long.
Production minimum duration remains 30 seconds.
```

Configurable minimum duration:

```text
VELORA_MIN_AUDIO_DURATION=30.0
```

## 7. PostgreSQL DB Server

Installed PostgreSQL 14.

DB listens locally only:

```text
127.0.0.1:5432
```

Production database:

```text
velora_prod
```

Application DB user:

```text
velora_app
```

Connection string is stored in:

```text
/etc/velora-prod-api.env
```

File permission:

```text
chmod 600 /etc/velora-prod-api.env
```

Installed Python DB packages into backend conda environment:

```text
SQLAlchemy
psycopg
psycopg-binary
```

## 8. Database Tables

Created tables:

```text
users
consents
audio_files
voice_samples
analysis_results
notices
board_posts
audit_logs
```

Created indexes:

```text
idx_consents_token
idx_audio_files_created_at
idx_analysis_results_created_at
idx_notices_published
idx_board_posts_created_at
```

Verification:

```text
psql connection OK
SQLAlchemy connection OK
```

## 9. Backend DB App Logic

Added DB module:

```text
app/database.py
```

Updated routers:

```text
app/routers/consent.py
app/routers/upload.py
app/routers/analysis.py
app/routers/results.py
app/routers/admin.py
```

DB-backed behavior now includes:

```text
Consent registration -> users + consents
Consent verification -> DB lookup fallback
Audio upload -> audio_files
Voice sample upload -> voice_samples
Analysis completion -> analysis_results
Result lookup -> DB lookup fallback
Admin dashboard -> DB statistics
```

Memory dictionaries remain as process-local cache for current requests.

## 10. Upload Storage Paths

Production upload directories:

```text
/opt/velora-prod/uploads/raw
/opt/velora-prod/uploads/processed
/opt/velora-prod/uploads/voice_samples
```

Environment variables:

```text
VELORA_UPLOAD_DIR=/opt/velora-prod/uploads/raw
VELORA_PROCESSED_DIR=/opt/velora-prod/uploads/processed
VELORA_VOICE_SAMPLES_DIR=/opt/velora-prod/uploads/voice_samples
```

## 11. Tests Performed

API health:

```text
GET /healthz -> {"status":"ok"}
```

Model status:

```text
GET /api/analysis/model-status -> available true
```

Consent DB write:

```text
POST /api/consent/agree -> consent_token returned
DB row created in users and consents
```

Consent DB lookup:

```text
GET /api/consent/verify/{token} -> valid true
```

Audio upload DB write:

```text
POST /api/upload/audio with sample .flac
DB row created in audio_files
```

Expected result for the 3-second sample:

```text
quality_pass: false
reason: minimum duration is 30 seconds
```

Admin dashboard:

```text
GET /api/admin/dashboard -> DB statistics returned
```

## 12. Important Current State

Working:

```text
Web server
Frontend static serving
API server
Nginx API proxy
CPU model status
PostgreSQL server
DB schema
DB-backed consent/upload/result logic
```

Still to do:

```text
Add authentication/admin login
Build admin pages for users/consents/audio/results
Add notices and board API
Add HTTPS domain certificate
Add DB backup script
Add production log rotation
Consider object storage for audio files
```

## 13. Useful Commands

Nginx:

```bash
nginx -t
systemctl reload nginx
systemctl status nginx
```

API:

```bash
systemctl status velora-prod-api
systemctl restart velora-prod-api
journalctl -u velora-prod-api -f
```

PostgreSQL:

```bash
systemctl status postgresql
psql -h 127.0.0.1 -U velora_app -d velora_prod
```

Health checks:

```bash
curl http://175.118.124.67/healthz
curl http://175.118.124.67/api/analysis/model-status
curl http://175.118.124.67/api/admin/dashboard
```
