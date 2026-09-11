"""路径安全：web API 只允许访问媒体目录与配置/用户数据目录内的文件。"""

from pathlib import Path

from fastapi import HTTPException

from mdcx.config.extend import parse_media_paths
from mdcx.config.manager import manager


def allowed_roots() -> list[Path]:
    roots: list[Path] = []
    try:
        roots.extend(Path(p) for p in parse_media_paths())
    except Exception:  # noqa: BLE001 媒体目录配置异常时仍允许访问配置目录
        pass
    roots.append(Path(manager.data_folder))
    return roots


def safe_path(path_str: str) -> Path:
    p = Path(path_str).resolve()
    if not p.is_file():
        raise HTTPException(status_code=404, detail=f"文件不存在: {path_str}")
    for root in allowed_roots():
        try:
            p.relative_to(Path(root).resolve())
            return p
        except ValueError:
            continue
    raise HTTPException(status_code=403, detail="路径不在允许访问的目录内")
