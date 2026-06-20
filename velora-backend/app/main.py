from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.config import env_bool, env_str
from app.routers import admin, auth, consent, upload, analysis, results

DEFAULT_CORS_ORIGINS = "https://localhost:5173,https://127.0.0.1:5173"


def _cors_origins() -> list[str]:
    if env_bool("SORIMEMO_CORS_ALLOW_ALL"):
        return ["*"]
    configured = env_str("SORIMEMO_CORS_ORIGINS", DEFAULT_CORS_ORIGINS)
    return [origin.strip() for origin in configured.split(",") if origin.strip()]


cors_origins = _cors_origins()

app = FastAPI(
    title="SoriMemo API",
    description="안심소리 기억케어 음성 기반 인지 변화 참고 서비스",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials="*" not in cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(consent.router, prefix="/api/consent", tags=["Consent & Governance"])
app.include_router(auth.router, prefix="/api/auth", tags=["Test Auth"])
app.include_router(upload.router, prefix="/api/upload", tags=["Upload & Quality Check"])
app.include_router(analysis.router, prefix="/api/analysis", tags=["Analysis Pipeline"])
app.include_router(results.router, prefix="/api/results", tags=["Results & Guidance"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin Console"])


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


# Serve frontend static files
STATIC_DIR = Path(__file__).parent.parent / "static"
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(request: Request, full_path: str):
        file_path = STATIC_DIR / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(STATIC_DIR / "index.html"))
