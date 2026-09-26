"""视频管理页的视频列表缓存：userdata/video_cache/<媒体库Id>.json。

每个媒体库一个 JSON 文件（整包条目列表，含提取的番号），跟随 /app/data
挂载卷持久化，多浏览器共享。列表请求直接读缓存（内存过滤/排序/分页，
毫秒级）；点「刷新列表」才重新请求 Emby 全量并重提取番号更新此处。
"""

import json
import re
import time
from pathlib import Path
from typing import Any

from mdcx.config.resources import resources

_SAFE_ID = re.compile(r"[^A-Za-z0-9_-]")


def _cache_path(library_id: str) -> Path:
    safe = _SAFE_ID.sub("_", str(library_id)) or "_"
    return Path(resources.u("video_cache")) / f"{safe}.json"


def get_videos(library_id: str) -> tuple[float, str, list[dict[str, Any]]] | None:
    """返回 (updated_at epoch 秒, 生成口径 include_types, 视频列表)；无缓存返回 None。

    include_types 记录生成缓存时的条目类型口径（""=平铺视频，"Series"=按剧归组），
    供读取方校验缓存与当前请求口径一致。
    """
    path = _cache_path(library_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    videos = data.get("videos")
    if not isinstance(videos, list):
        return None
    return float(data.get("updated_at") or 0), str(data.get("include_types") or ""), videos


def _write(path: Path, data: dict[str, Any]) -> float:
    """原子写缓存文件，返回写入时的 updated_at epoch 秒。"""
    updated_at = time.time()
    data["updated_at"] = updated_at
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{int(updated_at * 1000)}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return updated_at


def set_videos(library_id: str, videos: list[dict[str, Any]], include_types: str = "") -> float:
    """写入视频列表缓存（原子写），返回 updated_at epoch 秒。"""
    path = _cache_path(library_id)
    return _write(path, {"include_types": include_types, "videos": videos})


def remove_video(library_id: str, item_id: str) -> bool:
    """从缓存中移除指定条目（删除视频后调用），返回是否命中移除。

    无缓存或条目不在缓存里时不改文件（此时整包刷新会自然对齐）。
    """
    path = _cache_path(library_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    videos = data.get("videos")
    if not isinstance(videos, list):
        return False
    kept = [v for v in videos if str(v.get("id") or "") != str(item_id)]
    if len(kept) == len(videos):
        return False
    data["videos"] = kept
    _write(path, data)
    return True
