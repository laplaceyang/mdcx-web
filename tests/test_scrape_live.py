"""「刮削中」实时卡片追踪器（scrape_live）与刮削主流程挂点的集成测试。

走真实 process_one_file 包装层（含 finally 清理），桩掉文件探测与实际刮削，
验证：任务开始注册在途条目 → LogBuffer 日志实时归因 → 标题/图片中途补齐 →
任务结束（成功/失败/异常）条目移除。
"""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from mdcx.core import scrape_live
from mdcx.models.enums import FileMode
from mdcx.models.flags import Flags
from mdcx.models.model_types import CrawlersResult, FileInfo, OtherInfo


def _build_file_info(number: str) -> FileInfo:
    file_info = FileInfo.empty()
    file_info.number = number
    file_info.mosaic = "有码"
    file_info.file_path = Path(f"/movies/{number}.mp4")
    file_info.folder_path = Path("/movies")
    file_info.file_name = number
    file_info.file_ex = ".mp4"
    file_info.file_show_name = f"{number}.mp4"
    file_info.file_show_path = file_info.file_path
    file_info.sub_list = []
    return file_info


def _setup_scraper_test_env(monkeypatch: pytest.MonkeyPatch):
    from mdcx.core import scraper as scraper_module

    Flags.reset()
    scrape_live.reset()

    async def fake_get_file_info_v2(file_path):
        return _build_file_info("ABC-123")

    async def fake_check_file(*_args, **_kwargs):
        return True

    def fake_get_movie_path_setting(_file_path=None):
        return SimpleNamespace(success_folder=Path("."), movie_path=Path("."))

    original_sleep = asyncio.sleep

    async def fast_sleep(_seconds: float):
        await original_sleep(0)

    monkeypatch.setattr(scraper_module, "get_file_info_v2", fake_get_file_info_v2)
    monkeypatch.setattr(scraper_module, "check_file", fake_check_file)
    monkeypatch.setattr(scraper_module, "get_movie_path_setting", fake_get_movie_path_setting)
    monkeypatch.setattr(scraper_module.asyncio, "sleep", fast_sleep)
    monkeypatch.setattr(scraper_module.manager.config, "main_mode", 1)
    monkeypatch.setattr(scraper_module.manager.config, "file_size", "0")
    return scraper_module


@pytest.mark.asyncio
async def test_live_item_lifecycle_on_success(monkeypatch: pytest.MonkeyPatch):
    """成功路径：在途条目从注册到移除，日志/标题/图片中途可见。"""
    scraper_module = _setup_scraper_test_env(monkeypatch)
    scraper = scraper_module.Scraper(crawler_provider=object())
    snapshots_mid_flight: list = []

    async def fake_process_one_file(file_info, file_mode):
        # 模拟 _with_context 内部：写日志（应实时归因到在途条目）→ 元数据 → 图片
        from mdcx.models.log_buffer import LogBuffer

        LogBuffer.log().write("\n 🔍 [javbus] 搜索成功")
        assert scrape_live.snapshot(), "任务开始后应有在途条目"
        assert scrape_live.snapshot()[0]["last_log"] == "🔍 [javbus] 搜索成功"
        scrape_live.update_item(
            str(file_info.file_path), number="ABC-123", title="测试标题", actors=["演员A", "演员B"]
        )
        scrape_live.update_item(
            str(file_info.file_path), poster="/out/ABC-123-poster.jpg", thumb="/out/ABC-123-thumb.jpg"
        )
        snapshots_mid_flight.append(scrape_live.snapshot())
        return CrawlersResult.empty(), OtherInfo.empty()

    monkeypatch.setattr(scraper, "_process_one_file", fake_process_one_file)
    file_path = Path("/movies/ABC-123.mp4")
    Flags.remain_list = [file_path]

    file_info = await scraper_module.get_file_info_v2(file_path)
    await asyncio.wait_for(scraper.process_one_file((file_path, 1, 1)), timeout=5)

    # 任务结束：条目移除、tap 解绑
    assert scrape_live.snapshot() == []
    from mdcx.models.log_buffer import LogBuffer

    assert LogBuffer._taps == {}

    # 中途快照：元数据/图片已补齐
    assert len(snapshots_mid_flight) == 1
    item = snapshots_mid_flight[0][0]
    assert item["number"] == "ABC-123"
    assert item["title"] == "测试标题"
    assert item["actors"] == "演员A, 演员B"
    assert item["poster"] == "/out/ABC-123-poster.jpg"
    assert "🔍 [javbus] 搜索成功" in item["logs"]


@pytest.mark.asyncio
async def test_live_item_removed_on_failure(monkeypatch: pytest.MonkeyPatch):
    """失败路径（返回 None, None）：条目在任务结束时移除，且失败原因随结果推送。"""
    scraper_module = _setup_scraper_test_env(monkeypatch)
    scraper = scraper_module.Scraper(crawler_provider=object())

    # 在测试桩 signal 上包 spy，捕获 show_list_name 推送的结果
    captured: list[tuple] = []
    dummy = scraper_module.signal
    orig_show_list_name = getattr(dummy, "show_list_name", None)

    def spy_show_list_name(status, show_data, real_number=""):
        captured.append((status, show_data, real_number))
        if callable(orig_show_list_name):
            return orig_show_list_name(status, show_data, real_number)
        return None

    monkeypatch.setattr(dummy, "show_list_name", spy_show_list_name, raising=False)

    async def fake_process_one_file(_file_info, _file_mode):
        return None, None

    monkeypatch.setattr(scraper, "_process_one_file", fake_process_one_file)
    file_path = Path("/movies/ABC-123.mp4")
    Flags.remain_list = [file_path]

    await asyncio.wait_for(scraper.process_one_file((file_path, 1, 1)), timeout=5)

    assert scrape_live.snapshot() == []
    # 失败结果带失败原因（error 缓冲为空时回退「未知错误」）
    assert len(captured) == 1
    status, show_data, _number = captured[0]
    assert status == "fail"
    assert show_data.other.fail_reason == "未知错误"


@pytest.mark.asyncio
async def test_live_item_removed_when_scrape_raises(monkeypatch: pytest.MonkeyPatch):
    """桩抛错被 impl 转为失败处理：条目在任务结束时移除，不留幽灵。"""
    scraper_module = _setup_scraper_test_env(monkeypatch)
    scraper = scraper_module.Scraper(crawler_provider=object())

    async def fake_process_one_file(_file_info, _file_mode):
        raise RuntimeError("boom")

    monkeypatch.setattr(scraper, "_process_one_file", fake_process_one_file)
    file_path = Path("/movies/ABC-123.mp4")
    Flags.remain_list = [file_path]

    await asyncio.wait_for(scraper.process_one_file((file_path, 1, 1)), timeout=5)
    assert scrape_live.snapshot() == []
    from mdcx.models.log_buffer import LogBuffer

    assert LogBuffer._taps == {}
