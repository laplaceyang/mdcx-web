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

    def _on_event(self, name: str, args: tuple) -> None:
        payload = {"type": "event", "event": name, "args": [to_jsonable(a) for a in args]}
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

    async def connect(self, ws: WebSocket) -> None:
        """接受一个 WS 客户端：先发快照（补发缓冲事件），再持续推送实时事件。"""
        await ws.accept()
        queue: asyncio.Queue = asyncio.Queue(maxsize=_MAX_CLIENT_QUEUE)
        with self._lock:
            self._next_id += 1
            client_id = self._next_id
            self._clients[client_id] = queue
        try:
            await ws.send_json({"type": "hello", "clients": len(self._clients)})
            for name, args in self.bus.replay_events():
                await ws.send_json({"type": "event", "event": name, "args": [to_jsonable(a) for a in args]})
            while True:
                payload = await queue.get()
                await ws.send_json(payload)
        except WebSocketDisconnect:
            pass
        finally:
            with self._lock:
                self._clients.pop(client_id, None)
