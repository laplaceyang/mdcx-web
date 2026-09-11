"""网络检测 API。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from mdcx.webapp.network import CheckAlreadyRunning
from mdcx.webapp.runtime import network_manager

router = APIRouter(prefix="/api/network", tags=["network"])


class CheckRequest(BaseModel):
    retry_failed_only: bool = False


@router.post("/check")
async def check(req: CheckRequest):
    try:
        await network_manager.start(retry_failed_only=req.retry_failed_only)
        return {"ok": True}
    except CheckAlreadyRunning as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@router.post("/stop")
def stop():
    network_manager.stop()
    return {"ok": True}


@router.get("/results")
def results():
    return network_manager.snapshot()
