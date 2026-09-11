"""FastAPI 应用工厂：REST API + WebSocket 实时推送 + 前端静态托管。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .routers import config as config_router
from .routers import media as media_router
from .routers import network as network_router
from .routers import scrape as scrape_router
from .routers import system as system_router
from .runtime import hub  # 导入 runtime 即完成无头总线切换（见 runtime.py 注释）


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    hub.attach()
    yield
    hub.detach()


def _frontend_dist() -> Path | None:
    """前端构建产物目录：MDCX_WEB_DIST 环境变量优先，其次源码树 frontend/dist。"""
    import os

    env = os.environ.get("MDCX_WEB_DIST")
    if env:
        p = Path(env)
        return p if (p / "index.html").is_file() else None
    repo = Path(__file__).resolve().parents[2]
    p = repo / "frontend" / "dist"
    return p if (p / "index.html").is_file() else None


def create_app() -> FastAPI:
    app = FastAPI(title="MDCx Web", version="2.0.9", lifespan=lifespan)
    # dev 模式 vite(5173) 直连后端；生产同源部署
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(scrape_router.router)
    app.include_router(config_router.router)
    app.include_router(media_router.router)
    app.include_router(network_router.router)
    app.include_router(system_router.router)

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket):
        await hub.connect(websocket)

    dist = _frontend_dist()
    if dist is not None:
        if (dist / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str):
            candidate = (dist / full_path).resolve()
            if full_path and candidate.is_file() and candidate.is_relative_to(dist.resolve()):
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

    return app


app = create_app()
