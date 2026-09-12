"""服务器文件系统浏览 API：为前端"目录/文件选择弹窗"提供数据。

与桌面版文件对话框等价的信任模型（局域网单用户）：允许浏览任意已存在的目录，
只返回目录名/文件名（不读文件内容），路径校验仅要求目录真实存在。
"""

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

from mdcx.config.extend import parse_media_paths
from mdcx.config.manager import manager
from mdcx.webapp.paths import allowed_roots

router = APIRouter(prefix="/api/fs", tags=["fs"])


def _resolve(path: str) -> Path:
    p = Path(os.path.expanduser(path or "/")).resolve()
    if not p.is_dir():
        raise HTTPException(status_code=404, detail=f"目录不存在: {path}")
    return p


@router.get("/media-browse")
def media_browse(path: str = "", exts: str = ""):
    """在白名单目录内浏览媒体文件，导航不可越出白名单。

    path 为空时返回可用的根目录列表；exts（逗号分隔，如 ".nfo,.jpg"）可覆盖默认的
    媒体/字幕扩展名过滤。
    """
    from mdcx.config.manager import manager

    roots = [r for r in allowed_roots() if r.exists()]
    if not path:
        return {"roots": [str(r) for r in roots]}
    p = _resolve(path)
    if not any(p == r or p.is_relative_to(r) for r in roots):
        raise HTTPException(status_code=403, detail="路径不在允许访问的目录内")
    try:
        entries = list(os.scandir(p))
    except OSError as e:
        raise HTTPException(status_code=403, detail=f"目录无法读取: {e}") from e
    if exts.strip():
        media_exts = {e.strip().lower() for e in exts.split(",") if e.strip()}
    else:
        media_exts = {str(e).lower() for e in (*(manager.config.media_type or []), *(manager.config.sub_type or []))}
    dirs = sorted((e.name for e in entries if e.is_dir() and not e.name.startswith(".")), key=str.lower)
    files = sorted(
        (e.name for e in entries if e.is_file() and Path(e.name).suffix.lower() in media_exts),
        key=str.lower,
    )
    at_root = any(p == r for r in roots)
    return {
        "current": str(p),
        "parent": "" if at_root else str(p.parent),
        "dirs": dirs,
        "files": files,
    }


@router.get("/shortcuts")
def shortcuts():
    """快捷入口：主目录、配置数据目录、当前媒体目录。"""
    media = []
    try:
        media = [str(p) for p in parse_media_paths() if Path(p).exists()]
    except Exception:  # noqa: BLE001
        pass
    data_folder = Path(manager.data_folder)
    return {
        "home": str(Path.home()),
        "data_folder": str(data_folder) if data_folder.exists() else "",
        "media": media,
    }


@router.get("/browse")
def browse(path: str = "", with_files: bool = False):
    """列出目录内容。dirs 只含子目录；with_files 时附带文件列表。"""
    p = _resolve(path)
    try:
        entries = list(os.scandir(p))
    except OSError as e:
        raise HTTPException(status_code=403, detail=f"目录无法读取: {e}") from e
    dirs = sorted(
        (e.name for e in entries if e.is_dir() and not e.name.startswith(".")),
        key=str.lower,
    )
    files = []
    if with_files:
        files = sorted(
            (e.name for e in entries if e.is_file() and not e.name.startswith(".")),
            key=str.lower,
        )
    parent = str(p.parent) if p.parent != p else ""
    return {"current": str(p), "parent": parent, "dirs": dirs, "files": files}
