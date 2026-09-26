"""Emby 演员管理 API（包装无头的 tools/emby_actor_manager.py）。"""

import asyncio
import dataclasses
import re
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel

from mdcx.config.manager import manager
from mdcx.signals import signal
from mdcx.tools import emby_actor_manager as em
from mdcx.tools import emby_video_manager as emv
from mdcx.utils import executor
from mdcx.webapp import video_cache
from mdcx.webapp.jsonable import to_jsonable
from mdcx.webapp.paths import safe_path

router = APIRouter(prefix="/api/emby", tags=["emby"])


def _map_actor(item: dict) -> dict:
    """Emby /Persons 原始条目 → 前端表格结构。"""
    image_tags = item.get("ImageTags") or {}
    return {
        "name": item.get("Name", ""),
        "actor_id": item.get("Id", ""),
        "server_id": item.get("ServerId", ""),
        "has_image": bool(image_tags.get("Primary")),
        "has_overview": bool((item.get("Overview") or "").strip()),
        "movie_count": item.get("ChildCount") or 0,
    }


def _require_api_key() -> None:
    if not manager.config.api_key:
        raise HTTPException(status_code=400, detail="Emby API 密钥未填写，请在「软件设置 → 演员」页填写 API 密钥与用户 ID")


@router.post("/test")
async def test_connection():
    """连接测试：拉取 Emby 媒体库目录。"""
    _require_api_key()
    try:
        folders = await em.get_media_folders()
        return {"ok": True, "folders": to_jsonable(folders)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Emby 连接失败: {e}") from e


@router.get("/actors")
async def actors(filter_actor_only: bool = True):
    _require_api_key()
    try:
        result = await em.get_emby_actor_list(filter_actor_only=filter_actor_only)
        return {"actors": [_map_actor(item) for item in result]}
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"获取演员列表失败: {e}") from e


# region 视频管理（从 Emby 媒体库拉取视频条目）


@router.get("/libraries")
async def libraries():
    """媒体库列表（视频管理页的库选择下拉）。"""
    try:
        folders = await emv.get_media_libraries()
        return {
            "libraries": [
                {
                    "id": str(f.get("Id") or ""),
                    "name": f.get("Name", ""),
                    "type": f.get("CollectionType") or f.get("Type", ""),
                }
                for f in folders
            ]
        }
    except RuntimeError as e:
        raise HTTPException(status_code=400 if "未填写" in str(e) else 502, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"获取媒体库失败: {e}") from e


def _video_image_proxy_url(item_id: str, tag: str = "", max_width: int = 200) -> str:
    """前端可见的图片地址：本服务的相对代理路径（emby_url 与 api_key 留在后端，
    浏览器可能根本无法直连 emby_url——如 127.0.0.1/容器内地址）。tag 入查询串兼作缓存失效键。"""
    query = f"item_id={quote(str(item_id), safe='')}&max_width={max_width}"
    if tag:
        query += f"&tag={quote(tag, safe='')}"
    return f"/api/emby/video-image?{query}"


def _map_video(item: dict, with_number: bool = True) -> dict:
    """Emby /Items 原始条目 → 缓存行结构（含番号提取与图片代理 URL）。

    with_number=False 用于非默认库的直查路径（不做番号提取）。
    """
    image_tags = item.get("ImageTags") or {}
    item_id = str(item.get("Id") or "")
    has_image = bool(image_tags.get("Primary"))
    tag = str(image_tags.get("Primary") or "")
    path = item.get("Path") or ""
    return {
        "id": item_id,
        "name": item.get("Name", ""),
        "type": item.get("Type", ""),
        "number": _extract_number(path) if with_number else "",
        "year": item.get("ProductionYear"),
        "path": path,
        "size": item.get("Size") or 0,
        "provider_ids": item.get("ProviderIds") or {},
        "date_created": (item.get("DateCreated") or "")[:10],
        "has_image": has_image,
        "thumb": _video_image_proxy_url(item_id, tag) if has_image and item_id else "",
        "image": _video_image_proxy_url(item_id, tag, max_width=1200) if has_image and item_id else "",
    }


def _fix_cached_image_urls(rows: list[dict]) -> None:
    """就地修复旧缓存的图片地址：thumb/image 曾是直连 emby_url 的绝对地址（浏览器加载不到），
    从旧 URL 里抠出 tag 重写为相对代理地址；已是相对路径（新缓存）则不动。"""
    for row in rows:
        if not row.get("has_image") or not row.get("id"):
            continue
        thumb = str(row.get("thumb") or "")
        if thumb.startswith("/"):
            continue
        tag = ""
        if "?" in thumb:
            tag = (parse_qs(urlparse(thumb).query).get("tag") or [""])[0]
        row["thumb"] = _video_image_proxy_url(str(row["id"]), tag)
        row["image"] = _video_image_proxy_url(str(row["id"]), tag, max_width=1200)


def _extract_number(path: str) -> str:
    """从路径最后一项（文件名/目录名）提取番号，与正常刮削同一规则；提取不出为空串。"""
    if not path:
        return ""
    from mdcx.number import get_file_number

    try:
        return get_file_number(Path(path).name, manager.computed.escape_string_list) or ""
    except Exception:  # noqa: BLE001
        return ""


def _number_sort_key(number: str) -> tuple[tuple[int, Any], ...]:
    """番号自然排序：数字段按数值、字母段按字典序（IPX-9 < IPX-100）。"""
    return tuple(
        (1, int(part)) if part.isdigit() else (0, part)
        for part in re.split(r"(\d+)", number.upper())
    )


def _sort_videos(rows: list[dict]) -> None:
    """有番号的在前按番号自然排序，无番号的在后按名称。"""
    rows.sort(
        key=lambda v: (
            0 if v["number"] else 1,
            _number_sort_key(v["number"]) if v["number"] else ((0, v["name"].upper()),),
            v["name"].upper(),
        )
    )


def _dup_key(number: str) -> str:
    return str(number or "").strip().upper()


def _filter_duplicates(rows: list[dict]) -> list[dict]:
    """筛出番号在整库缓存里出现多次的条目（大小写不敏感；无番号不参与计数）。

    在缓存全量上计数后再过滤，保持缓存原有排序，同番号条目相邻展示。
    """
    counts = Counter(_dup_key(v.get("number")) for v in rows if _dup_key(v.get("number")))
    return [v for v in rows if counts[_dup_key(v.get("number"))] > 1]


async def _refresh_library_cache(parent_id: str, library_type: str) -> float:
    """Emby 全量拉取 + 提取番号 + 排序 + 写缓存，返回缓存时间戳。"""
    include_types = "Series" if library_type == "tvshows" else None
    items = await emv.get_all_video_items(parent_id, include_types)
    rows = await asyncio.to_thread(_build_video_rows, items)
    return video_cache.set_videos(parent_id, rows, include_types or "")


def _build_video_rows(items: list[dict]) -> list[dict]:
    rows = [_map_video(item) for item in items]
    _sort_videos(rows)
    return rows


# 每个媒体库一把全量刷新锁：并发进页面/点刷新只触发一次 Emby 全量拉取
_REFRESH_LOCKS: dict[str, asyncio.Lock] = {}


def _library_lock(parent_id: str) -> asyncio.Lock:
    lock = _REFRESH_LOCKS.get(parent_id)
    if lock is None:
        lock = _REFRESH_LOCKS.setdefault(parent_id, asyncio.Lock())
    return lock


def _default_library_id() -> str:
    """设置里保存的视频库 Id；番号提取与缓存只对它生效。"""
    return str(manager.config.video_library_id or "").strip()


@router.get("/videos")
async def videos(
    parent_id: str = Query(..., min_length=1),
    start_index: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=1000),
    keyword: str = "",
    library_type: str = "",
    duplicates_only: bool = Query(False),
):
    """tvshows 库按 Series（剧）归组，其余平铺视频条目。

    仅当 parent_id 是「软件设置 → 服务器」配置的视频库时：走番号提取 + 缓存
    （无缓存自动全量拉取一次，keyword 在缓存上做名称/番号/路径过滤，番号排序）。
    duplicates_only=True 时先在缓存全量上计数，只返回番号出现多次的条目。
    其他库（或未配置视频库）为轻量直查：Emby 服务端分页，不提取番号、不落缓存
    （duplicates_only 无意义，忽略）。
    """
    try:
        include_types = "Series" if library_type == "tvshows" else None
        if parent_id != _default_library_id():
            items, total = await emv.get_video_items(parent_id, start_index, limit, keyword, include_types)
            return {
                "total": total,
                "cached": False,
                "ts": 0,
                "videos": [_map_video(item, with_number=False) for item in items],
            }

        expected_types = include_types or ""
        cached = video_cache.get_videos(parent_id)
        refreshed_now = False
        if cached is not None and cached[1] != expected_types:
            cached = None  # 缓存口径（平铺/按剧归组）与当前请求不一致，按当前口径重拉
        if cached is None:
            async with _library_lock(parent_id):
                cached = video_cache.get_videos(parent_id)
                if cached is not None and cached[1] != expected_types:
                    cached = None
                if cached is None:
                    ts = await _refresh_library_cache(parent_id, library_type)
                    got = video_cache.get_videos(parent_id)
                    cached = (ts, expected_types, got[2] if got else [])
                    refreshed_now = True
        ts, _type, all_rows = cached
        _fix_cached_image_urls(all_rows)  # 旧缓存可能存的是直连 emby_url 的绝对图片地址
        if duplicates_only:
            all_rows = _filter_duplicates(all_rows)
        kw = keyword.strip().lower()
        if kw:
            all_rows = [
                v
                for v in all_rows
                if kw in v["name"].lower() or kw in v["number"].lower() or kw in v["path"].lower()
            ]
        total = len(all_rows)
        return {
            "total": total,
            "cached": not refreshed_now,
            "ts": ts,
            "videos": all_rows[start_index : start_index + limit],
        }
    except RuntimeError as e:
        raise HTTPException(status_code=400 if "未填写" in str(e) else 502, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"获取视频列表失败: {e}") from e


@router.get("/video-image")
async def video_image(
    item_id: str = Query(..., min_length=1),
    max_width: int = Query(200, ge=16, le=2000),
    tag: str = "",
):
    """代理 Emby 条目图片：浏览器不直连 emby_url（可能是 127.0.0.1/容器内地址）。"""
    try:
        data, content_type, err = await emv.fetch_video_image(item_id, max_width, tag)
    except RuntimeError as e:
        raise HTTPException(status_code=400 if "未填写" in str(e) else 502, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"获取图片失败: {e}") from e
    if data is None:
        raise HTTPException(status_code=404, detail=f"获取图片失败: {err}")
    return Response(
        content=data,
        media_type=content_type or "image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},  # tag 变化即换 URL，天然失效
    )


class VideoRefresh(BaseModel):
    parent_id: str
    library_type: str = ""


@router.post("/videos/refresh")
async def videos_refresh(req: VideoRefresh):
    """强制重新从 Emby 拉取全量、重提取番号并更新缓存（「刷新列表」按钮，仅配置的视频库）。"""
    if req.parent_id != _default_library_id():
        raise HTTPException(
            status_code=400,
            detail="仅「软件设置 → 服务器」配置的视频库支持刷新缓存",
        )
    try:
        async with _library_lock(req.parent_id):
            ts = await _refresh_library_cache(req.parent_id, req.library_type)
        return {"ok": True, "ts": ts}
    except RuntimeError as e:
        raise HTTPException(status_code=400 if "未填写" in str(e) else 502, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"刷新视频列表失败: {e}") from e


class VideoDelete(BaseModel):
    parent_id: str
    item_id: str


@router.post("/videos/delete")
async def videos_delete(req: VideoDelete):
    """从 Emby 删除视频并把条目移出列表缓存（仅配置的视频库开放）。

    删除期间持有库锁，避免与全量刷新并发导致已删条目重新回到缓存；
    源文件是否一并删除取决于 Emby/Jellyfin 服务器自身的删除设置。
    """
    if req.parent_id != _default_library_id():
        raise HTTPException(status_code=400, detail="仅「软件设置 → 服务器」配置的视频库支持删除")
    if not req.item_id:
        raise HTTPException(status_code=422, detail="缺少视频条目 Id")
    try:
        async with _library_lock(req.parent_id):
            ok, msg = await emv.delete_video_item(req.item_id)
            if ok:
                video_cache.remove_video(req.parent_id, req.item_id)
        if not ok:
            raise HTTPException(status_code=502, detail=msg)
        return {"ok": True, "message": msg}
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=400 if "未填写" in str(e) else 502, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"删除视频失败: {e}") from e


# endregion


# region 演员列表缓存（userdata/actor_cache.db，跨浏览器共享、随挂载卷持久化）


@router.get("/actors-cache")
def actors_cache():
    from mdcx.webapp.actor_cache import get_actors

    row = get_actors()
    if row is None:
        return {"cached": False, "ts": 0, "actors": []}
    ts, value = row
    return {"cached": True, "ts": ts, "actors": value}


@router.put("/actors-cache")
def save_actors_cache(body: dict):
    from mdcx.webapp.actor_cache import set_actors

    value = body.get("actors")
    if not isinstance(value, list):
        raise HTTPException(status_code=422, detail='请求体需为 {"actors": [...]}')
    ts = set_actors(value)
    return {"ok": True, "ts": ts}


# endregion


# endregion


@router.get("/actor/detail")
async def actor_detail(name: str):
    try:
        detail = await em.fetch_actor_detail(name)
        if detail is None:
            raise HTTPException(status_code=404, detail=f"未找到演员: {name}")
        return to_jsonable(detail)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"获取演员详情失败: {e}") from e


class ActorUpdate(BaseModel):
    actor: dict  # ActorInfo 字段子集（name/actor_id/server_id 必填）
    image_path: str = ""  # 本地图片路径（可选，同时上传头像）


@router.post("/actor/update")
async def actor_update(req: ActorUpdate):
    valid_fields = {f.name for f in dataclasses.fields(em.ActorInfo)}
    kwargs = {k: v for k, v in req.actor.items() if k in valid_fields}
    if not kwargs.get("name"):
        raise HTTPException(status_code=422, detail="actor.name 必填")
    if req.image_path:
        kwargs["new_image_path"] = safe_path(req.image_path)
    info = em.ActorInfo(**kwargs)

    async def _run():
        if info.new_image_path:
            ok, msg = await em.upload_actor_image(info, str(info.new_image_path))
            signal.show_log_text(f"{'✅' if ok else '🔴'} 头像上传 {info.name}: {msg}")
        ok, msg = await em.update_person_info(info)
        signal.show_log_text(f"{'✅' if ok else '🔴'} 演员更新 {info.name}: {msg}")

    executor.submit(_run())
    return {"ok": True, "queued": True}


class ActorImageRequest(BaseModel):
    actor: dict
    image_path: str = ""


@router.post("/actor/upload-image-file")
async def actor_upload_image_file(
    request: Request,
    name: str = Query(...),
    actor_id: str = Query(""),
    server_id: str = Query(""),
    filename: str = Query("avatar.jpg"),
):
    """直接上传本地图片作为演员头像（raw body，图片二进制）。"""
    import time

    import aiofiles

    from mdcx.config.manager import manager

    if not name.strip():
        raise HTTPException(status_code=422, detail="演员名必填")
    if not actor_id:
        raise HTTPException(status_code=422, detail="缺少演员 ItemId")
    body = await request.body()
    if not body:
        raise HTTPException(status_code=422, detail="未收到图片数据")
    if len(body) > 20 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="头像图片不能超过 20MB")
    ext = Path(filename).suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        raise HTTPException(status_code=422, detail=f"不支持的图片格式: {ext or '(缺扩展名)'}")

    info = em.ActorInfo(name=name.strip(), actor_id=actor_id, server_id=server_id)
    tmp = manager.data_folder / f".[avatar]{int(time.time() * 1000)}{ext}"
    tmp.write_bytes(body)
    try:
        ok, msg = await em.upload_actor_image(info, str(tmp))
        return {"ok": ok, "message": msg}
    finally:
        tmp.unlink(missing_ok=True)


@router.post("/actor/upload-image")
async def actor_upload_image(req: ActorImageRequest):
    valid_fields = {f.name for f in dataclasses.fields(em.ActorInfo)}
    kwargs = {k: v for k, v in req.actor.items() if k in valid_fields}
    if not kwargs.get("name"):
        raise HTTPException(status_code=422, detail="actor.name 必填")
    if req.image_path:
        kwargs["new_image_path"] = safe_path(req.image_path)
    info = em.ActorInfo(**kwargs)
    try:
        ok, msg = await em.upload_actor_image(info, str(info.new_image_path or ""))
        return {"ok": ok, "message": msg}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/actor/delete-image")
async def actor_delete_image(req: ActorImageRequest):
    valid_fields = {f.name for f in dataclasses.fields(em.ActorInfo)}
    kwargs = {k: v for k, v in req.actor.items() if k in valid_fields}
    if not kwargs.get("name"):
        raise HTTPException(status_code=422, detail="actor.name 必填")
    info = em.ActorInfo(**kwargs)
    try:
        ok, msg = await em.delete_actor_image(info)
        return {"ok": ok, "message": msg}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(e)) from e
