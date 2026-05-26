from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.api.v1 import auth, sessions, stream
from src.api.v1.stream import WebSocketHandshakeTimingMiddleware
from src.core.cors import get_cors_allow_origins

_STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="L.U.V.E Core API",
    description="Hệ thống lõi cho hệ sinh thái học tiếng Anh AI",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_allow_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.add_middleware(WebSocketHandshakeTimingMiddleware)

app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

# Kết nối các "tuyến đường" đã xây dựng ở Phase 2
app.include_router(auth.router, prefix="/api/v1")
app.include_router(sessions.router, prefix="/api/v1")
app.include_router(stream.router)


@app.get("/control-center", include_in_schema=False)
async def control_center() -> FileResponse:
    return FileResponse(_STATIC_DIR / "index.html")


@app.get("/")
async def root():
    return {
        "message": "Chào mừng Monty Finn đến với L.U.V.E API",
        "status": "Running",
        "docs": "/docs",
    }
