"""Amazon 连接熔断器单元测试。

背景：amazon.co.jp 在部分网络环境整体不可达（连接挂起无响应），一次高清海报搜索要
烧完所有重试超时（可达数分钟）。熔断器在连续网络级失败后短路后续请求。
"""

import pytest

from mdcx.base import web as base_web


@pytest.fixture(autouse=True)
def _reset_breaker():
    with base_web._AMAZON_BREAKER_LOCK:
        base_web._AMAZON_BREAKER["fails"] = 0
        base_web._AMAZON_BREAKER["opened_at"] = 0.0
    yield
    with base_web._AMAZON_BREAKER_LOCK:
        base_web._AMAZON_BREAKER["fails"] = 0
        base_web._AMAZON_BREAKER["opened_at"] = 0.0


def _record(html, error):
    base_web._amazon_breaker_record(html, error)


def test_breaker_opens_after_consecutive_network_failures():
    assert not base_web._amazon_breaker_open()
    _record(None, "GET https://www.amazon.co.jp/s 失败: 连接超时")
    assert not base_web._amazon_breaker_open()
    _record(None, "GET https://www.amazon.co.jp/s 失败: 连接超时")
    assert base_web._amazon_breaker_open()


def test_breaker_resets_on_any_response():
    _record(None, "失败: 连接超时")
    # 拿到 HTTP 状态（哪怕是 503 反爬页）说明站点可达
    _record("<html>robot check</html>", "")
    assert not base_web._amazon_breaker_open()


def test_breaker_resets_on_http_status_error():
    _record(None, "失败: 连接超时")
    _record(None, "GET https://www.amazon.co.jp/s 失败: HTTP 503 body=Service Unavailable")
    assert not base_web._amazon_breaker_open()


def test_breaker_ignores_non_network_errors():
    _record(None, "文本解析失败: boom")
    assert not base_web._amazon_breaker_open()


def test_breaker_half_open_after_cooldown(monkeypatch):
    _record(None, "失败: 连接超时")
    _record(None, "失败: 连接超时")
    assert base_web._amazon_breaker_open()
    # 把打开时间拨回 31 分钟前 → 冷却已过，放行一次探测
    with base_web._AMAZON_BREAKER_LOCK:
        base_web._AMAZON_BREAKER["opened_at"] -= base_web._AMAZON_BREAKER_COOLDOWN + 60
    assert not base_web._amazon_breaker_open()
    # 探测仍失败 → 立即再次熔断
    _record(None, "失败: 连接超时")
    assert base_web._amazon_breaker_open()


@pytest.mark.asyncio
async def test_get_amazon_data_short_circuits_when_open():
    with base_web._AMAZON_BREAKER_LOCK:
        base_web._AMAZON_BREAKER["fails"] = base_web._AMAZON_BREAKER_THRESHOLD
        base_web._AMAZON_BREAKER["opened_at"] = __import__("time").time()
    ok, error = await base_web.get_amazon_data("https://www.amazon.co.jp/s?k=x")
    assert ok is False
    assert "熔断" in error
