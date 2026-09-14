"""事件总线（无头版）。

业务层通过 `from ..signals import signal` 获取全局总线，向 UI 层回传日志、进度、结果等事件。
由 `WebSignalBus` 承载：事件先写入 replay 环形缓冲（供 WS 客户端断线重连补发），再通知
订阅者；webapp 订阅事件并经 WebSocket 推送给前端。

`signal` 是转发代理：业务模块在导入时绑定的始终是同一个代理实例，代理把属性读写转发给
当前实现，因此 set_signal() 在任何导入时机之后切换实现都能生效，不会留下旧引用。
"""

import threading
import time
from collections import deque
from collections.abc import Callable
from contextlib import suppress
from typing import Any, Literal

from .models.model_types import ShowData
from .utils import singleton

# 事件名清单：与 Signals 上的 Qt 信号一一对应，WebSignalBus 按此建同名事件
EVENT_NAMES: tuple[str, ...] = (
    "log_text",
    "scrape_info",
    "net_info",
    "exec_set_main_info",
    "change_buttons_status",
    "reset_buttons_status",
    "set_label_file_path",
    "label_result",
    "logs_failed_settext",
    "view_success_file_settext",
    "exec_set_processbar",
    "exec_exit_app",
    "view_failed_list_settext",
    "exec_show_list_name",
    "logs_failed_show",
)


class _Event:
    """无头模式的轻量事件：emit 时同步回调订阅者（在发射者线程执行）。"""

    def __init__(self) -> None:
        self._subscribers: list[Callable[..., None]] = []

    def connect(self, callback: Callable[..., None]) -> None:
        self._subscribers.append(callback)

    def disconnect(self, callback: Callable[..., None] | None = None) -> None:
        if callback is None:
            self._subscribers.clear()
        else:
            with suppress(ValueError):
                self._subscribers.remove(callback)

    def emit(self, *args: Any) -> None:
        for callback in tuple(self._subscribers):
            with suppress(Exception):
                callback(*args)


class WebSignalBus:
    """web 后端的无头信号总线，与桌面 `Signals` 鸭子类型兼容。

    - 同名事件属性（.emit/.connect/.disconnect），emit 先写入 replay 环形缓冲再通知
      订阅者，供 WS 客户端断线重连后补发错过的日志/进度
    - 每条事件带全局递增 seq：WS 客户端凭 lastSeq 去重重连补发、检测丢失
    - 订阅回调签名统一为 callback(event_name, args, seq)，在发射者线程同步执行；
      跨线程投递（核心跑在 executor 的后台事件循环）由订阅者自行 call_soon_threadsafe
    - add_log/get_log 保留原详情日志缓冲语义
    """

    def __init__(self, replay_size: int = 2000) -> None:
        self.log_lock = threading.Lock()
        self.detail_log_list: list[str] = []
        self.stop = False
        self._events: dict[str, _BusEvent] = {}
        self._replay: deque[tuple[int, str, tuple[Any, ...]]] = deque(maxlen=replay_size)
        self._replay_lock = threading.Lock()
        self._seq = 0
        # emit → 订阅回调在同一线程同步执行，用 thread-local 传递本次事件的 seq，
        # 避免多线程并发 emit 时共享变量串号；支持回调内嵌套 emit（弹出时恢复）
        self._emit_tls = threading.local()
        for name in EVENT_NAMES:
            self._events[name] = _BusEvent(self, name)

    def __getattr__(self, name: str) -> Any:
        try:
            return self.__dict__["_events"][name]
        except KeyError:
            raise AttributeError(name) from None

    # region 与 Signals 相同的便捷方法
    def add_log(self, *text: Any) -> None:
        if self.stop:
            return
        try:
            with self.log_lock:
                self.detail_log_list.append(f" ⏰ {time.strftime('%H:%M:%S', time.localtime())} {' '.join(text)}")
        except Exception:
            pass

    def get_log(self) -> str:
        with self.log_lock:
            text = "\n".join(self.detail_log_list)
            self.detail_log_list = []
        return text

    def show_traceback_log(self, text: str) -> None:
        with suppress(Exception):
            print(text)
        self.add_log(text)

    def show_log_text(self, text: str) -> None:
        self.log_text.emit(text)

    def show_scrape_info(self, before_info: str = "") -> None:
        self.scrape_info.emit(before_info)

    def show_net_info(self, text: str) -> None:
        self.net_info.emit(text)

    def set_main_info(self, show_data: ShowData | None = None) -> None:
        if show_data is None:
            show_data = ShowData.empty()
        self.exec_set_main_info.emit(show_data)

    def show_list_name(self, status: Literal["succ", "fail"], show_data: ShowData, real_number: str = "") -> None:
        self.exec_show_list_name.emit(status, show_data, real_number)

    # endregion

    def subscribe(self, callback: Callable[[str, tuple[Any, ...], int], None]) -> Callable[[], None]:
        """订阅全部事件，返回取消订阅函数。

        与事件本身的 Qt 风格透传（emit(*args) 原样转发）不同，这里统一聚合签名：
        callback(event_name, args_tuple, seq)。
        """
        wired: list[tuple[_Event, Callable[..., None]]] = []
        for name, event in self._events.items():

            def on_event(*args: Any, _name: str = name) -> None:
                callback(_name, args, getattr(self._emit_tls, "seq", 0))

            event.connect(on_event)
            wired.append((event, on_event))

        def unsubscribe() -> None:
            for event, on_event in wired:
                event.disconnect(on_event)

        return unsubscribe

    def replay_events(self, after: int = 0) -> list[tuple[int, str, tuple[Any, ...]]]:
        """返回 seq > after 的事件（供 WS 断线重连补发）。"""
        with self._replay_lock:
            return [(seq, name, args) for seq, name, args in self._replay if seq > after]

    @property
    def last_seq(self) -> int:
        """最近一条已记录事件的 seq（并发下读到的可能略旧，仅用于展示/握手指引）。"""
        with self._replay_lock:
            return self._seq

    def _record(self, name: str, args: tuple[Any, ...]) -> int:
        with self._replay_lock:
            self._seq += 1
            self._replay.append((self._seq, name, args))
            return self._seq


class _BusEvent(_Event):
    """带总线记录的事件：emit 时先写 replay 缓冲，再以 thread-local seq 通知订阅者。"""

    def __init__(self, bus: WebSignalBus, name: str) -> None:
        super().__init__()
        self._bus = bus
        self._name = name

    def emit(self, *args: Any) -> None:
        seq = self._bus._record(self._name, args)
        tls = self._bus._emit_tls
        prev = getattr(tls, "seq", None)
        tls.seq = seq
        try:
            super().emit(*args)
        finally:
            if prev is None:
                del tls.seq
            else:
                tls.seq = prev


signal_qt = WebSignalBus()  # 兼容历史名称


class _SignalProxy:
    """把属性读写转发给当前实现的代理。

    业务层 `from ..signals import signal` 在导入时绑定的始终是本代理实例，
    set_signal() 切换实现后仍能转发到最新实现，避免旧引用悬空。
    """

    def __init__(self, impl: Any) -> None:
        object.__setattr__(self, "_impl", impl)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._impl, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "_impl":
            object.__setattr__(self, name, value)
            return
        setattr(self._impl, name, value)


signal: Any = _SignalProxy(signal_qt)


def set_signal(signal_instance: Any) -> None:
    """切换全局信号实现（web 后端切换为 WebSignalBus；测试注入桩对象）。"""
    signal._impl = signal_instance
