"""无头导入守卫。

web 后端必须能在未安装 PyQt6 的环境运行核心链路。本测试用子进程 + 导入拦截器
模拟"未安装 PyQt6"的环境，验证核心模块可导入且 WebSignalBus 行为正确。

若此测试失败，说明有人往核心层（crawlers/core/base/config/tools）新加了
模块级 PyQt6 导入——请把 Qt 相关代码移入 views/controllers，或改用
`mdcx.signals.signal`（代理总线）而非直接依赖 Qt 类型。
"""

import subprocess
import sys

PROBE = """
import importlib.abc
import sys


class BlockPyQt6(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "PyQt6" or fullname.startswith("PyQt6."):
            raise ImportError(f"blocked: {fullname}")
        return None


sys.meta_path.insert(0, BlockPyQt6())

import mdcx.core.scraper  # noqa: F401
import mdcx.cmd.crawl  # noqa: F401
import mdcx.crawlers  # noqa: F401
import mdcx.web_async  # noqa: F401
import mdcx.tools.actor_db_tool  # noqa: F401
import mdcx.tools.emby_actor_manager  # noqa: F401
import mdcx.config.resources  # noqa: F401
import mdcx.image  # noqa: F401
from mdcx.signals import WebSignalBus, set_signal, signal

bus = WebSignalBus()
set_signal(bus)
signal.show_log_text("hello")
signal.exec_set_processbar.emit(42)
seen = []
unsubscribe = bus.subscribe(lambda name, args: seen.append((name, args)))
signal.change_buttons_status.emit()
unsubscribe()
signal.exec_exit_app.emit()

assert seen == [("change_buttons_status", ())], seen
replay_names = [name for name, _ in bus.replay_events()]
assert "log_text" in replay_names and "exec_set_processbar" in replay_names, replay_names
signal.stop = False
assert bus.stop is False
print("HEADLESS IMPORT OK")
"""


def test_core_imports_without_pyqt6():
    result = subprocess.run([sys.executable, "-c", PROBE], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "HEADLESS IMPORT OK" in result.stdout
