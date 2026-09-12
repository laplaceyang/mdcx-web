"""Emby 演员管理 API（包装无头的 tools/emby_actor_manager.py）。"""

import dataclasses
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from mdcx.config.manager import manager
from mdcx.signals import signal
from mdcx.tools import emby_actor_manager as em
from mdcx.utils import executor
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
