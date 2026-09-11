"""网络检测任务管理：包装 core/network_check.py 的无头检测流程。

检测进度行通过总线 net_info 事件推送；结构化结果存内存供查询。
同一时刻只允许一轮检测（与桌面版一致）。
"""

import asyncio
import threading

from mdcx.core.network_check import (
    NetworkCheckResult,
    NetworkCheckStatus,
    run_network_check,
)
from mdcx.signals import signal

from .jsonable import to_jsonable


class CheckAlreadyRunning(RuntimeError):
    pass


class NetworkCheckManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.running = False
        self.results: list[dict] = []
        self._raw: list[NetworkCheckResult] = []
        self._cancel_event: threading.Event | None = None

    async def start(self, retry_failed_only: bool = False) -> None:
        with self._lock:
            if self.running:
                raise CheckAlreadyRunning("网络检测正在进行中")
            prev_raw = self._raw  # 重测失败项要用上一轮结果，先取再清
            self.running = True
            self.results = []
            self._raw = []
            self._cancel_event = threading.Event()

        async def run() -> None:
            try:
                if retry_failed_only:
                    failed = [r.spec for r in prev_raw if r.status != NetworkCheckStatus.OK]
                    specs = failed or None  # 没有失败项时退化为全量
                else:
                    specs = None
                results = await run_network_check(
                    progress=signal.show_net_info,
                    cancel_event=self._cancel_event,
                    specs=specs,
                )
                self._raw = results
                self.results = [to_jsonable(r) for r in results]
                signal.show_net_info("✅ 网络检测完成")
            except Exception as e:  # noqa: BLE001 检测异常不能打穿后台任务
                signal.show_net_info(f"❌ 网络检测异常: {e}")
            finally:
                self.running = False

        asyncio.create_task(run())

    def stop(self) -> None:
        if self._cancel_event is not None:
            self._cancel_event.set()

    def snapshot(self) -> dict:
        with self._lock:
            return {"running": self.running, "results": list(self.results)}
