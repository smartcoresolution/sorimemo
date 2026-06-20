#!/usr/bin/env bash
set -euo pipefail

# SoriMemo production rebuild helper.
# This script is intentionally guarded. It deletes local conda/service/runtime
# artifacts only when CONFIRM_REBUILD=YES is supplied.

if [[ "${CONFIRM_REBUILD:-}" != "YES" ]]; then
  echo "Refusing to rebuild. Run with CONFIRM_REBUILD=YES after backup/snapshot."
  exit 1
fi

APP_ROOT="${APP_ROOT:-/home/scs_dev/velora}"
PROD_ROOT="${PROD_ROOT:-/opt/sorimemo-prod}"
CONDA_HOME="${CONDA_HOME:-${APP_ROOT}/tools/miniconda3}"
BACKEND_ENV="${BACKEND_ENV:-${APP_ROOT}/tools/conda-envs/velora-backend}"
FRONTEND_ENV="${FRONTEND_ENV:-${APP_ROOT}/tools/conda-envs/velora-frontend}"
DB_NAME="${SORIMEMO_DB_NAME:-${DB_NAME:-sorimemo_prod}}"
DB_USER="${SORIMEMO_DB_USER:-${DB_USER:-sorimemo_app}}"
DB_PASSWORD="${DB_PASSWORD:-CHANGE_ME_BEFORE_RUNNING}"
SERVER_NAME="${SERVER_NAME:-175.118.124.67}"
PASSWORD_FILE="${PASSWORD_FILE:-${APP_ROOT}/ops/prod/secrets/generated-db-password.txt}"
ADMIN_PASSWORD_FILE="${ADMIN_PASSWORD_FILE:-${APP_ROOT}/ops/prod/secrets/generated-admin-password.txt}"
SSL_CERT_FILE="${SSL_CERT_FILE:-/etc/ssl/certs/ssl-cert-snakeoil.pem}"
SSL_CERT_KEY="${SSL_CERT_KEY:-/etc/ssl/private/ssl-cert-snakeoil.key}"
RESET_CONDA="${RESET_CONDA:-YES}"

if [[ "${DB_PASSWORD}" == "CHANGE_ME_BEFORE_RUNNING" ]]; then
  if [[ -s "${PASSWORD_FILE}" ]]; then
    DB_PASSWORD="$(tr -d '\r\n' < "${PASSWORD_FILE}")"
    echo "Using DB password from ${PASSWORD_FILE}"
  else
    set +o pipefail
    DB_PASSWORD="$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 40)"
    set -o pipefail
    old_umask="$(umask)"
    umask 077
    printf '%s\n' "${DB_PASSWORD}" > "${PASSWORD_FILE}"
    umask "${old_umask}"
    echo "Generated DB password at ${PASSWORD_FILE}"
  fi
fi
if [[ ! "${DB_NAME}" =~ ^[A-Za-z0-9_]+$ || ! "${DB_USER}" =~ ^[A-Za-z0-9_]+$ ]]; then
  echo "DB_NAME and DB_USER may contain only letters, numbers, and underscores."
  exit 1
fi
if [[ "${DB_PASSWORD}" == *"'"* ]]; then
  echo "DB_PASSWORD must not contain a single quote for this rebuild helper."
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y nginx postgresql postgresql-contrib ufw curl ca-certificates build-essential ffmpeg rsync

systemctl stop sorimemo-prod-api 2>/dev/null || true
systemctl stop nginx 2>/dev/null || true

if [[ "${RESET_CONDA}" == "YES" ]]; then
  rm -rf "${CONDA_HOME}" "${BACKEND_ENV}" "${FRONTEND_ENV}"
fi
if [[ ! -x "${CONDA_HOME}/bin/conda" ]]; then
  bash "${APP_ROOT}/tools/Miniconda3-latest-Linux-x86_64.sh" -b -p "${CONDA_HOME}"
fi
"${CONDA_HOME}/bin/conda" config --set auto_activate_base false
if [[ ! -x "${BACKEND_ENV}/bin/python" ]]; then
  "${CONDA_HOME}/bin/conda" create -y -p "${BACKEND_ENV}" python=3.11 pip
fi
if [[ ! -x "${FRONTEND_ENV}/bin/node" ]]; then
  "${CONDA_HOME}/bin/conda" create -y -p "${FRONTEND_ENV}" nodejs=20.17.0
fi
export PATH="${FRONTEND_ENV}/bin:${BACKEND_ENV}/bin:${CONDA_HOME}/bin:${PATH}"

"${BACKEND_ENV}/bin/pip" install --upgrade pip
"${BACKEND_ENV}/bin/pip" install \
  'fastapi[standard]>=0.135.2,<0.136.0' \
  python-multipart==0.0.22 \
  librosa==0.11.0 \
  soundfile==0.13.1 \
  numpy==1.26.4 \
  scipy \
  scikit-learn \
  pydub==0.25.1 \
  tensorflow==2.15.1 \
  keras==2.15.0 \
  h5py \
  matplotlib \
  pillow \
  'sqlalchemy>=2.0,<3.0' \
  'psycopg[binary]>=3.2,<4.0'

install -d -m 0755 "${PROD_ROOT}"
install -d -m 0755 "${PROD_ROOT}/models"
rsync -a --delete "${APP_ROOT}/velora-backend/" "${PROD_ROOT}/backend/"
rsync -a --delete "${APP_ROOT}/normal_mci_ad_task-ALL_best.h5" "${PROD_ROOT}/models/"
rsync -a --delete "${APP_ROOT}/normal_mci_ad_task-ALL_metadata.json" "${PROD_ROOT}/models/"
install -d -m 0755 "${PROD_ROOT}/uploads/raw" "${PROD_ROOT}/uploads/processed" "${PROD_ROOT}/uploads/voice_samples"
install -d -m 0755 /var/www/sorimemo

if [[ -s "${ADMIN_PASSWORD_FILE}" ]]; then
  ADMIN_PASSWORD="$(tr -d '\r\n' < "${ADMIN_PASSWORD_FILE}")"
else
  set +o pipefail
  ADMIN_PASSWORD="$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 32)"
  set -o pipefail
  old_umask="$(umask)"
  umask 077
  printf '%s\n' "${ADMIN_PASSWORD}" > "${ADMIN_PASSWORD_FILE}"
  umask "${old_umask}"
  echo "Generated admin password at ${ADMIN_PASSWORD_FILE}"
fi
ADMIN_HASH="$(openssl passwd -apr1 "${ADMIN_PASSWORD}")"
printf 'sorimemo_admin:%s\n' "${ADMIN_HASH}" > "${ADMIN_AUTH_FILE}"
chown root:www-data "${ADMIN_AUTH_FILE}"
chmod 640 "${ADMIN_AUTH_FILE}"

cd "${APP_ROOT}/velora-frontend"
"${FRONTEND_ENV}/bin/npm" ci
"${FRONTEND_ENV}/bin/npm" run build
rsync -a --delete dist/ /var/www/sorimemo/
chmod -R a+rX /var/www/sorimemo

run_as_postgres() {
  if command -v sudo >/dev/null 2>&1; then
    sudo -u postgres "$@"
  else
    su -s /bin/sh postgres -c "$(printf '%q ' "$@")"
  fi
}

run_as_postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${DB_USER}') THEN
    CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASSWORD}';
  ELSE
    ALTER ROLE ${DB_USER} WITH LOGIN PASSWORD '${DB_PASSWORD}';
  END IF;
END
\$\$;
SELECT 'CREATE DATABASE ${DB_NAME} OWNER ${DB_USER}'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${DB_NAME}')\gexec
SQL

install -m 0644 "${APP_ROOT}/ops/prod/prod_schema.sql" /tmp/sorimemo-prod-schema.sql
run_as_postgres psql -v ON_ERROR_STOP=1 -d "${DB_NAME}" -f /tmp/sorimemo-prod-schema.sql
run_as_postgres psql -v ON_ERROR_STOP=1 -d "${DB_NAME}" -c "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO ${DB_USER};"
run_as_postgres psql -v ON_ERROR_STOP=1 -d "${DB_NAME}" -c "GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO ${DB_USER};"

cat > /etc/sorimemo-prod-api.env <<ENV
DATABASE_URL=postgresql+psycopg://${DB_USER}:${DB_PASSWORD}@127.0.0.1:5432/${DB_NAME}
SORIMEMO_FORCE_CPU=true
CUDA_VISIBLE_DEVICES=-1
SORIMEMO_COGNITIVE_MODEL_PATH=${PROD_ROOT}/models/normal_mci_ad_task-ALL_best.h5
SORIMEMO_COGNITIVE_METADATA_PATH=${PROD_ROOT}/models/normal_mci_ad_task-ALL_metadata.json
SORIMEMO_UPLOAD_DIR=${PROD_ROOT}/uploads/raw
SORIMEMO_PROCESSED_DIR=${PROD_ROOT}/uploads/processed
SORIMEMO_VOICE_SAMPLES_DIR=${PROD_ROOT}/uploads/voice_samples
SORIMEMO_MIN_AUDIO_DURATION=30.0
ENV
chmod 600 /etc/sorimemo-prod-api.env

cat > /etc/systemd/system/sorimemo-prod-api.service <<SERVICE
[Unit]
Description=SoriMemo Production API
After=network.target postgresql.service

[Service]
Type=simple
WorkingDirectory=${PROD_ROOT}/backend
EnvironmentFile=/etc/sorimemo-prod-api.env
ExecStart=${BACKEND_ENV}/bin/fastapi run app/main.py --host 127.0.0.1 --port 8010
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

cat > /etc/nginx/sites-available/sorimemo <<NGINX
server {
    listen 80;
    listen 8080;
    server_name ${SERVER_NAME};

    return 301 https://\$host\$request_uri;
}

server {
    listen 443 ssl http2;
    server_name ${SERVER_NAME};

    ssl_certificate ${SSL_CERT_FILE};
    ssl_certificate_key ${SSL_CERT_KEY};
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    root /var/www/sorimemo;
    index index.html;

    location /api/admin/ {
        proxy_pass http://127.0.0.1:8010/api/admin/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8010/api/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /healthz {
        proxy_pass http://127.0.0.1:8010/healthz;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location / {
        try_files \$uri \$uri/ /index.html;
    }
}
NGINX

ln -sf /etc/nginx/sites-available/sorimemo /etc/nginx/sites-enabled/sorimemo
rm -f /etc/nginx/sites-enabled/default

ufw allow 22/tcp || true
ufw allow 80/tcp || true
ufw allow 443/tcp || true
ufw allow 8080/tcp || true

systemctl daemon-reload
systemctl enable postgresql nginx sorimemo-prod-api
nginx -t
systemctl restart postgresql
systemctl restart sorimemo-prod-api
systemctl restart nginx

for attempt in {1..30}; do
  if curl -fsS "http://127.0.0.1:8010/healthz"; then
    break
  fi
  sleep 1
  if [[ "${attempt}" == "30" ]]; then
    echo "API health check did not pass within 30 seconds."
    systemctl status sorimemo-prod-api --no-pager || true
    exit 1
  fi
done
curl -fsS "http://127.0.0.1:8010/api/analysis/model-status"
echo
echo "SoriMemo production rebuild finished."
