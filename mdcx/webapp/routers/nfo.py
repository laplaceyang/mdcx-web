"""NFO 信息管理 API（对应桌面版"信息管理/NFO 库"页面）。

直接操作媒体目录中的 .nfo 文件：浏览、字段编辑、批量操作、删除、重新刮削。
XML 解析用 defusedxml；写回保持 utf-8 缩进格式。
"""

import json
import xml.etree.ElementTree as ET  # noqa: S405 写回的是用户自己的媒体 nfo；读取用 defusedxml
from pathlib import Path
from typing import Any

import defusedxml.ElementTree as SafeET
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from mdcx.signals import signal
from mdcx.webapp.paths import allowed_roots, safe_path

router = APIRouter(prefix="/api/nfo", tags=["nfo"])

# 可编辑字段（与桌面版 NFO 库编辑表单对齐）
SCALAR_FIELDS = [
    "title",
    "originaltitle",
    "outline",
    "plot",
    "tagline",
    "director",
    "release",
    "runtime",
    "score",
    "year",
    "series",
    "studio",
    "publisher",
    "number",
]
LIST_FIELDS = ["actor", "tag"]

VIDEO_EXTS = {".mp4", ".avi", ".rmvb", ".wmv", ".mov", ".mkv", ".flv", ".ts", ".webm", ".mpg", ".m4v", ".iso"}


def _parse_nfo(path) -> ET.Element:
    try:
        return SafeET.parse(path).getroot()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"NFO 解析失败: {e}") from e


def _text(root: ET.Element, tag: str) -> str:
    el = root.find(tag)
    return (el.text or "").strip() if el is not None and el.text else ""


def _list_text(root: ET.Element, tag: str, child: str | None = None) -> list[str]:
    out = []
    for el in root.findall(tag):
        child_el = el.find(child) if child else None
        value = child_el.text if child_el is not None else el.text
        if value and value.strip():
            out.append(value.strip())
    return out


def _summary(path) -> dict:
    root = _parse_nfo(path)
    p = Path(path)
    directory = p.parent
    return {
        "path": str(p),
        "dir": str(directory),
        "file": p.name,
        "title": _text(root, "title"),
        "number": _text(root, "num") or _text(root, "number"),
        "actor": _list_text(root, "actor", "name"),
        "director": _text(root, "director"),
        "series": _text(root, "series"),
        "release": _text(root, "release"),
        "has_poster": (directory / "poster.jpg").is_file(),
        "has_thumb": any((directory / n).is_file() for n in ("fanart.jpg", "thumb.jpg")),
    }


def _check_dir(resolved: Path) -> None:
    if not any(resolved == Path(r).resolve() or resolved.is_relative_to(Path(r).resolve()) for r in allowed_roots()):
        raise HTTPException(status_code=403, detail="路径不在允许访问的目录内")


@router.get("/roots")
def roots():
    """可浏览的根目录（媒体目录 + 配置目录，过滤掉不存在的）。"""
    return {"roots": [str(r) for r in allowed_roots() if Path(r).exists()]}


@router.get("/browse")
def browse(path: str = "", keyword: str = ""):
    """浏览目录：返回子目录与 nfo 文件列表（含摘要）。keyword 过滤全部字段。"""
    if not path:
        return {"dirs": [str(r) for r in allowed_roots() if Path(r).exists()], "items": []}
    d = Path(path)
    if d.is_file():
        d = d.parent
    resolved = d.resolve()
    _check_dir(resolved)
    if not resolved.is_dir():
        raise HTTPException(status_code=404, detail=f"目录不存在: {path}（请在「软件设置 → 刮削目录」配置实际存在的媒体路径）")
    try:
        dirs = sorted(str(p) for p in d.iterdir() if p.is_dir() and not p.name.startswith("."))
    except OSError as e:
        raise HTTPException(status_code=403, detail=f"目录无法读取: {e}") from e
    items = []
    for nfo in sorted(d.glob("*.nfo")):
        try:
            entry = _summary(nfo)
        except HTTPException:
            continue
        if keyword and keyword.lower() not in json.dumps(entry, ensure_ascii=False).lower():
            continue
        items.append(entry)
    return {"dirs": dirs, "items": items, "current": str(resolved)}


@router.get("/item")
def item(path: str):
    p = safe_path(path)
    root = _parse_nfo(p)
    fields: dict[str, Any] = {name: _text(root, name) for name in SCALAR_FIELDS}
    for name in LIST_FIELDS:
        fields[name] = _list_text(root, name, "name" if name == "actor" else None)
    directory = p.parent
    images = {}
    for key, name in (("poster", "poster.jpg"), ("thumb", "thumb.jpg"), ("fanart", "fanart.jpg")):
        if (directory / name).is_file():
            images[key] = str(directory / name)
    return {"path": str(p), "fields": fields, "images": images}


class NfoUpdate(BaseModel):
    path: str
    fields: dict


def _apply_update(p: Path, fields: dict) -> list[str]:
    root = _parse_nfo(p)
    changed = []
    for name, value in fields.items():
        if name in SCALAR_FIELDS:
            el = root.find(name)
            if el is None:
                el = ET.SubElement(root, name)
            el.text = str(value)
            changed.append(name)
        elif name == "tag":
            for el in root.findall("tag"):
                root.remove(el)
            for v in value or []:
                el = ET.SubElement(root, "tag")
                el.text = str(v)
            changed.append("tag")
        elif name == "actor":
            for el in root.findall("actor"):
                root.remove(el)
            for v in value or []:
                el = ET.SubElement(root, "actor")
                name_el = ET.SubElement(el, "name")
                name_el.text = str(v)
            changed.append("actor")
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(p, encoding="utf-8", xml_declaration=True)
    return changed


@router.put("/item")
def update_item(req: NfoUpdate):
    p = safe_path(req.path)
    changed = _apply_update(p, req.fields)
    signal.show_log_text(f"✏️ NFO 已更新: {p} ({', '.join(changed) or '无变更'})")
    return {"ok": True, "changed": changed}


class BatchRequest(BaseModel):
    paths: list[str]
    action: str  # replace_actor | add_tag | del_tag | set_series
    value: str = ""


@router.post("/batch")
def batch(req: BatchRequest):
    """批量操作（桌面版信息管理批量面板）：替换演员 / 加删标签 / 统一系列名。"""
    ok, fail = 0, []
    for path in req.paths:
        p = safe_path(path)
        fields: dict[str, Any]
        try:
            if req.action == "replace_actor":
                fields = {"actor": [a.strip() for a in req.value.split(",") if a.strip()]}
            elif req.action == "set_series":
                fields = {"series": req.value}
            elif req.action == "add_tag":
                existing = _list_text(_parse_nfo(p), "tag")
                new_tags = [t.strip() for t in req.value.split(",") if t.strip()]
                fields = {"tag": list(dict.fromkeys(existing + new_tags))}
            elif req.action == "del_tag":
                remove = {t.strip() for t in req.value.split(",") if t.strip()}
                fields = {"tag": [t for t in _list_text(_parse_nfo(p), "tag") if t not in remove]}
            else:
                raise HTTPException(status_code=422, detail=f"未知批量操作: {req.action}")
            _apply_update(p, fields)
            ok += 1
        except HTTPException as e:
            fail.append({"path": path, "error": e.detail})
        except Exception as e:  # noqa: BLE001
            fail.append({"path": path, "error": str(e)})
    signal.show_log_text(f"🔧 批量操作 {req.action} 完成: 成功 {ok} / 失败 {len(fail)}")
    return {"ok": True, "success": ok, "failed": fail}


@router.delete("/item")
def delete_item(path: str):
    p = safe_path(path)
    p.unlink()
    signal.show_log_text(f"🗑️ NFO 已删除: {p}")
    return {"ok": True}


@router.post("/rescrape")
def rescrape(path: str):
    """重新刮削：找同目录视频文件，走 again 链路。"""
    from mdcx.models.enums import FileMode
    from mdcx.webapp.jobs import JobAlreadyRunning
    from mdcx.webapp.runtime import job_manager

    p = safe_path(path)
    video = next((f for f in p.parent.iterdir() if f.suffix.lower() in VIDEO_EXTS), None)
    if video is None:
        raise HTTPException(status_code=404, detail=f"目录中未找到视频文件: {p.parent}")
    try:
        job_manager.start(FileMode.Again, [str(video)])
    except JobAlreadyRunning as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {"ok": True, "video": str(video)}
