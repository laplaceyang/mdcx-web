"""工具页 API：包装桌面版工具页的各组功能（全部无头运行，日志经信号总线推送）。

并发模型：同一名工具不允许重入；演员库维护家族共享互斥（与桌面版一致）。
长任务经 executor 后台事件循环执行，进度/日志通过信号事件实时推送前端。
"""

import asyncio
import csv
import io
import shutil
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
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


@router.post("/cover-backfill")
async def cover_backfill(req: CoverBackfillRequest):
    """封面补图（scripts.cover_backfill.backfill_cover）。"""
    if not req.numbers:
        raise HTTPException(status_code=422, detail="请提供番号列表")
    from scripts.cover_backfill import backfill_cover

    from mdcx.config.manager import manager

    async def _run():
        results = []
        for number in req.numbers:
            signal.show_log_text(f"开始补图: {number}")
            try:
                result = await backfill_cover(
                    number,
                    output_dir=manager.data_folder,
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
