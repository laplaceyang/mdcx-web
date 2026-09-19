"""配置 API：读/写/重置/多配置文件切换。

写路径复用 ConfigManager 的迁移与原子写语义：Config.update → validate →
_replace_config（热切换派生网络栈）→ save（原子落盘）。
"""

import enum as _enum
from pathlib import Path as _Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from mdcx.config import enums as _config_enums
from mdcx.config.manager import manager
from mdcx.config.models import Config
from mdcx.core.naming.renderer import NamingTarget, NameRenderOptions, render_name
from mdcx.models.model_types import CrawlersResult, FileInfo

router = APIRouter(prefix="/api/config", tags=["config"])

# 工作模式/更新方式的选项文案：纯展示元数据，挂在 schema 的 x-options 上供前端渲染卡片
_MAIN_MODE_OPTIONS = [
    {"value": 1, "label": "整理模式", "description": "从输入目录刮削，按「命名格式」模板整理进输出目录（日常用这个）"},
    {"value": 2, "label": "视频模式", "description": "轻量整理：按番号命名归类到目录，配合开关清理旧 poster/thumb/nfo"},
    {"value": 3, "label": "更新模式", "description": "库已整理好：位置按「更新方式」决定，只刷新 NFO/图片等元数据"},
    {"value": 4, "label": "读取模式", "description": "不联网：直接读已有 NFO 补数据；没有 NFO 时按「读取模式选项」决定是否刮削"},
]
_UPDATE_MODE_OPTIONS = [
    {"value": "c", "label": "原地刷新", "code": "C", "description": "文件夹不动，只更新 NFO/图片"},
    {"value": "bc", "label": "移到上级目录", "code": "BC", "description": "在视频所在目录的上一级，按「番号目录模板（B）」新建"},
    {"value": "abc", "label": "重建两级目录", "code": "ABC", "description": "在上两级，按「第一级模板（A）/番号目录模板（B）」两层重建"},
    {"value": "d", "label": "目录内新建子目录", "code": "D", "description": "在当前文件夹里，按「子目录模板（D）」再套一层"},
]
_FIELD_OPTIONS = {"main_mode": _MAIN_MODE_OPTIONS, "update_mode": _UPDATE_MODE_OPTIONS}


@router.get("")
def get_config():
    return {"config": manager.config.model_dump(mode="json"), "path": str(manager.path)}


@router.get("/schema")
def get_schema():
    """前端设置表单可用 JSON Schema 做字段元数据（描述/默认值/枚举）。

    附加展示元数据：x-options（工作模式/更新方式的选项卡片）、
    x-enum-names（枚举的中文名，来自各 Enum.names()，与取值按序对齐）。
    """
    schema = Config.model_json_schema()
    for name, defn in (schema.get("$defs") or {}).items():
        cls = getattr(_config_enums, name, None)
        if not (isinstance(cls, type) and issubclass(cls, _enum.Enum)):
            continue
        names_fn = getattr(cls, "names", None)
        if not callable(names_fn):
            continue
        try:
            labels = names_fn()
            if len(labels) == len(cls):
                defn["x-enum-names"] = labels
        except Exception:  # noqa: BLE001
            continue
    for field, options in _FIELD_OPTIONS.items():
        if field in (schema.get("properties") or {}):
            schema["properties"][field]["x-options"] = options
    return schema


@router.get("/sites")
def get_sites():
    """全部站点的实际生效 URL（含用户自定义），供单文件刮削的番号网址选择。"""
    from mdcx.crawlers.base import crawler_registry
    from mdcx.config.models import Website

    out = []
    for site in Website:
        cls = crawler_registry.get(site)
        if cls is None:
            continue
        try:
            url = str(cls.base_url_())
        except Exception:  # noqa: BLE001
            url = ""
        if url:
            out.append({"site": site.value, "url": url})
    return {"sites": out}


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


# ---------- 更新方式预览 ----------

_PREVIEW_SOURCE = "/媒体库/三田真铃/SNOS-323目录/SNOS-323-C.mp4"


def _preview_sample() -> tuple["FileInfo", "CrawlersResult"]:
    """固定示例：有中字、无 4K，番号 SNOS-323（设置页预览展示用）。"""
    fi = FileInfo.empty()
    fi.file_path = _Path(_PREVIEW_SOURCE)
    fi.file_name = "SNOS-323-C"
    fi.file_ex = ".mp4"
    fi.c_word = "-C"
    res = CrawlersResult.empty()
    res.number = "SNOS-323"
    res.actor = "三田真铃"
    res.title = "SNOS-323（示例标题）"
    res.year = "2025"
    return fi, res


class PreviewRequest(BaseModel):
    config: dict = {}  # 设置表单当前值（未保存的编辑也参与预览）；缺的键回落到当前生效配置


@router.post("/render-preview")
def render_preview(body: PreviewRequest):
    """用真实 render_name 引擎预览「更新方式」的目标目录树。

    suffix_sort/actor_no_name 等由命名上下文从生效配置读取（不从 body 合并），
    模板类字段均以表单当前值为准。
    """
    merged = manager.config.model_dump(mode="json")
    merged.update({k: v for k, v in (body.config or {}).items() if v is not None})
    fi, res = _preview_sample()

    def _render(template: str, target: "NamingTarget", max_length: int, **opts: bool) -> str:
        try:
            return render_name(template, fi, res, NameRenderOptions(target=target, max_length=max_length, **opts)).text
        except Exception as e:  # noqa: BLE001
            return f"模板渲染失败: {e}"

    mode = str(merged.get("update_mode") or "c")
    folder_max = int(merged.get("folder_name_max") or 60)
    folder_opts = dict(
        show_definition_suffix=bool(merged.get("folder_hd")),
        show_cnword_suffix=bool(merged.get("folder_cnword")),
        show_moword_suffix=bool(merged.get("folder_moword")),
    )
    src_folder = fi.file_path.parent
    note = ""
    if mode == "c":
        folder = src_folder
        note = "目录结构与文件位置不动"
    elif "bc" in mode and "a" in mode:
        a = _Path(_render(str(merged.get("update_a_folder") or ""), NamingTarget.FOLDER, folder_max, **folder_opts))
        b = _Path(_render(str(merged.get("update_b_folder") or ""), NamingTarget.FOLDER, folder_max, **folder_opts))
        folder = src_folder.parent.parent / a / b
    elif "bc" in mode:
        b = _Path(_render(str(merged.get("update_b_folder") or ""), NamingTarget.FOLDER, folder_max, **folder_opts))
        folder = src_folder.parent / b
    elif mode == "d":
        d = _Path(_render(str(merged.get("update_d_folder") or ""), NamingTarget.FOLDER, folder_max, **folder_opts))
        folder = src_folder / d
    else:
        folder = src_folder
        note = f"未知更新方式「{mode}」，按原地刷新展示"

    if merged.get("success_file_rename", True):
        file_max = int(merged.get("file_name_max") or 100)
        name = _render(
            str(merged.get("update_c_filetemplate") or "{{ number }}"),
            NamingTarget.FILE,
            file_max,
            show_definition_suffix=bool(merged.get("file_hd")),
            show_cnword_suffix=bool(merged.get("file_cnword")),
            show_moword_suffix=bool(merged.get("file_moword")),
        )
        file_name = f"{name}.mp4"
    else:
        file_name = fi.file_path.name
        note = note or "未开「成功后重命名文件」，文件名保持原样"

    return {"mode": mode, "source": str(fi.file_path), "folder": str(folder), "file": str(folder / file_name), "note": note}
