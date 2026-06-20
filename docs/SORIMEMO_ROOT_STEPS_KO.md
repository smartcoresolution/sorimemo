# SoriMemo Root/PostgreSQL 전환 작업

아래 작업은 실제 서버 설정을 바꾸므로 root 또는 postgres 권한이 필요합니다.
현재 앱 코드는 기존 `VELORA_*`, `velora_dev`, `velora_app`도 fallback으로 지원하므로,
아래 전환을 하기 전까지 서버는 기존 설정으로 계속 동작합니다.

## 1. PostgreSQL 개발 DB 복제

기존 개발 DB를 유지한 채 새 이름으로 복제합니다.

```bash
sudo -u postgres createdb -T velora_dev sorimemo_dev
sudo -u postgres psql -v ON_ERROR_STOP=1 <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'sorimemo_app') THEN
    CREATE ROLE sorimemo_app LOGIN PASSWORD 'CHANGE_ME';
  END IF;
END
$$;
GRANT ALL PRIVILEGES ON DATABASE sorimemo_dev TO sorimemo_app;
\c sorimemo_dev
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO sorimemo_app;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO sorimemo_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO sorimemo_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO sorimemo_app;
SQL
```

`CHANGE_ME`는 실제 사용할 DB 비밀번호로 바꿔야 합니다.

## 2. 백엔드 실행 환경 전환

수동 실행 또는 cron/tmux에서 아래 환경변수를 추가합니다.

```bash
export SORIMEMO_DB_NAME=sorimemo_dev
export SORIMEMO_DB_USER=sorimemo_app
```

비밀번호 파일을 새 사용자 비밀번호로 맞춰야 합니다. 기존 `velora_app`용 파일과 분리하기 위해 새 파일을 사용합니다.

```bash
printf 'CHANGE_ME\n' > /home/scs_dev/velora/ops/generated-sorimemo-dev-db-password.txt
chmod 600 /home/scs_dev/velora/ops/generated-sorimemo-dev-db-password.txt
```

## 3. nginx 설정 파일명/경로 전환

현재 `/etc/nginx/sites-enabled/velora`를 바로 삭제하지 말고 새 설정을 먼저 검사합니다.

```bash
sudo cp /home/scs_dev/velora/ops/dev/nginx-sorimemo-dev-direct-api.conf /etc/nginx/sites-available/sorimemo
sudo ln -sf /etc/nginx/sites-available/sorimemo /etc/nginx/sites-enabled/sorimemo
sudo nginx -t
sudo systemctl reload nginx
```

새 설정 확인 후 기존 설정을 제거합니다.

```bash
sudo rm -f /etc/nginx/sites-enabled/velora
sudo nginx -t
sudo systemctl reload nginx
```

## 4. 관리자 API 보호 방식 확인

관리자 콘솔은 백엔드의 `/api/admin/login` 로그인과 bearer 토큰으로 보호합니다.
nginx의 `auth_basic`을 `/api/admin/`에 걸면 로그인 API가 HTML 401 응답을 반환해
프론트엔드에서 JSON 파싱 오류가 발생합니다.

추가 접근 제한이 필요하면 nginx Basic Auth 대신 IP allowlist 또는 VPN을 검토합니다.

## 5. systemd 서비스명 전환이 필요한 경우

개발 서버에서는 아직 백엔드가 systemd 서비스로 등록되어 있지 않을 수 있습니다.
등록한다면 새 이름을 사용합니다.

```bash
sudo nano /etc/systemd/system/sorimemo-backend.service
sudo systemctl daemon-reload
sudo systemctl enable sorimemo-backend
sudo systemctl start sorimemo-backend
sudo systemctl status sorimemo-backend
```

## 6. 확인

```bash
curl -k https://175.118.124.67/healthz
curl -k https://175.118.124.67/api/consent/policy
```
