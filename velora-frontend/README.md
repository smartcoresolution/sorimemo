# SoriMemo Frontend

React + TypeScript + Vite frontend for smartphone voice recording/upload and 안심소리 기억케어 cognitive risk result display.

## Run

```bash
npm ci
npm run dev
```

Run the development server over HTTPS by providing a local certificate:

```bash
VITE_HTTPS_KEY=/path/to/dev.key
VITE_HTTPS_CERT=/path/to/dev.crt
npm run dev
```

Set the backend URL in `.env` only when the API is on a different HTTPS origin. In production, prefer same-origin `/api` through the HTTPS reverse proxy:

```bash
VITE_API_URL=https://api.example.com
```

## Build

```bash
npm run build
```
