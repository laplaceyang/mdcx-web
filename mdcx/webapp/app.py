"""FastAPI 应用工厂：REST API + WebSocket 实时推送 + 前端静态托管。

访问控制：设置环境变量 MDCX_WEB_TOKEN 后，/api 与 /ws 需要携带令牌
（Authorization: Bearer <token> 或 ?token=<token>）；未设置时信任局域网。
"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .routers import config as config_router
from .routers import fs as fs_router
from .routers import media as media_router
from .routers import network as network_router
from .routers import nfo as nfo_router
from .routers import scrape as scrape_router
from .routers import system as system_router
from .routers import tools as tools_router
from .runtime import hub  # 导入 runtime 即完成无头总线切换（见 runtime.py 注释）


def _web_token() -> str:
    return os.environ.get("MDCX_WEB_TOKEN", "")


def _check_token(supplied: str) -> bool:
    token = _web_token()
    return not token or supplied == token


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    hub.attach()
    yield
    hub.detach()


def _frontend_dist() -> Path | None:
    """前端构建产物目录：MDCX_WEB_DIST 环境变量优先，其次源码树 frontend/dist。"""
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

    @app.middleware("http")
    async def token_auth(request, call_next):
        if _web_token() and request.url.path.startswith(("/api", "/ws")):
            supplied = request.query_params.get("token", "")
            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                supplied = auth_header[len("Bearer ") :]
            if not _check_token(supplied):
                return JSONResponse({"detail": "未授权：缺少或错误的访问令牌"}, status_code=401)
        return await call_next(request)

    app.include_router(scrape_router.router)
    app.include_router(config_router.router)
    app.include_router(fs_router.router)
    app.include_router(media_router.router)
    app.include_router(network_router.router)
    app.include_router(nfo_router.router)
    app.include_router(tools_router.router)
    app.include_router(system_router.router)

    from .routers import emby as emby_router

    app.include_router(emby_router.router)

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket, token: str = Query("")):
        if not _check_token(token):
            await websocket.close(code=4401)
            return
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
