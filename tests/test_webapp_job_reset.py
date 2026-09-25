"""点开始后计数必须同步清零（进度条闪 100% 回 0 的回归测试）。

背景：计数的正式重置在异步 run 开头，而 POST /api/scrape/start 立即返回、
前端随即拉 /status。若启动入口不同步清零，上一轮的 done/total 会被当成
新任务进度，进度条先闪一下旧任务的 100% 再回 0。
"""

import importlib
import sys
from pathlib import Path

import pytest

from mdcx.models.enums import FileMode
from mdcx.models.flags import Flags

# conftest 给 mdcx.signals 装的桩没有 WebSignalBus（webapp.jobs 依赖它）；
# 真实模块是无头纯实现，弹掉桩换真身（setdefault 桩仅在真身未加载时生效）
sys.modules.pop("mdcx.signals", None)
importlib.import_module("mdcx.signals")

import mdcx.webapp.jobs as jobs_mod  # noqa: E402
from mdcx.webapp.jobs import JobAlreadyRunning, ScrapeJobManager  # noqa: E402


@pytest.fixture()
def mgr(monkeypatch):
    """桩掉异步启动：只测启动入口自身的同步行为。"""
    monkeypatch.setattr(jobs_mod, "start_new_scrape", lambda *a, **k: None)
    monkeypatch.setattr(jobs_mod, "start_resume_scrape", lambda *a, **k: None)
    return ScrapeJobManager()


def _seed_previous_run() -> None:
    Flags.total_count = 36
    Flags.scrape_started = 36
    Flags.scrape_done = 33
    Flags.succ_count = 29
    Flags.fail_count = 4
    Flags.skipped_count = 2
    Flags.restored_count = 1


def _assert_counts_zero() -> None:
    assert Flags.total_count == 0
    assert Flags.scrape_started == 0
    assert Flags.scrape_done == 0
    assert Flags.succ_count == 0
    assert Flags.fail_count == 0
    assert Flags.skipped_count == 0
    assert Flags.restored_count == 0


def test_start_resets_counts_synchronously(mgr):
    _seed_previous_run()
    mgr.start(FileMode.Default, [])
    _assert_counts_zero()
    assert mgr.results == []
    assert mgr.progress == 0


def test_start_resume_resets_counts_synchronously(mgr):
    _seed_previous_run()
    mgr.start_resume([])
    _assert_counts_zero()


def test_start_single_resets_counts_synchronously(mgr, tmp_path):
    _seed_previous_run()
    f = tmp_path / "a.mp4"
    f.write_bytes(b"x")
    mgr.start_single(str(f), "https://www.javbus.com/ABC-123")
    _assert_counts_zero()
    # 单文件输入在清零后仍须保留
    assert Flags.single_file_path == f


def test_start_rejects_double_run(mgr):
    mgr.state = "running"
    with pytest.raises(JobAlreadyRunning):
        mgr.start(FileMode.Default, [])
