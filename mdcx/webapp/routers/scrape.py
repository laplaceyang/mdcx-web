"""刮削任务 API。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from mdcx.core.scraper import get_resume_state
from mdcx.models.enums import FileMode
from mdcx.webapp.jobs import JobAlreadyRunning
from mdcx.webapp.runtime import job_manager

router = APIRouter(prefix="/api/scrape", tags=["scrape"])


class StartRequest(BaseModel):
    mode: str = "default"  # default | again | single
    movie_list: list[str] | None = None  # 指定文件列表（不传则按配置扫描）
    resume: bool = False  # true 时按 remain.txt 续刮
    file_path: str = ""  # mode=single：视频文件路径
    appoint_url: str = ""  # mode=single：番号网址


class ResultCompleteReq(BaseModel):
    real_number: str = ""
    file_path: str = ""
    new_path: str = ""


@router.get("/status")
def status():
    return job_manager.status()


@router.get("/active")
def active():
    """在途刮削条目快照（「刮削中」卡片视图，前端 1s 轮询）。

    任务已结束（idle）时在途条目视为陈旧残留（停止硬杀可能跳过 finally），不再返回。
    """
    from mdcx.core import scrape_live

    running = job_manager.state == "running"
    return {"items": scrape_live.snapshot() if running or job_manager.state == "stopping" else [], "running": running}


@router.get("/resume-info")
def resume_info():
    info = job_manager.resume_info()
    return info or {"available": False}


@router.post("/start")
async def start(req: StartRequest):
    try:
        if req.resume:
            state = get_resume_state()
            if state is None:
                raise HTTPException(status_code=409, detail="没有可续刮的剩余任务")
            job_manager.start_resume(state.remain_list)
            return {"ok": True, "resumed": True}
        if req.mode == "single":
            try:
                job_manager.start_single(req.file_path, req.appoint_url)
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e)) from e
            return {"ok": True}
        mode = {"default": FileMode.Default, "again": FileMode.Again}.get(req.mode)
        if mode is None:
            raise HTTPException(status_code=422, detail=f"未知模式: {req.mode}")
        job_manager.start(mode, req.movie_list)
        return {"ok": True}
    except JobAlreadyRunning as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@router.post("/stop")
async def stop():
    await job_manager.stop()
    return {"ok": True}


@router.get("/results")
def results(status: str | None = None):
    return {"items": job_manager.list_results(status)}


@router.delete("/results")
def clear_results():
    job_manager.clear_results()
    return {"ok": True}


@router.post("/results/complete")
def complete_result(req: ResultCompleteReq):
    """手动刮削完成后把失败条目转为成功（路径更新为新视频位置，成功页签可见）。"""
    if not req.file_path or not req.new_path:
        raise HTTPException(status_code=422, detail="file_path / new_path 不能为空")
    done = job_manager.complete_failed_result(req.real_number, req.file_path, req.new_path)
    return {"ok": True, "completed": done}


@router.get("/detail-log")
def detail_log():
    """排空详情日志缓冲（signal.add_log 写入，前端轮询读取）。"""
    from mdcx.signals import signal

    return {"text": signal.get_log()}


@router.post("/retry-failed")
async def retry_failed():
    """重刮失败列表（桌面版"重刮失败列表"按钮，走 Flags.again_dic → FileMode.Again）。"""
    from fastapi.concurrency import run_in_threadpool

    from mdcx.core.scraper import again_search
    from mdcx.models.flags import Flags

    if not Flags.again_dic:
        raise HTTPException(status_code=409, detail="没有失败列表可重刮")
    try:
        await run_in_threadpool(again_search)
    except JobAlreadyRunning as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {"ok": True, "count": len(Flags.new_again_dic) if hasattr(Flags, "new_again_dic") else None}
