from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.v1 import auth, sessions, stream
from src.api.v1.stream import WebSocketHandshakeTimingMiddleware

app = FastAPI(
    title="L.U.V.E Core API",
    description="Hệ thống lõi cho hệ sinh thái học tiếng Anh AI",
    version="0.1.0",
)

# Cấu hình CORS - Cho phép Client truy cập (Rất quan trọng cho Phase 4)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Trong thực tế sẽ giới hạn domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(WebSocketHandshakeTimingMiddleware)

# Kết nối các "tuyến đường" đã xây dựng ở Phase 2
app.include_router(auth.router, prefix="/api/v1")
app.include_router(sessions.router, prefix="/api/v1")
app.include_router(stream.router)


@app.get("/")
async def root():
    return {
        "message": "Chào mừng Monty Finn đến với L.U.V.E API",
        "status": "Running",
        "docs": "/docs",
    }
