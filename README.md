# SoriMemo

SoriMemo는 안심소리 기억케어 서비스의 개발 저장소입니다. 부모님 통화 음성 또는 본인 목소리를 기반으로 인지기능 변화 가능성을 참고용으로 확인하고, 관리자 콘솔에서 사용자, 음성 데이터, 분석 결과, 학습 동의 데이터를 관리합니다.

## 구성

- `velora-frontend/`: Vite + React 기반 서비스/관리자 화면
- `velora-backend/`: FastAPI 기반 API 서버
- `ops/`: 개발/운영 DB, Nginx, systemd, 배포 보조 스크립트
- `docs/`: SoriMemo 전환 및 운영 작업 문서

## 개발 실행

```bash
cd /home/scs_dev/velora
./ops/run_dev_backend.sh
```

```bash
cd /home/scs_dev/velora/velora-frontend
npm run dev
```

## 빌드

```bash
cd /home/scs_dev/velora/velora-frontend
npm run build
```

## 모델 파일

인지기능 분석 모델 바이너리(`*.h5`, `*.keras`, `*.onnx`, `*.pt`, `*.pth`)는 Git에 포함하지 않습니다. 서버에서는 `SORIMEMO_COGNITIVE_MODEL_PATH`와 `SORIMEMO_COGNITIVE_METADATA_PATH` 환경변수로 별도 배치한 모델 파일을 지정합니다.

## 주의

이 서비스의 분석 결과는 의료 진단이 아니라 참고 정보입니다. 정확한 진단은 전문 의료기관 검사를 통해 확인해야 합니다.
