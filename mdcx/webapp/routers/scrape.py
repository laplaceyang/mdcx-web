"""刮削任务 API。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from mdcx.core.scraper import get_resume_state
from mdcx.models.enums import FileMode
from mdcx.webapp.jobs import JobAlreadyRunning
from mdcx.webapp.runtime import job_manager

router = APIRouter(prefix="/api/scrape", tags=["scrape"])


class StartRequest(BaseModel):
    mode: str = "default"  # default | again
    movie_list: list[str] | None = None  # 指定文件列表（不传则按配置扫描）
    resume: bool = False  # true 时按 remain.txt 续刮


@router.get("/status")
def status():
    return job_manager.status()


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
