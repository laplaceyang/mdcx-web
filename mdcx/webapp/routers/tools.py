"""工具页 API：包装桌面版工具页的各组功能（全部无头运行，日志经信号总线推送）。

并发模型：同一名工具不允许重入；演员库维护家族共享互斥（与桌面版一致）。
长任务经 executor 后台事件循环执行，进度/日志通过信号事件实时推送前端。
"""

import asyncio
import csv
import io
import os
import re
import shutil
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from mdcx.config.resources import resources
from mdcx.core.scrape_cache import ScrapeStateCache
from mdcx.signals import signal
from mdcx.utils import executor
from mdcx.webapp.paths import safe_path

router = APIRouter(prefix="/api/tools", tags=["tools"])

# 演员库维护家族共享互斥（桌面版 _ACTOR_DB_SCRAPE_MANAGED 语义）
_ACTOR_DB_TASKS = frozenset({"translate", "link", "sync_aliases", "fill_minnano", "fill_zh_javdb", "clean_male", "verify_tmdbid", "update_nfo_tmdbid"})

_running: set[str] = set()
_running_lock = asyncio.Lock()


async def _acquire(name: str) -> None:
    async with _running_lock:
        if name in _running:
            raise HTTPException(status_code=409, detail=f"工具「{name}」正在运行中")
        if name in _ACTOR_DB_TASKS and _running & _ACTOR_DB_TASKS:
            raise HTTPException(status_code=409, detail="演员库维护工具同一时间只能运行一个")
        _running.add(name)


async def _release(name: str) -> None:
    async with _running_lock:
        _running.discard(name)


async def run_tool(name: str, coro_factory):
    """提交长任务到后台事件循环；调用方立即返回。异常与完成均写日志事件。"""

    async def _run():
        try:
            await coro_factory()
        except Exception as e:  # noqa: BLE001 工具异常不能打穿后台循环
            import traceback

            signal.show_log_text(f"🔴 工具「{name}」异常: {e}\n{traceback.format_exc()}")
        finally:
            await _release(name)
            signal.show_log_text(f"🧰 工具「{name}」结束")

    await _acquire(name)
    signal.show_log_text(f"🧰 工具「{name}」开始")
    executor.submit(_run())
    return {"ok": True}


@router.get("/status")
async def status():
    async with _running_lock:
        return {"running": sorted(_running)}


# region 单文件刮削（走 /api/scrape/start mode=single，见 jobs.start_single）


# endregion


class SymlinkRequest(BaseModel):
    copy_nfo: bool = False


@router.post("/symlink")
async def symlink(req: SymlinkRequest):
    """网盘目录软链接创建（newtdisk_creat_symlink）。"""
    from mdcx.base.file import newtdisk_creat_symlink

    return await run_tool("软链接创建", lambda: newtdisk_creat_symlink(req.copy_nfo))


@router.post("/move-videos")
async def move_videos():
    """把媒体目录中的视频/字幕移动到 Movie_moved 子目录（桌面版"视频/字幕移动"）。"""
    from mdcx.base.file import movie_lists
    from mdcx.config.extend import get_movie_path_setting
    from mdcx.config.manager import manager

    async def _run():
        for movie_path in get_movie_path_setting().movie_paths:
            if not Path(movie_path).exists():
                signal.show_log_text(f" 🔴 Movie folder does not exist: {movie_path}")
                continue
            c = get_movie_path_setting(movie_path_override=Path(movie_path))
            ignore_dirs = c.ignore_dirs
            ignore_dirs.append(Path(movie_path) / "Movie_moved")
            movie_list = await movie_lists(ignore_dirs, manager.config.media_type + manager.config.sub_type, Path(movie_path))
            if not movie_list:
                signal.show_log_text(f"No movie found in {movie_path}!")
                continue
            des_path = Path(movie_path) / "Movie_moved"
            des_path.mkdir(parents=True, exist_ok=True)
            signal.show_log_text(f"Start move movies in {movie_path}...")
            for file_path in movie_list:
                try:
                    await asyncio.to_thread(shutil.move, str(file_path), str(des_path / file_path.name))
                    kind = "movie" if file_path.suffix.lower() in manager.config.media_type else "sub"
                    signal.show_log_text(f"   Move {kind}: {file_path.name} to Movie_moved Success!")
                except Exception as e:  # noqa: BLE001
                    signal.show_log_text(f"   🔴 Skip {file_path.name}: {e}")

    return await run_tool("视频/字幕移动", _run)


@router.post("/subtitle")
async def add_subtitle():
    """为所有视频批量添加字幕（add_sub_for_all_video）。"""
    from mdcx.tools.subtitle import add_sub_for_all_video

    return await run_tool("批量字幕添加", add_sub_for_all_video)


class ExtrasRequest(BaseModel):
    kind: str  # extras | theme | extrafanart_copy
    action: str  # add | del


@router.post("/extras")
async def extras(req: ExtrasRequest):
    """批量创建/删除 extras（extrafanart 剧照副本 / theme video 主题视频）。"""
    if req.kind == "extrafanart_copy":
        from mdcx.base.image import add_del_extrafanart_copy

        factory = lambda: add_del_extrafanart_copy(req.action)  # noqa: E731
    elif req.kind == "theme":
        from mdcx.base.video import add_del_theme_videos

        factory = lambda: add_del_theme_videos(req.action)  # noqa: E731
    elif req.kind == "extras":
        from mdcx.base.video import add_del_extras

        factory = lambda: add_del_extras(req.action)  # noqa: E731
    else:
        raise HTTPException(status_code=422, detail=f"未知类型: {req.kind}")
    return await run_tool(f"extras {req.kind} {req.action}", factory)


class CoverBackfillRequest(BaseModel):
    numbers: list[str]
    overwrite: bool = False
    watermark: bool = False


def _cover_output_dir() -> Path:
    """补图输出目录 = 设置里的成功输出目录；非绝对路径/未配置时回退数据目录。"""
    from mdcx.config.manager import manager

    folder = str(manager.config.success_output_folder or "").split("|")[0].strip()
    path = Path(folder)
    if path.is_absolute():
        return path
    return manager.data_folder


@router.post("/cover-backfill")
async def cover_backfill(req: CoverBackfillRequest):
    """封面补图（scripts.cover_backfill.backfill_cover）。输出到成功输出目录。"""
    if not req.numbers:
        raise HTTPException(status_code=422, detail="请提供番号列表")

    output_dir = _cover_output_dir()

    async def _run():
        from scripts.cover_backfill import backfill_cover

        results = []
        for number in req.numbers:
            signal.show_log_text(f"开始补图: {number}（输出目录: {output_dir}）")
            try:
                result = await backfill_cover(
                    number,
                    output_dir=output_dir,
                    overwrite=req.overwrite,
                    watermark=req.watermark,
                )
                results.append(result)
                signal.show_log_text(f"  ✅ {result.number}: thumb={result.thumb_path}, poster={result.poster_path}")
            except Exception as e:  # noqa: BLE001
                signal.show_log_text(f"  🔴 {number}: {e}")
        signal.show_log_text("=" * 60)
        signal.show_log_text(f"封面补图完成: {len(results)}/{len(req.numbers)} 成功")

    return await run_tool("封面补图", _run)


class GfriendsRequest(BaseModel):
    local_path: str


@router.post("/gfriends")
async def sync_gfriends(req: GfriendsRequest):
    """Gfriends 头像库同步（git pull 本地仓库）。"""
    if not req.local_path:
        raise HTTPException(status_code=422, detail="请提供 Gfriends 本地仓库目录")
    from mdcx.tools.sync_gfriends import sync_gfriends as do_sync

    async def _run():
        success, msg = await asyncio.to_thread(do_sync, req.local_path)
        signal.show_log_text(f"{'✅' if success else '🔴'} Gfriends 同步: {msg}")

    return await run_tool("Gfriends 同步", _run)


@router.post("/cover-backfill/upload")
async def cover_backfill_upload(
    request: Request,
    number: str = Query(...),
    filename: str = Query("cover.jpg"),
    overwrite: bool = Query(False),
):
    """上传本地图补图：图片作为 thumb，横图自动裁竖版 poster。

    走 raw body 上传（避免引入 python-multipart 依赖），
    输出与 dmm_direct 直构路径一致：{番号}-thumb.jpg / {番号}-poster.jpg。
    输出到成功输出目录。
    """
    import time

    import aiofiles

    if not number.strip():
        raise HTTPException(status_code=422, detail="请提供番号")
    body = await request.body()
    if not body:
        raise HTTPException(status_code=422, detail="未收到图片数据")
    ext = Path(filename).suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        raise HTTPException(status_code=422, detail=f"不支持的图片格式: {ext or '(缺扩展名)'}")

    from scripts.cover_backfill import backfill_cover_from_upload

    output_dir = _cover_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    tmp = output_dir / f".[upload]{int(time.time() * 1000)}{ext}"
    tmp.write_bytes(body)
    try:
        result = await backfill_cover_from_upload(number.strip(), tmp, output_dir, overwrite=overwrite)
        signal.show_log_text(f"📤 上传补图完成 {result.number}: {result.thumb_path} / {result.poster_path}")
        return {"ok": True, "number": result.number, "thumb": str(result.thumb_path), "poster": str(result.poster_path)}
    finally:
        await aiofiles.os.remove(tmp)


# region 翻译测试（web 版翻译调试：文本直翻 / NFO 按正常流程翻译）


class TranslateTestRequest(BaseModel):
    mode: str  # text | nfo
    text: str = ""
    path: str = ""  # mode=nfo 时的 nfo 路径


def _xml_text(root, tag: str) -> str:
    el = root.find(tag)
    return (el.text or "").strip() if el is not None and el.text else ""


_CREDIT_RE = re.compile(r"\n*由\s*.+?\s*提供翻译\s*$")


def _strip_translation_credit(text: str) -> str:
    """去掉正常流程写在简介末尾的「由 xx 提供翻译」署名（core/nfo.py 写入）。"""
    if not text:
        return text
    return _CREDIT_RE.sub("", text).rstrip()


def _xml_set_text(root, tag: str, value: str) -> None:
    import xml.etree.ElementTree as ET

    el = root.find(tag)
    if el is None:
        el = ET.SubElement(root, tag)
    el.text = value


@router.post("/translate-test")
async def translate_test(req: TranslateTestRequest):
    """翻译测试。

    text 模式：输入内容按正常流程的标题翻译逻辑处理（检测日/英文 → 按字段配置的目标
    语言走配置的翻译引擎降级 → 简繁转换）。
    nfo 模式：解析 NFO，用与刮削管线相同的 translate_title_outline 翻译标题/简介
    （只动正常流程里会被翻译的部分），返回翻译后的 NFO 全文。
    """
    import xml.etree.ElementTree as ET  # noqa: S405 只处理用户自己的 nfo；读取用 defusedxml

    import defusedxml.ElementTree as SafeET
    from mdcx.config.manager import manager
    from mdcx.core.translate import translate_title_outline
    from mdcx.gen.field_enums import CrawlerResultFields
    from mdcx.models.log_buffer import LogBuffer
    from mdcx.models.model_types import CrawlersResult

    def _field_info() -> dict:
        t = manager.config.get_field_config(CrawlerResultFields.TITLE)
        o = manager.config.get_field_config(CrawlerResultFields.OUTLINE)
        return {
            "title_language": t.language.value,
            "title_translate": t.translate,
            "outline_language": o.language.value,
            "outline_translate": o.translate,
            "translate_by": [str(e.value) for e in manager.config.translate_config.translate_by],
        }

    root_id = LogBuffer.new_root()  # 收集翻译引擎日志，随响应返回给弹窗展示

    if req.mode == "text":
        text = req.text.strip()
        if not text:
            raise HTTPException(status_code=422, detail="请输入要翻译的内容")
        result = CrawlersResult.empty()
        result.title = text
        translated = await translate_title_outline(result, "", "")
        log_text = LogBuffer.log().get()
        return {
            "mode": "text",
            "original": text,
            "content": translated.title,
            "log": log_text,
            "field_info": _field_info(),
        }

    if req.mode == "nfo":
        p = safe_path(req.path)
        try:
            root = SafeET.parse(p).getroot()
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=422, detail=f"NFO 解析失败: {e}") from e
        title_src = _strip_translation_credit(_xml_text(root, "title"))
        outline_src = _strip_translation_credit(_xml_text(root, "outline"))
        plot_src = _strip_translation_credit(_xml_text(root, "plot"))
        result = CrawlersResult.empty()
        result.number = _xml_text(root, "num") or _xml_text(root, "number")
        result.title = title_src
        result.originaltitle = _xml_text(root, "originaltitle")
        # 正常流程里简介翻译后写入 <plot>（core/nfo.py），<outline> 为同一来源：
        # outline 元素为空时用 plot 作翻译源
        result.outline = outline_src or plot_src
        if not (result.title or result.outline):
            raise HTTPException(status_code=422, detail="NFO 中没有 title/outline 可翻译")
        translated = await translate_title_outline(result, "", result.number)
        _xml_set_text(root, "title", translated.title)
        _xml_set_text(root, "outline", translated.outline)
        # plot 独立存在且内容不同时单独翻译（同一文本则复用 outline 的翻译结果）
        if plot_src and plot_src != outline_src:
            r2 = CrawlersResult.empty()
            r2.number = result.number
            r2.outline = plot_src
            r2 = await translate_title_outline(r2, "", result.number)
            _xml_set_text(root, "plot", r2.outline)
        elif plot_src:
            _xml_set_text(root, "plot", translated.outline)
        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        content = ET.tostring(root, encoding="unicode", xml_declaration=True)
        return {"mode": "nfo", "path": str(p), "content": content, "log": LogBuffer.log().get(), "field_info": _field_info()}

    raise HTTPException(status_code=422, detail=f"未知模式: {req.mode}")


class TranslateSaveRequest(BaseModel):
    path: str
    content: str


@router.post("/translate-test/save")
def translate_test_save(req: TranslateSaveRequest):
    """把翻译后的 NFO 覆盖保存：原文件重命名为 .bak 备份，新内容写入原路径。"""
    import os

    p = safe_path(req.path)
    if p.suffix.lower() != ".nfo":
        raise HTTPException(status_code=422, detail="只支持覆盖保存 .nfo 文件")
    if not req.content.strip():
        raise HTTPException(status_code=422, detail="内容为空，拒绝保存")

    tmp = p.with_name(p.name + ".[new].tmp")
    tmp.write_text(req.content, encoding="utf-8")
    bak = p.with_name(p.name + ".bak")
    try:
        if bak.exists():
            bak.unlink()
        p.rename(bak)  # 原始 NFO 备份为 .bak
        os.replace(tmp, p)
    except Exception:
        # 失败回滚：备份恢复为原文件
        if not p.exists() and bak.exists():
            bak.rename(p)
        tmp.unlink(missing_ok=True)
        raise
    signal.show_log_text(f"🌐 翻译结果已覆盖保存: {p}（原文件备份为 {bak.name}）")
    return {"ok": True, "path": str(p), "bak": str(bak)}


# endregion


class ActorDbRequest(BaseModel):
    task: str  # translate|link|sync_aliases|fill_minnano|fill_zh_javdb|clean_male|verify_tmdbid|check|update_nfo_tmdbid
    alias_source: str = "tmdb"  # tmdb | javdb | avwiki(minnano)
    alias_overwrite: bool = False
    offset: int = 0
    limit: int = 0
    nfo_dir: str = ""


@router.post("/actor-db")
async def actor_db(req: ActorDbRequest):
    """演员库维护（actor_database.xlsx 各类维护任务）。"""
    from mdcx.tools import actor_db_tool

    name_map = {
        "translate": "补全中文名",
        "link": "补全 LibreDMM 链接",
        "sync_aliases": "补全别名",
        "fill_minnano": "minnano 补全",
        "fill_zh_javdb": "JavDB 中文名",
        "clean_male": "剔除男演员",
        "verify_tmdbid": "校验 tmdbid 有效性",
        "check": "检查用户库",
        "update_nfo_tmdbid": "更新 nfo tmdbid",
    }
    if req.task not in name_map:
        raise HTTPException(status_code=422, detail=f"未知任务: {req.task}")

    async def _run():
        if req.task == "clean_male":
            await actor_db_tool.clean_male_actors()
        elif req.task == "verify_tmdbid":
            await actor_db_tool.verify_tmdb_ids()
        elif req.task == "check":
            db_path = Path(resources.u("actor_database.xlsx"))
            if not db_path.exists():
                signal.show_log_text("🔴 actor_database.xlsx 不存在，请先刮削或执行一次演员库维护生成数据库")
                return
            issues = await asyncio.to_thread(actor_db_tool._check_actor_db_issues, db_path)
            signal.show_log_text(f"🔍 检查完成，发现问题 {len(issues)} 项（详见上方日志）")
        elif req.task == "update_nfo_tmdbid":
            if not req.nfo_dir or not Path(req.nfo_dir).is_dir():
                signal.show_log_text(f"🔴 nfo 目录无效: {req.nfo_dir}")
                return
            await actor_db_tool.update_nfo_tmdb_ids(Path(req.nfo_dir))
        else:
            kwargs = {}
            if req.task == "sync_aliases":
                kwargs = dict(
                    alias_source=req.alias_source,
                    overwrite=req.alias_overwrite,
                    offset=req.offset,
                    limit=req.limit,
                )
            elif req.task == "fill_zh_javdb":
                kwargs = dict(offset=req.offset, limit=req.limit)
            await actor_db_tool.run_actor_db_xlsx(mode=req.task, **kwargs)

    return await run_tool(name_map[req.task], _run)


@router.post("/missing-number")
async def missing_number():
    """查找缺失番号（本地库 vs 演员库）。"""
    from mdcx.tools.missing import check_missing_number

    return await run_tool("查找缺失番号", lambda: check_missing_number(True))


# region 刮削缓存管理


def _open_cache() -> ScrapeStateCache:
    cache = ScrapeStateCache(resources.u("scrape_state.db"))
    if not cache.open():
        raise HTTPException(status_code=500, detail="刮削缓存数据库不可用")
    return cache


@router.get("/cache/stats")
def cache_stats():
    cache = _open_cache()
    try:
        stats = cache.stats()
        failed = cache.list_failed_detail(limit=1000)
    finally:
        cache.close()
    return {
        "stats": stats,
        "failed": [
            {
                "file_path": f.file_path,
                "number": f.number,
                "fail_count": f.fail_count,
                "error": f.error,
                "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(f.scraped_at)) if f.scraped_at else "",
            }
            for f in failed
        ],
    }


@router.get("/cache/export")
def cache_export():
    """导出失败列表 CSV。"""
    cache = _open_cache()
    try:
        failed = cache.list_failed_detail(limit=100000)
    finally:
        cache.close()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["文件路径", "番号", "失败次数", "最后错误", "时间"])
    for f in failed:
        w.writerow(
            [
                f.file_path,
                f.number,
                f.fail_count,
                f.error,
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(f.scraped_at)) if f.scraped_at else "",
            ]
        )
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=scrape_failed.csv"},
    )


class CacheDeleteRequest(BaseModel):
    paths: list[str]


@router.post("/cache/delete")
def cache_delete(req: CacheDeleteRequest):
    cache = _open_cache()
    try:
        for p in req.paths:
            cache.delete_state(Path(p))
    finally:
        cache.close()
    return {"ok": True, "count": len(req.paths)}


@router.post("/cache/clear")
def cache_clear():
    cache = _open_cache()
    try:
        cache.clear()
    finally:
        cache.close()
    signal.show_log_text(" 刮削缓存已全部清空")
    return {"ok": True}


# endregion


class PosterCutRequest(BaseModel):
    path: str  # 原图路径
    box: tuple[int, int, int, int]  # (left, top, right, bottom)，相对原图像素
    output_path: str = ""  # 留空则覆盖原图


@router.post("/poster-cut")
async def poster_cut(req: PosterCutRequest):
    """海报裁剪（前端 canvas 框选，后端 PIL 落盘）。"""
    from PIL import Image

    src = safe_path(req.path)
    left, top, right, bottom = req.box
    width, height = right - left, bottom - top
    if width <= 0 or height <= 0:
        raise HTTPException(status_code=422, detail="裁剪框无效")
    out = safe_path(req.output_path) if req.output_path else src

    def _cut():
        with Image.open(src) as img:
            cropped = img.crop((max(0, left), max(0, top), min(img.width, right), min(img.height, bottom)))
            cropped.save(out, quality=95, subsampling=0)

    await run_in_threadpool(_cut)
    signal.show_log_text(f"✂️ 海报已裁剪: {out}")
    return {"ok": True, "output": str(out)}


# region 演员信息 / 头像（Emby/Kodi，原"设置-演员"与工具页演员组）


class ActorSyncRequest(BaseModel):
    config_save: bool = True


@router.post("/actor-info-sync")
async def actor_info_sync():
    """演员信息写入 Emby（update_emby_actor_info）。"""
    from mdcx.tools.emby_actor_info import update_emby_actor_info

    return await run_tool("演员信息写入", update_emby_actor_info)


@router.post("/actor-photo-sync")
async def actor_photo_sync():
    """演员头像写入 Emby（update_emby_actor_photo）。"""
    from mdcx.tools.emby_actor_image import update_emby_actor_photo

    return await run_tool("演员头像写入", update_emby_actor_photo)


@router.post("/actor-kodi-write")
async def actor_kodi_write():
    """创建 Kodi 演员头像目录（creat_kodi_actors(True)）。"""
    from mdcx.tools.emby_actor_info import creat_kodi_actors

    return await run_tool("Kodi 头像写入", lambda: creat_kodi_actors(True))


@router.post("/actor-kodi-delete")
async def actor_kodi_delete():
    """删除演员文件夹（creat_kodi_actors(False)）。"""
    from mdcx.tools.emby_actor_info import creat_kodi_actors

    return await run_tool("Kodi 头像删除", lambda: creat_kodi_actors(False))


@router.post("/actor-list-show")
async def actor_list_show():
    """显示 Emby 演员列表（show_emby_actor_list）。"""
    from mdcx.tools.emby_actor_info import show_emby_actor_list

    return await run_tool("演员列表", lambda: show_emby_actor_list(0))


# endregion
