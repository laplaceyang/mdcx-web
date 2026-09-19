"""在途刮削条目实时追踪（刮削页「刮削中」卡片视图的数据源）。

每个刮削任务开始时注册条目（文件路径/番号），刮削过程中标题、演员、
图片、最新日志逐步补齐（日志经 LogBuffer 的 root tap 实时归因）；
任务协程结束时（成功/失败/手动停止/异常，一律走 process_one_file 的
finally）移除条目——完成后的结果改由 /api/scrape/results 呈现。
前端经 /api/scrape/active 轮询快照，与 WS 推送解耦，避免刷屏 replay 缓冲。

追踪器自身的任何故障都不允许影响刮削主流程：公开接口统一吞异常。
"""

import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable

# 安全上限：并发数通常是个位数，正常远达不到；防异常场景内存无界
_MAX_ITEMS = 500
_LOG_LINES = 6

_lock = threading.Lock()
_items: OrderedDict[str, dict] = OrderedDict()
_roots: dict[int, str] = {}


def reset() -> None:
    """新任务开始时清空上一轮的在途条目。"""
    try:
        with _lock:
            _items.clear()
            _roots.clear()
    except Exception:
        pass


def start_item(file_path: str, show_path: str = "", number: str = "") -> None:
    try:
        with _lock:
            if file_path in _items:
                return
            if len(_items) >= _MAX_ITEMS:
                _items.popitem(last=False)
            _items[file_path] = {
                "file_path": file_path,
                "show_path": show_path,
                "number": number,
                "title": "",
                "actors": "",
                "poster": "",
                "thumb": "",
                "started_at": time.time(),
                "logs": deque(maxlen=_LOG_LINES),
            }
    except Exception:
        pass


def bind_root(root: int | None, file_path: str) -> None:
    """把 LogBuffer 任务组 root 归因到条目：该组此后写入的每行日志实时进条目。"""
    if root is None:
        return

    def _on_line(line: str) -> None:
        append_log(file_path, line)

    try:
        from ..models.log_buffer import LogBuffer

        with _lock:
            _roots[root] = file_path
        LogBuffer.bind_tap(root, _on_line)
    except Exception:
        pass


def update_item(
    file_path: str,
    *,
    number: str | None = None,
    title: str | None = None,
    actors: list | tuple | str | None = None,
    poster: str | None = None,
    thumb: str | None = None,
) -> None:
    try:
        with _lock:
            item = _items.get(file_path)
            if item is None:
                return
            if number:
                item["number"] = str(number)
            if title:
                item["title"] = str(title)
            if actors:
                item["actors"] = ", ".join(actors) if isinstance(actors, (list, tuple)) else str(actors)
            if poster:
                item["poster"] = str(poster)
            if thumb:
                item["thumb"] = str(thumb)
    except Exception:
        pass


def append_log(file_path: str, line: str) -> None:
    try:
        text = " ".join(str(line).split())
        if not text:
            return
        with _lock:
            item = _items.get(file_path)
            if item is None:
                return
            if item["logs"] and item["logs"][-1] == text:
                return
            item["logs"].append(text)
    except Exception:
        pass


def finish_root(root: int | None) -> None:
    """任务协程结束（finally）时按 root 移除日志 tap 与在途条目。"""
    if root is None:
        return
    try:
        from ..models.log_buffer import LogBuffer

        LogBuffer.remove_tap(root)
    except Exception:
        pass
    try:
        with _lock:
            file_path = _roots.pop(root, None)
            if file_path is not None:
                _items.pop(file_path, None)
    except Exception:
        pass


def snapshot() -> list[dict]:
    """当前全部在途条目（按开始时间先后），供 /api/scrape/active 返回。"""
    try:
        with _lock:
            items = [
                {
                    "file_path": it["file_path"],
                    "show_path": it["show_path"],
                    "number": it["number"],
                    "title": it["title"],
                    "actors": it["actors"],
                    "poster": it["poster"],
                    "thumb": it["thumb"],
                    "started_at": it["started_at"],
                    "elapsed": round(max(0.0, time.time() - it["started_at"]), 1),
                    "last_log": it["logs"][-1] if it["logs"] else "",
                    "logs": list(it["logs"]),
                }
                for it in _items.values()
            ]
        return items
    except Exception:
        return []
