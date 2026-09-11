"""配置 API：读/写/重置/多配置文件切换。

写路径复用 ConfigManager 的迁移与原子写语义：Config.update → validate →
_replace_config（热切换派生网络栈）→ save（原子落盘）。
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from mdcx.config.manager import manager
from mdcx.config.models import Config

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("")
def get_config():
    return {"config": manager.config.model_dump(mode="json"), "path": str(manager.path)}


@router.get("/schema")
def get_schema():
    """前端设置表单可用 JSON Schema 做字段元数据（描述/默认值/枚举）。"""
    return Config.model_json_schema()


@router.put("")
def put_config(body: dict):
    data = body.get("config")
    if not isinstance(data, dict):
        raise HTTPException(status_code=422, detail='请求体需为 {"config": {...}} 且包含完整配置')
    try:
        errors = Config.update(data)
        config = Config.model_validate(data)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"配置校验失败: {e}") from e
    manager._replace_config(config)
    manager.save()
    return {"ok": True, "errors": errors or []}


class SwitchRequest(BaseModel):
    name: str  # 配置文件名（位于当前配置目录内）


@router.post("/reset")
def reset_config():
    manager.reset()
    errors = manager.load()
    return {"ok": True, "errors": errors}


@router.get("/files")
def list_files():
    return {"files": manager.list_configs(), "current": manager.file}


@router.post("/switch")
def switch_config(req: SwitchRequest):
    target = (manager.path.parent / req.name).resolve()
    if target.parent != manager.path.parent or not target.is_file():
        raise HTTPException(status_code=404, detail=f"配置文件不存在: {req.name}")
    manager.path = target
    errors = manager.load()
    return {"ok": True, "errors": errors}
