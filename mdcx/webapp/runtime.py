"""webapp 运行时单例。

关键顺序：必须先创建 WebSignalBus 并 set_signal，再导入任何会触发核心链路的模块
（hub/jobs/routers）。核心层通过 `signal` 代理访问总线，因此这里的切换对任何
导入时机的模块都生效。
"""

from mdcx.signals import WebSignalBus, set_signal

bus = WebSignalBus()
set_signal(bus)

from .hub import EventHub  # noqa: E402
from .jobs import ScrapeJobManager  # noqa: E402
from .network import NetworkCheckManager  # noqa: E402

hub = EventHub(bus)
job_manager = ScrapeJobManager()
job_manager.attach_bus(bus)
network_manager = NetworkCheckManager()
