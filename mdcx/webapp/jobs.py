"""刮削任务管理：web 后端封装 start_new_scrape / stop 生命周期。

与桌面版一致的单任务模型：同一时刻只有一个刮削任务（Flags 是全局单例）。
任务状态由总线事件驱动：change_buttons_status → running，
reset_buttons_status → idle（scraper 自然结束/停止完成时发出）。
"""

import asyncio
import threading
import time
from pathlib import Path

from mdcx.base.file import save_success_list
from mdcx.core.scraper import get_resume_state, start_new_scrape, start_resume_scrape
from mdcx.models.enums import FileMode
from mdcx.models.flags import Flags
from mdcx.signals import WebSignalBus, signal
from mdcx.utils import executor

from .jsonable import to_jsonable


class JobAlreadyRunning(RuntimeError):
    pass


class ScrapeJobManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.state = "idle"  # idle | running | stopping
        self.results: list[dict] = []
        self.progress = 0
        self.started_at = 0.0

    def attach_bus(self, bus: WebSignalBus) -> None:
        bus.subscribe(self._on_event)

    # region 总线事件 → 状态/结果累积
    def _on_event(self, name: str, args: tuple, seq: int = 0) -> None:
        if name == "exec_show_list_name":
            status, show_data, real_number = args
            with self._lock:
                self.results.append({"status": status, "real_number": real_number, "show": to_jsonable(show_data)})
        elif name == "change_buttons_status":
            if self.state != "stopping":
                self.state = "running"
        elif name == "reset_buttons_status":
            self.state = "idle"
        elif name == "exec_set_processbar":
            self.progress = args[0] if args else 0

    # endregion

    def start(self, mode: FileMode = FileMode.Default, movie_list: list | None = None) -> None:
        with self._lock:
            if self.state != "idle":
                raise JobAlreadyRunning("当前有任务正在运行或停止中")
            self.results.clear()
            self.progress = 0
            self.started_at = time.time()
        start_new_scrape(mode, [Path(p) for p in movie_list] if movie_list else None)

    def start_resume(self, remain_list: list) -> None:
        with self._lock:
            if self.state != "idle":
                raise JobAlreadyRunning("当前有任务正在运行或停止中")
            self.results.clear()
            self.progress = 0
            self.started_at = time.time()
        start_resume_scrape([Path(p) for p in remain_list])

    def start_single(self, file_path: str, appoint_url: str) -> None:
        """单文件刮削（桌面版工具页"单文件刮削"）：按网址识别站点后刮削指定文件。"""
        import os

        if not file_path:
            raise ValueError("请选择文件")
        if not os.path.isfile(file_path):
            raise ValueError(f"文件不存在: {file_path}")
        if not appoint_url:
            raise ValueError("请填写番号网址")
        from mdcx.config.extend import deal_url

        website, _ = deal_url(appoint_url.strip())
        if not website:
            raise ValueError(f"不支持的网站: {appoint_url}")
        with self._lock:
            if self.state != "idle":
                raise JobAlreadyRunning("当前有任务正在运行或停止中")
            self.results.clear()
            self.progress = 0
            self.started_at = time.time()
        from mdcx.models.flags import Flags

        Flags.single_file_path = Path(file_path)
        Flags.appoint_url = appoint_url.strip()
        Flags.website_name = website
        start_new_scrape(FileMode.Single)

    def resume_info(self) -> dict | None:
        state = get_resume_state()
        if state is None:
            return None
        return {
            "available": True,
            "count": len(state.remain_list),
            "first_path": str(state.first_path),
            "first_in_scan_dirs": state.first_in_scan_dirs,
            "scan_dirs": state.scan_dirs,
        }

    async def stop(self) -> None:
        """停止当前刮削。复刻桌面版停止流程（不含 _kill_threads 的 SystemExit hack）。"""
        with self._lock:
            if self.state != "running":
                return
            self.state = "stopping"
        Flags.stop_requested = True
        signal.stop = True
        try:
            await asyncio.to_thread(executor.run, save_success_list())
        finally:
            Flags.rest_time_convert_ = Flags.rest_time_convert
            Flags.rest_time_convert = 0
            signal.show_scrape_info("⛔️ 刮削停止中...")
            executor.cancel_async()

    def status(self) -> dict:
        with self._lock:
            state = self.state
            progress = self.progress
            result_count = len(self.results)
        running = state in ("running", "stopping")
        return {
            "state": state,
            "progress": progress,
            "results": result_count,
            "counts": {
                "succ": Flags.succ_count,
                "fail": Flags.fail_count,
                "done": Flags.scrape_done,
                "total": Flags.total_count,
                "skipped": Flags.skipped_count,
                "restored": Flags.restored_count,
            },
            "elapsed": round(time.time() - Flags.start_time, 1) if running and Flags.start_time else 0.0,
        }

    def list_results(self, status: str | None = None) -> list[dict]:
        with self._lock:
            results = list(self.results)
        if status in ("succ", "fail"):
            return [r for r in results if r["status"] == status]
        return results

    def clear_results(self) -> None:
        with self._lock:
            self.results.clear()
