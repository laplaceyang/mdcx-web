"""媒体文件服务：图片预览 / 视频流播放 / 任意受控文件读取。

路径安全：只允许访问「刮削配置的媒体目录」与「配置/用户数据目录」内的文件，
越界一律 403。
"""

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

from mdcx.config.extend import parse_media_paths
from mdcx.config.manager import manager

router = APIRouter(prefix="/api/media", tags=["media"])

_CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".mp4": "video/mp4",
    ".mkv": "video/x-matroska",
    ".wmv": "video/x-ms-wmv",
    ".avi": "video/x-msvideo",
    ".mov": "video/quicktime",
    ".ts": "video/mp2t",
    ".nfo": "text/xml; charset=utf-8",
}

_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)$")


def _allowed_roots() -> list[Path]:
    roots: list[Path] = []
    try:
        roots.extend(Path(p) for p in parse_media_paths())
    except Exception:  # noqa: BLE001 媒体目录配置异常时仍允许访问配置目录
        pass
    roots.append(Path(manager.data_folder))
    return roots


def _safe_path(path_str: str) -> Path:
    p = Path(path_str).resolve()
    if not p.is_file():
        raise HTTPException(status_code=404, detail=f"文件不存在: {path_str}")
    for root in _allowed_roots():
        try:
            p.relative_to(Path(root).resolve())
            return p
        except ValueError:
            continue
    raise HTTPException(status_code=403, detail="路径不在允许访问的目录内")


def _content_type(p: Path) -> str:
    return _CONTENT_TYPES.get(p.suffix.lower(), "application/octet-stream")


@router.get("/file")
def get_file(path: str):
    """图片 / NFO 等小文件直接返回。"""
    p = _safe_path(path)
    return FileResponse(p, media_type=_content_type(p))


@router.get("/video")
def get_video(path: str, request: Request):
    """视频播放，支持 Range 分段请求（浏览器 <video> 拖动进度条）。"""
    p = _safe_path(path)
    file_size = p.stat().st_size
    range_header = request.headers.get("range")
    if not range_header:
        return FileResponse(p, media_type=_content_type(p))

    match = _RANGE_RE.match(range_header.strip())
    if not match:
        raise HTTPException(status_code=416, detail="不支持的 Range 头")
    start_s, end_s = match.groups()
    start = int(start_s) if start_s else 0
    end = int(end_s) if end_s else min(start + 4 * 1024 * 1024, file_size - 1)  # 默认 4MB 分片
    end = min(end, file_size - 1)
    if start > end or start >= file_size:
        raise HTTPException(status_code=416, detail="Range 超出文件大小")

    chunk_size = 256 * 1024

    def iterator():
        with open(p, "rb") as f:
            f.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                data = f.read(min(chunk_size, remaining))
                if not data:
                    break
                remaining -= len(data)
                yield data

    return StreamingResponse(
        iterator(),
        status_code=206,
        media_type=_content_type(p),
        headers={
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(end - start + 1),
        },
    )
