"""WebSocket 事件中心：把核心层的信号事件实时推送给前端。

事件可能从 executor 后台事件循环线程发出（刮削协程），通过
call_soon_threadsafe 投递到 uvicorn 主循环，再分发给每个客户端队列。
"""

import asyncio
import threading
from collections.abc import Callable

from fastapi import WebSocket, WebSocketDisconnect

from mdcx.signals import WebSignalBus

from .jsonable import to_jsonable

_MAX_CLIENT_QUEUE = 2000

# 断线重连补发的事件范围：日志/进度/状态提示类。结果列表（exec_show_list_name）
# 不补发——job_manager.results 是权威累计值，重连后由前端重新 GET /api/scrape/results
# 同步，避免逐条重放造成重复行（旧版每个新连接都全量重放缓冲，重连后成功列表
# 会出现成批重复、刷新才消失）
REPLAYABLE_EVENTS = frozenset(
    {
        "log_text",
        "net_info",
        "scrape_info",
        "set_label_file_path",
        "label_result",
        "logs_failed_settext",
        "logs_failed_show",
        "view_failed_list_settext",
        "view_success_file_settext",
        "exec_set_processbar",
    }
)


class EventHub:
    def __init__(self, bus: WebSignalBus):
        self.bus = bus
        self._loop: asyncio.AbstractEventLoop | None = None
        self._clients: dict[int, asyncio.Queue] = {}
        self._next_id = 0
        self._lock = threading.Lock()
        self._unsubscribe: Callable[[], None] | None = None
        self.dropped = 0

    def attach(self) -> None:
        """在应用启动（事件循环内）时订阅总线。"""
        self._loop = asyncio.get_running_loop()
        self._unsubscribe = self.bus.subscribe(self._on_event)

    def detach(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    def _on_event(self, name: str, args: tuple, seq: int = 0) -> None:
        payload = {"type": "event", "seq": seq, "event": name, "args": [to_jsonable(a) for a in args]}
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        with self._lock:
            queues = list(self._clients.values())
        if not queues:
            return

        def push() -> None:
            for q in queues:
                try:
                    q.put_nowait(payload)
                except asyncio.QueueFull:
                    self.dropped += 1  # 慢客户端丢事件，不阻塞核心刮削

        try:
            loop.call_soon_threadsafe(push)
        except RuntimeError:  # 循环已关闭（应用退出中）
            pass

    async def connect(self, ws: WebSocket, after: int = 0) -> None:
        """接受一个 WS 客户端：发快照 + 按 after 补发缺失事件，最后发 synced 标记。

        - after=客户端已处理的最大 seq：仅补发 (after, ∞) 内的可重放事件；
          客户端凭 seq 去重（补发与实时推送在注册瞬间可能重叠）
        - 补发与实时推送之间若有空洞（缓冲已溢出淘汰），客户端凭 synced 后
          的 seq 跳变检测并整体重新拉取
        """
        await ws.accept()
        queue: asyncio.Queue = asyncio.Queue(maxsize=_MAX_CLIENT_QUEUE)
        with self._lock:
            self._next_id += 1
            client_id = self._next_id
            self._clients[client_id] = queue
        try:
            await ws.send_json({"type": "hello", "clients": len(self._clients), "seq": self.bus.last_seq})
            for seq, name, args in self.bus.replay_events(after):
                if name not in REPLAYABLE_EVENTS:
                    continue
                await ws.send_json({"type": "event", "seq": seq, "event": name, "args": [to_jsonable(a) for a in args]})
            await ws.send_json({"type": "synced"})
            while True:
                payload = await queue.get()
                await ws.send_json(payload)
        except WebSocketDisconnect:
            pass
        finally:
            with self._lock:
                self._clients.pop(client_id, None)
