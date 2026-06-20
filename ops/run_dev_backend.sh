#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/home/scs_dev/velora}"
BACKEND_ROOT="${BACKEND_ROOT:-${APP_ROOT}/velora-backend}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${SORIMEMO_DB_NAME:-${DB_NAME:-velora_dev}}"
DB_USER="${SORIMEMO_DB_USER:-${DB_USER:-velora_app}}"
BACKEND_PORT="${BACKEND_PORT:-8011}"
DB_PASSWORD_FILE="${SORIMEMO_DB_PASSWORD_FILE:-${DB_PASSWORD_FILE:-${APP_ROOT}/ops/generated-dev-db-password.txt}}"
BACKEND_ENV="${BACKEND_ENV:-${APP_ROOT}/tools/conda-envs/velora-backend}"

if [[ ! -s "${DB_PASSWORD_FILE}" ]]; then
  echo "Missing dev DB password file: ${DB_PASSWORD_FILE}" >&2
  echo "Run the dev DB setup first." >&2
  exit 1
fi

DB_PASSWORD="$(tr -d '\r\n' < "${DB_PASSWORD_FILE}")"

export DATABASE_URL="postgresql+psycopg://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
export SORIMEMO_FORCE_CPU="${SORIMEMO_FORCE_CPU:-${VELORA_FORCE_CPU:-true}}"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:--1}"
export SORIMEMO_LIGHTWEIGHT_INFERENCE="${SORIMEMO_LIGHTWEIGHT_INFERENCE:-${VELORA_LIGHTWEIGHT_INFERENCE:-1}}"
export SORIMEMO_COGNITIVE_MODEL_PATH="${SORIMEMO_COGNITIVE_MODEL_PATH:-${VELORA_COGNITIVE_MODEL_PATH:-${APP_ROOT}/normal_mci_ad_task-ALL_best.h5}}"
export SORIMEMO_COGNITIVE_METADATA_PATH="${SORIMEMO_COGNITIVE_METADATA_PATH:-${VELORA_COGNITIVE_METADATA_PATH:-${APP_ROOT}/normal_mci_ad_task-ALL_metadata.json}}"
export SORIMEMO_UPLOAD_DIR="${SORIMEMO_UPLOAD_DIR:-${VELORA_UPLOAD_DIR:-/tmp/sorimemo_uploads}}"
export SORIMEMO_PROCESSED_DIR="${SORIMEMO_PROCESSED_DIR:-${VELORA_PROCESSED_DIR:-/tmp/sorimemo_processed}}"
export SORIMEMO_VOICE_SAMPLES_DIR="${SORIMEMO_VOICE_SAMPLES_DIR:-${VELORA_VOICE_SAMPLES_DIR:-/tmp/sorimemo_voice_samples}}"
export SORIMEMO_DELETE_VOICE_SAMPLE_AFTER_ANALYSIS="${SORIMEMO_DELETE_VOICE_SAMPLE_AFTER_ANALYSIS:-${VELORA_DELETE_VOICE_SAMPLE_AFTER_ANALYSIS:-false}}"

cd "${BACKEND_ROOT}"

if [[ -x "${BACKEND_ENV}/bin/python" ]]; then
  exec "${BACKEND_ENV}/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port "${BACKEND_PORT}"
fi

exec uvicorn app.main:app --host 127.0.0.1 --port "${BACKEND_PORT}"
