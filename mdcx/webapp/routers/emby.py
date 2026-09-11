"""Emby 演员管理 API（包装无头的 tools/emby_actor_manager.py）。"""

import dataclasses

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from mdcx.signals import signal
from mdcx.tools import emby_actor_manager as em
from mdcx.utils import executor
from mdcx.webapp.jsonable import to_jsonable
from mdcx.webapp.paths import safe_path

router = APIRouter(prefix="/api/emby", tags=["emby"])


@router.post("/test")
async def test_connection():
    """连接测试：拉取 Emby 媒体库目录。"""
    try:
        folders = await em.get_media_folders()
        return {"ok": True, "folders": to_jsonable(folders)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Emby 连接失败: {e}") from e


@router.get("/actors")
async def actors(filter_actor_only: bool = True):
    try:
        result = await em.get_emby_actor_list(filter_actor_only=filter_actor_only)
        return {"actors": to_jsonable(result)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"获取演员列表失败: {e}") from e


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
