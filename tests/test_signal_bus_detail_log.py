"""详情日志缓冲上限。

detail_log_list 只在有人调 get_log（前端轮询 /api/scrape/detail-log）时排空，
页面无人打开时会持续积压，必须有 maxlen 兜底防止无限增长。

conftest 用 _DummySignals 桩替换了 sys.modules["mdcx.signals"]，这里临时换入
真实模块做断言，结束后恢复桩，不影响其他测试。
"""

import importlib
import sys

import pytest


@pytest.fixture()
def real_signals():
    saved = sys.modules.pop("mdcx.signals", None)
    try:
        yield importlib.import_module("mdcx.signals")
    finally:
        if saved is not None:
            sys.modules["mdcx.signals"] = saved


def test_detail_log_trims_to_maxlen(real_signals):
    bus = real_signals.WebSignalBus()
    for i in range(5000):
        bus.add_log(f"line-{i}")

    text = bus.get_log()
    lines = text.strip().splitlines()
    assert len(lines) == 4000
    assert "line-0" not in text
    assert "line-1000" in text  # 尾部 4000 条里最旧的一条
    assert "line-4999" in text

    # get_log 排空后从零开始
    assert bus.get_log() == ""
    bus.add_log("next-round")
    assert bus.get_log().endswith("next-round")
