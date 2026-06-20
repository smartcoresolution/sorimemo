# VELORA 운영 서버 복구 런북

작성일: 2026-05-29

## 핵심 판단

해킹이 의심되는 서버는 단순 패키지 재설치만으로 신뢰하기 어렵습니다. 가능하면 클라우드/호스팅 콘솔에서 새 OS 이미지로 재설치하거나 새 VM을 만든 뒤, 소스와 모델만 다시 배포하는 방식을 권장합니다. 기존 서버에서 바로 재구축해야 한다면 먼저 스냅샷 또는 디스크 이미지를 남기고, 증거 보존이 필요 없는 경우에만 삭제 작업을 진행하세요.

## 즉시 조치

1. 서버 외부 접근 차단 또는 방화벽에서 22, 80, 443, 8080만 임시 허용
2. SSH 비밀번호/키, DB 비밀번호, API 환경변수, 호스팅 콘솔 비밀번호 전부 교체
3. 기존 DB/업로드 파일이 필요하면 `/var/lib/postgresql`, `/opt/velora-prod/uploads`, `/etc/velora-prod-api.env`, `/etc/nginx/sites-available/velora` 백업
4. 운영 OS 재설치 또는 새 서버 생성
5. 이 저장소의 `ops/prod/rebuild_prod.sh`로 운영 구성 재생성

## 재구축 실행 예시

아래 명령은 `miniconda3`, conda env, 운영 서비스 설정을 다시 만듭니다. DB 비밀번호는 반드시 새 값으로 넣으세요.

```bash
cd /root/velora
chmod +x ops/prod/rebuild_prod.sh
CONFIRM_REBUILD=YES DB_PASSWORD='새로운_강한_DB_비밀번호' ./ops/prod/rebuild_prod.sh
```

스크립트 기본값:

```text
APP_ROOT=/root/velora
PROD_ROOT=/opt/velora-prod
CONDA_HOME=/root/velora/tools/miniconda3
BACKEND_ENV=/root/velora/tools/conda-envs/velora-backend
FRONTEND_ENV=/root/velora/tools/conda-envs/velora-frontend
DB_NAME=velora_prod
DB_USER=velora_app
SERVER_NAME=175.118.124.67
```

## 수동 검증

```bash
systemctl status postgresql
systemctl status velora-prod-api
systemctl status nginx
nginx -t
curl http://127.0.0.1:8010/healthz
curl http://127.0.0.1:8010/api/analysis/model-status
curl http://175.118.124.67/healthz
```

## 관리자 API

관리자 API는 Nginx Basic Auth로 보호합니다.

```text
사용자: velora_admin
비밀번호 파일: /root/velora/ops/prod/secrets/generated-admin-password.txt
Nginx htpasswd: /etc/nginx/.velora-admin.htpasswd
```

비밀번호 파일은 root 전용 권한으로 보관하세요.

## DB만 다시 만들 때

```bash
sudo -u postgres psql -d velora_prod -f /root/velora/ops/prod/prod_schema.sql
```

## 백업

일일 백업은 `/etc/cron.daily/velora-prod-backup`에 등록되어 있습니다.

```bash
/root/velora/ops/prod/backup_prod.sh
```

백업 위치:

```text
/root/velora/backups/prod/YYYYMMDD-HHMMSS
```

기본 보관 기간은 14일입니다. `RETENTION_DAYS` 환경변수로 조정할 수 있습니다.

## 방화벽

UFW 기본 정책은 inbound deny, outbound allow입니다.

허용 포트:

```text
22/tcp
80/tcp
443/tcp
8080/tcp
```

## 복구 후 꼭 해야 할 일

1. `/etc/velora-prod-api.env` 권한 확인: `chmod 600 /etc/velora-prod-api.env`
2. PostgreSQL이 외부에 열리지 않았는지 확인: `ss -lntp | grep 5432`
3. 관리자 API 인증 확인: `curl -i http://175.118.124.67/api/admin/dashboard`
4. HTTPS 인증서 적용
5. 백업 정상 생성 확인: `/root/velora/ops/prod/backup_prod.sh`
6. `/var/log/auth.log`, `journalctl`, Nginx access/error log를 확인해 침입 경로 조사
