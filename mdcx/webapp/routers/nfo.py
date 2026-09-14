"""NFO 信息管理 API（对应桌面版"信息管理/NFO 库"页面）。

直接操作媒体目录中的 .nfo 文件：浏览、字段编辑、批量操作、删除、重新刮削。
XML 解析用 defusedxml；写回保持 utf-8 缩进格式。
"""

import json
import re
import xml.etree.ElementTree as ET  # noqa: S405 写回的是用户自己的媒体 nfo；读取用 defusedxml
from pathlib import Path
from typing import Any

import defusedxml.ElementTree as SafeET
from fastapi import APIRouter, HTTPException, Query, Request
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


class NfoCreate(BaseModel):
    dir: str = ""  # 保存目录；留空 = 成功输出目录（非绝对路径时回退配置数据目录）
    subfolder: str = ""  # 番号子目录（手动刮削）：在 dir 下再建一层，清洗规则同文件名
    filename: str = ""  # 文件名（可省略 .nfo 后缀）；留空 = 番号
    overwrite: bool = False
    fields: dict = {}


def _as_str(fields: dict, key: str) -> str:
    return str(fields.get(key) or "").strip()


def _as_list(fields: dict, key: str) -> list[str]:
    """演员/标签列表：接受 list 或逗号/换行分隔的字符串。"""
    value = fields.get(key)
    if value is None:
        return []
    raw = value if isinstance(value, list) else re.split(r"[,，\n]", str(value))
    return [str(v).strip() for v in raw if str(v).strip()]


def _default_create_dir() -> Path:
    """创建 NFO 的默认保存目录 = 成功输出目录（存在时）；否则回退配置数据目录。"""
    from mdcx.config.manager import manager

    folder = str(manager.config.success_output_folder or "").split("|")[0].strip()
    path = Path(folder)
    if path.is_absolute() and path.exists():
        return path
    return manager.data_folder


def _build_nfo_xml(fields: dict) -> str:
    """按正常刮削流程（core/nfo.py）的元素顺序生成 NFO，空字段跳过。"""
    from xml.sax.saxutils import escape

    plot = _as_str(fields, "plot")
    originalplot = _as_str(fields, "originalplot").replace("\r\n", "\n").replace("\r", "\n")
    release = _as_str(fields, "release")
    number = _as_str(fields, "number")
    title = _as_str(fields, "title")
    originaltitle = _as_str(fields, "originaltitle")
    country = _as_str(fields, "countrycode")
    series = _as_str(fields, "series")
    studio = _as_str(fields, "studio")
    publisher = _as_str(fields, "publisher")
    actors = _as_list(fields, "actors")
    genres = _as_list(fields, "genres")

    tagline = _as_str(fields, "tagline")
    if not tagline and release:
        from mdcx.config.manager import manager

        tagline = str(manager.config.nfo_tagline or "").replace("release", release)

    lines = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>', "<movie>"]

    def add(tag: str, value: str, indent: str = "  ") -> None:
        if value:
            lines.append(f"{indent}<{tag}>{escape(value)}</{tag}>")

    add("plot", plot)
    add("originalplot", originalplot)
    add("tagline", tagline)
    for tag in ("premiered", "releasedate", "release"):
        add(tag, release)
    add("num", number)
    add("title", title)
    add("originaltitle", originaltitle)
    add("countrycode", country)
    for name in actors:
        lines.append("  <actor>")
        add("name", name, indent="    ")
        lines.append("    <type>Actor</type>")
        lines.append("  </actor>")
    add("series", series)
    add("studio", studio)
    add("maker", studio)
    add("publisher", publisher)
    add("label", publisher)
    for genre in genres:
        add("genre", genre)

    lines.append("</movie>")
    return "\n".join(lines) + "\n"


def _create_base_name(filename: str, number: str) -> str:
    """创建 NFO 的目标文件名（不含 .nfo），NFO 与补图共用：清洗 Windows 非法字符与首尾空白/点。"""
    name = (filename or number).strip()
    name = re.sub(r'[\\/:*?"<>|\r\n]', "_", name).strip(" .")
    if name.lower().endswith(".nfo"):
        name = name[:-4]
    return name


def _resolve_create_dir(dir_value: str, subfolder: str = "") -> Path:
    """创建 NFO 的落盘目录：dir 留空 = 成功输出目录，subfolder（番号）再建一层；统一清洗。

    macOS 上 /var 等符号链接路径不 resolve 时无法与白名单匹配，故统一 resolve。
    """
    directory = (Path(dir_value) if dir_value.strip() else _default_create_dir()).resolve()
    sub = _create_base_name(subfolder, "")
    if sub:
        directory = directory / sub
    return directory


@router.post("/create")
def create_nfo(req: NfoCreate):
    """创建 NFO：表单字段按正常流程的元素顺序写成 .nfo 文件（工具页「创建 NFO」）。"""
    fields = req.fields or {}
    directory = _resolve_create_dir(req.dir, req.subfolder)
    _check_dir(directory)

    name = _create_base_name(req.filename, _as_str(fields, "number"))
    if not name:
        raise HTTPException(status_code=422, detail="请填写文件名或番号")
    name += ".nfo"

    target = directory / name
    if target.exists() and not req.overwrite:
        raise HTTPException(status_code=409, detail=f"文件已存在: {target}")
    try:
        directory.mkdir(parents=True, exist_ok=True)
        content = _build_nfo_xml(fields)
        target.write_text(content, encoding="utf-8")
    except OSError as e:
        raise HTTPException(status_code=422, detail=f"NFO 写入失败: {e}") from e
    signal.show_log_text(f"🆕 NFO 已创建: {target}")
    return {"ok": True, "path": str(target), "content": content}


@router.post("/create-cover")
async def create_nfo_cover(
    request: Request,
    name: str = Query(..., description="NFO 文件名（可带 .nfo），图片基础名与其一致"),
    dir: str = Query("", description="保存目录；留空 = 成功输出目录"),
    subfolder: str = Query("", description="番号子目录，与 NFO 落盘目录一致"),
    filename: str = Query("cover.jpg", description="上传图片原始文件名，用于识别扩展名"),
    overwrite: bool = Query(True),
):
    """创建 NFO 的补图：本地上传图片走 backfill_cover_from_upload（原图作 thumb，横图裁竖版 poster）。

    输出与 NFO 同目录、基础名同 NFO 文件名：{name}-thumb.jpg / {name}-poster.jpg。
    """
    import time

    body = await request.body()
    if not body:
        raise HTTPException(status_code=422, detail="未收到图片数据")
    ext = Path(filename).suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        raise HTTPException(status_code=422, detail=f"不支持的图片格式: {ext or '(缺扩展名)'}")

    base = _create_base_name(name, "")
    if not base:
        raise HTTPException(status_code=422, detail="请填写文件名或番号")
    directory = _resolve_create_dir(dir, subfolder)
    _check_dir(directory)

    from scripts.cover_backfill import backfill_cover_from_upload

    directory.mkdir(parents=True, exist_ok=True)
    tmp = directory / f".[create-cover]{int(time.time() * 1000)}{ext}"
    tmp.write_bytes(body)
    try:
        result = await backfill_cover_from_upload(base, tmp, directory, overwrite=overwrite)
        signal.show_log_text(f"🖼️ NFO 补图完成: {result.thumb_path} / {result.poster_path}")
        return {"ok": True, "thumb": str(result.thumb_path), "poster": str(result.poster_path)}
    finally:
        tmp.unlink(missing_ok=True)


@router.get("/extract-number")
def extract_number(path: str = Query(..., description="视频文件路径，从其文件名提取番号")):
    """从文件名提取番号（手动刮削表单的番号默认值），与正常刮削/补图同一规则。"""
    from mdcx.config.manager import manager
    from mdcx.number import get_file_number

    name = Path(path.strip()).name
    number = get_file_number(name, manager.computed.escape_string_list) or ""
    return {"number": number}


@router.post("/move-video")
def move_video(
    src: str = Query(..., description="视频文件当前路径"),
    dir: str = Query("", description="父目录；留空 = 成功输出目录"),
    subfolder: str = Query("", description="番号子目录，与 NFO 落盘目录一致"),
    name: str = Query(..., description="目标文件名（不含扩展名），与番号一致"),
    overwrite: bool = Query(False),
):
    """手动刮削收尾：把选中的视频移入番号目录并改名为番号。

    跨挂载点（如 NAS 的 /media → /out）由 shutil.move 自动 copy+delete。
    """
    import shutil

    s = Path(src.strip())
    if not s.is_file():
        raise HTTPException(status_code=404, detail=f"视频文件不存在: {src}")

    base = _create_base_name(name, "")
    if not base:
        raise HTTPException(status_code=422, detail="请填写番号")
    directory = _resolve_create_dir(dir, subfolder)
    _check_dir(directory)

    target = directory / f"{base}{s.suffix}"
    if target.exists() and not overwrite:
        raise HTTPException(status_code=409, detail=f"文件已存在: {target}")
    try:
        directory.mkdir(parents=True, exist_ok=True)
        shutil.move(str(s), str(target))
    except OSError as e:
        raise HTTPException(status_code=422, detail=f"视频移动失败: {e}") from e
    signal.show_log_text(f"🎬 视频已移动: {s} → {target}")
    return {"ok": True, "path": str(target)}


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
