from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import signal
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.core.config import settings
from src.realtime.adapters.ten_compat import (
    TEN_SINGLE_SESSION_CAPACITY,
    TenEnvAdapter,
    WebRTCGatewayManager,
)
from src.realtime.contracts import CmdRequest, IceRequest, OfferRequest, OfferResponse
from src.ten_ext.luve_extension import LUVEExtension


logger = logging.getLogger("run_ten")
logging.basicConfig(level=logging.INFO)

# Suppress noisy ICE logs
logging.getLogger("aioice").setLevel(logging.WARNING)
logging.getLogger("aiortc").setLevel(logging.WARNING)

ROOT_DIR = Path(__file__).resolve().parent
GRAPH_PATH = ROOT_DIR / "graph.json"
LUVE_PROPERTY_PATH = ROOT_DIR / "src" / "ten_ext" / "property.json"
STATIC_DIR = ROOT_DIR / "src" / "static"


def _load_graph() -> dict[str, Any]:
    return json.loads(GRAPH_PATH.read_text(encoding="utf-8"))


def _load_luve_properties() -> dict[str, Any]:
    return json.loads(LUVE_PROPERTY_PATH.read_text(encoding="utf-8"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    graph = _load_graph()
    luve_props = _load_luve_properties()
    webrtc_props = next(
        node["properties"] for node in graph["nodes"] if node["id"] == "webrtc_gateway"
    )
    if settings.max_webrtc_sessions > TEN_SINGLE_SESSION_CAPACITY:
        logger.warning(
            "MAX_WEBRTC_SESSIONS=%s capped to %s because LUVEExtension is single-session",
            settings.max_webrtc_sessions,
            TEN_SINGLE_SESSION_CAPACITY,
        )

    extension = LUVEExtension()
    gateway = WebRTCGatewayManager(extension)
    adapter = TenEnvAdapter(
        loop=asyncio.get_running_loop(),
        gateway=gateway,
        properties=luve_props,
    )
    await extension.start_async(adapter)

    app.state.graph = graph
    app.state.webrtc_props = webrtc_props
    app.state.gateway = gateway
    app.state.luve_extension = extension

    try:
        yield
    finally:
        with contextlib.suppress(Exception):
            await extension.stop_async()
        await gateway.close_all()

app = FastAPI(title="L.U.V.E TEN Gateway", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Cấp quyền CORS cho các trạm bên ngoài (Port 8000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/rtc/graph")
async def get_graph() -> dict[str, Any]:
    return app.state.graph


@app.get("/control-center", response_class=FileResponse)
async def control_center() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz():
    """Readiness probe: 200 once lifespan has initialized the gateway manager.

    Liveness stays on /healthz. This checks only in-process startup state — no
    DB ping, no Groq/STT/model calls, no WebRTC hot-path interaction.
    """
    gateway = getattr(app.state, "gateway", None)
    if gateway is not None:
        return {"status": "ready", "checks": {"gateway": "initialized"}}
    return JSONResponse(
        status_code=503,
        content={"status": "not_ready", "checks": {"gateway": "uninitialized"}},
    )


@app.get("/rtc/health")
async def rtc_health() -> dict[str, Any]:
    return await app.state.gateway.get_runtime_snapshot()


@app.post("/rtc/offer", response_model=OfferResponse)
async def rtc_offer(
    request: OfferRequest,
    authorization: str | None = Header(default=None),
) -> OfferResponse:
    await app.state.gateway.assert_session_owner(request.session_id or "", authorization)
    return await app.state.gateway.create_session(request)


@app.post("/rtc/ice")
async def rtc_ice(
    request: IceRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    await app.state.gateway.assert_session_owner(request.session_id, authorization)
    await app.state.gateway.add_ice_candidate(request)
    return {"status": "ok"}


@app.post("/rtc/cmd")
async def rtc_cmd(
    request: CmdRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    await app.state.gateway.assert_session_owner(request.session_id, authorization)
    command = request.cmd.strip().upper()
    if command == "BARGE_IN":
        await app.state.gateway.flush_outbound_audio(request.session_id)
    payload = {
        "session_id": request.session_id,
        "command": command,
        "source": request.source,
    }
    app.state.luve_extension.on_cmd(payload)
    return {"status": "ok", "cmd": command}


def main() -> None:
    server = uvicorn.Server(
        uvicorn.Config(
            app="run_ten:app",
            host="0.0.0.0",
            port=8080,
            log_level="info",
        )
    )

    def _handle_exit(signum: int, _frame: Any) -> None:
        logger.info("signal.received signum=%s, stopping TEN gateway", signum)
        server.handle_exit(signum, _frame)

    signal.signal(signal.SIGINT, _handle_exit)
    signal.signal(signal.SIGTERM, _handle_exit)
    server.run()


if __name__ == "__main__":
    main()
