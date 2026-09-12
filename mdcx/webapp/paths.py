"""路径安全：web API 只允许访问「配置中出现的目录」内的文件。

白名单 = 媒体路径（支持 | 多路径）+ 软链接/成功输出/失败输出/字幕/演员照片/
Gfriends 等配置目录 + 配置数据目录。只取绝对路径（相对路径的解析位置随运行
目录变化，无法可靠防护，不在白名单内）。
"""

from pathlib import Path

from fastapi import HTTPException

from mdcx.config.extend import parse_media_paths
from mdcx.config.manager import manager

# 配置中的目录类字段（值可能是 | 分隔的多路径）
_PATH_CONFIG_KEYS = (
    "softlink_path",
    "success_output_folder",
    "failed_output_folder",
    "subtitle_folder",
    "actor_photo_folder",
    "gfriends_local_path",
)


def allowed_roots() -> list[Path]:
    roots: list[Path] = []
    try:
        roots.extend(Path(p) for p in parse_media_paths())
    except Exception:  # noqa: BLE001 媒体目录配置异常时仍允许访问配置目录
        pass
    for key in _PATH_CONFIG_KEYS:
        value = str(getattr(manager.config, key, "") or "")
        for part in value.split("|"):
            part = part.strip()
            if part.startswith("/"):
                roots.append(Path(part))
    roots.append(Path(manager.data_folder))

    unique: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        try:
            resolved = Path(root).resolve()
        except OSError:
            continue
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return unique


def safe_path(path_str: str) -> Path:
    p = Path(path_str).resolve()
    if not p.is_file():
        raise HTTPException(status_code=404, detail=f"文件不存在: {path_str}")
    for root in allowed_roots():
        try:
            p.relative_to(root)
            return p
        except ValueError:
            continue
    raise HTTPException(status_code=403, detail="路径不在允许访问的目录内")
