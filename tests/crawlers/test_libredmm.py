from mdcx.crawlers.libredmm import _build_aws_cover_candidates, _build_aws_poster_candidates


def test_cover_candidates_ssis_no_prefix():
    assert _build_aws_cover_candidates("SSIS-001") == [
        "https://awsimgsrc.dmm.co.jp/pics_dig/digital/video/ssis00001/ssis00001pl.jpg"
    ]


def test_poster_candidates_ssis_no_prefix():
    assert _build_aws_poster_candidates("SSIS-001", "") == [
        "https://awsimgsrc.dmm.co.jp/pics_dig/digital/video/ssis00001/ssis00001ps.jpg"
    ]


def test_poster_candidates_prefixed_series():
    assert _build_aws_poster_candidates("WANZ-100", "")[0] == (
        "https://awsimgsrc.dmm.co.jp/pics_dig/digital/video/3wanz00100/3wanz00100ps.jpg"
    )
    assert _build_aws_poster_candidates("SW-123", "") == [
        "https://awsimgsrc.dmm.co.jp/pics_dig/digital/video/1sw00123/1sw00123ps.jpg",
        "https://awsimgsrc.dmm.co.jp/pics_dig/digital/video/sw00123/sw00123ps.jpg",
        "https://awsimgsrc.dmm.co.jp/pics_dig/digital/video/h_113sw00123/h_113sw00123ps.jpg",
    ]


def test_poster_candidates_thumb_suffix_fallback():
    thumb = "https://awsimgsrc.dmm.co.jp/pics_dig/digital/video/ipx00535/ipx00535pl.jpg"
    candidates = _build_aws_poster_candidates("IPX-535", thumb)
    assert "https://awsimgsrc.dmm.co.jp/pics_dig/digital/video/ipx00535/ipx00535ps.jpg" in candidates


def test_cover_candidates_only_landscape():
    for url in _build_aws_cover_candidates("IPX-535"):
        assert url.endswith("pl.jpg")


def test_poster_candidates_only_portrait():
    for url in _build_aws_poster_candidates("IPX-535", ""):
        assert url.endswith("ps.jpg")


# ============================================================
# 番号不匹配防护（A-122B-016 案例回归）
# ============================================================

_DETAIL_HTML = """
<html><body>
  <h1><span>{number}</span><span>{title}</span></h1>
  <div class="info">{number}</div>
</body></html>
"""


class _FakeClient:
    def __init__(self, html: str):
        self._html = html

    async def get_text(self, url, **kwargs):
        return self._html, None


def _make_crawler(html: str):
    from mdcx.crawlers.libredmm import LibredmmCrawler

    return LibredmmCrawler(client=_FakeClient(html), base_url="https://www.libredmm.com")


def _make_input(number: str):
    from mdcx.models.model_types import CrawlerInput

    inp = CrawlerInput.empty()
    inp.number = number
    return inp


def test_number_mismatch_rejected():
    """搜索重定向到其它影片（页面番号 B-016 ≠ 请求 A-122B-016）必须拒绝。

    run() 把 CrawlerException 包装进 debug_info.error（data=None）。
    """
    import asyncio

    crawler = _make_crawler(_DETAIL_HTML.format(number="B-016", title="バスという密室で…"))
    res = asyncio.run(crawler.run(_make_input("A-122B-016")))
    assert res.data is None
    assert "番号不匹配" in str(res.debug_info.error)


def test_number_match_accepted():
    """页面番号与请求一致时正常解析。"""
    import asyncio

    crawler = _make_crawler(_DETAIL_HTML.format(number="A-122B-016", title="テストタイトル"))
    res = asyncio.run(crawler.run(_make_input("A-122B-016")))
    assert res.data is not None
    assert res.data.number == "A-122B-016"
    assert res.data.title == "テストタイトル"
