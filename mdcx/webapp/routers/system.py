"""系统信息 API：版本 / 更新检查 / 运行环境。"""

import platform
import sys

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool

from mdcx.consts import GITHUB_REPO, LOCAL_VERSION, VERSION_NAME

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/version")
def version():
    return {"version_name": VERSION_NAME, "local_version": LOCAL_VERSION, "repo": GITHUB_REPO}


@router.get("/check-update")
async def check_update():
    """检查 GitHub 最新版本号（同步 HTTP，放线程池避免阻塞事件循环）。"""
    from mdcx.base.web import check_version

    latest = await run_in_threadpool(check_version)
    return {"local_version": LOCAL_VERSION, "latest": latest, "has_new": bool(latest and latest > LOCAL_VERSION)}


@router.get("/info")
def info():
    from mdcx.config.manager import manager
    from mdcx.consts import MAIN_PATH, SYSTEM_INFO
    from mdcx.webapp.runtime import hub

    return {
        "version_name": VERSION_NAME,
        "system": SYSTEM_INFO,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "main_path": str(MAIN_PATH),
        "config_path": str(manager.path),
        "data_folder": str(manager.data_folder),
        "ws_clients": len(hub._clients),
    }
