import pytest
from parsel import Selector

from mdcx.crawlers.missav import MissavCrawler


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        ("MIDV-999-U", "midv-999"),
        ("MIDV-0999-UC", "midv-999"),
        ("MIDV999U", "midv-999"),
        ("010101-123-U", "010101-123"),
        ("100225_100", "100225-100"),
        ("10musume_031426_01", "031426-01"),
        ("caribbeancom-031426-001", "031426-001"),
    ],
)
def test_normalize_number_for_uncensored_judge(number: str, expected: str):
    assert MissavCrawler._normalize_number_for_uncensored_judge(number) == expected


@pytest.mark.parametrize(
    ("number", "mosaic", "expected"),
    [
        ("MIDV-999-U", "无码破解", False),
        ("MIDV-999-UC", "无码", False),
        ("MIDV-999", "无码", False),
        ("HEYZO-1234-U", "有码", True),
        ("010101-123-U", "有码", True),
        ("100225_100", "有码", True),
        ("10musume_031426_01", "有码", True),
        ("caribbeancom-031426-001", "有码", True),
    ],
)
def test_should_use_uncensored_search_by_original_number(number: str, mosaic: str, expected: bool):
    assert MissavCrawler._should_use_uncensored_search(number, mosaic) is expected


def test_is_soft_404_page_detects_not_found_template():
    html = Selector(
        text="""
        <html>
            <head>
                <meta property="og:title" content="MissAV | 免費高清AV在線看" />
                <meta property="og:image" content="https://missav.ws/missav/logo-square.png" />
                <title>MissAV | 免費高清AV在線看</title>
            </head>
            <body>
                <p>404</p>
                <h1>找不到頁面</h1>
            </body>
        </html>
        """
    )

    assert MissavCrawler._is_soft_404_page(html) is True


def test_is_soft_404_page_ignores_normal_detail_page():
    html = Selector(
        text="""
        <html>
            <head>
                <meta property="og:title" content="SNOS-004 絶頂快感 - MissAV" />
                <meta property="og:image" content="https://fourhoi.com/snos-004/cover-n.jpg" />
                <title>SNOS-004 絶頂快感 - MissAV</title>
            </head>
            <body>
                <h1>SNOS-004 絶頂快感</h1>
                <p>發行日期：2024-01-01</p>
            </body>
        </html>
        """
    )

    assert MissavCrawler._is_soft_404_page(html) is False


# ============================================================
# Recombee 搜索结果番号校验（A-122B-016 案例回归）
# ============================================================


class TestPickMatchingItem:
    """_pick_matching_item：无 id 匹配时绝不能退回首条。"""

    def setup_method(self):
        from mdcx.crawlers.missav_api import MissavApiCrawler

        self.pick = MissavApiCrawler._pick_matching_item

    def test_no_match_returns_none_not_first(self):
        """搜索 A-122B-016 时首条是完全无关的 ymrk-016 → 必须返回 None。"""
        recomms = [
            {"id": "ymrk-016-uncensored-leak"},
            {"id": "ymrk-017"},
        ]
        assert self.pick(recomms, "a-122b-016") is None

    def test_exact_match(self):
        recomms = [{"id": "other-001"}, {"id": "a-122b-016"}]
        assert self.pick(recomms, "a-122b-016")["id"] == "a-122b-016"

    def test_uncensored_leak_prefix_match(self):
        recomms = [{"id": "ssis-200-uncensored-leak"}, {"id": "other-001"}]
        assert self.pick(recomms, "ssis-200")["id"] == "ssis-200-uncensored-leak"

    def test_alnum_equivalent_match(self):
        """id 分隔符形态不同（无横杠）时按 alphanumeric 等价匹配。"""
        recomms = [{"id": "a122b016"}, {"id": "other-001"}]
        assert self.pick(recomms, "a-122b-016")["id"] == "a122b016"

    def test_empty_recomms(self):
        assert self.pick([], "ssis-200") is None
