"""回归测试: emby_video_manager 的列表查询与缩略图 URL 拼装。

fake client 模式同 test_emby_actor_manager_http.py：patch
``manager.acquire_computed`` 注入 fake lease，断言请求 URL 参数与结果映射。
"""

from __future__ import annotations

import importlib
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# conftest 给 mdcx.signals 装的桩没有 WebSignalBus（webapp.runtime 依赖它），
# 测 router 映射前先还原真实模块（同 test_manual_scrape_naming.py 的做法）
sys.modules.pop("mdcx.signals", None)
importlib.import_module("mdcx.signals")


def _make_lease(client):
    lease = MagicMock()
    lease.__aenter__ = AsyncMock(return_value=MagicMock(async_client=client))
    lease.__aexit__ = AsyncMock(return_value=False)
    return lease


@pytest.fixture
def server_config(monkeypatch):
    from mdcx.config.manager import manager

    monkeypatch.setattr(manager.config, "api_key", "test-token")
    monkeypatch.setattr(manager.config, "emby_url", "http://test:8096/")
    monkeypatch.setattr(manager.config, "server_type", "emby")
    monkeypatch.setattr(manager.config, "user_id", "user-1")


def _video_item(item_id: str, name: str) -> dict:
    return {
        "Id": item_id,
        "Name": name,
        "Type": "Movie",
        "ProductionYear": 2024,
        "Path": f"/media/{name}.mp4",
        "Size": 1024 * 1024 * 1024,
        "DateCreated": "2026-09-20T10:00:00Z",
        "ProviderIds": {"imdb": "tt0000001"},
        "ImageTags": {"Primary": "imgtag"},
    }


@pytest.mark.asyncio
async def test_get_video_items_success(server_config):
    from mdcx.tools.emby_video_manager import get_video_items

    fake_client = MagicMock()
    fake_client.get_json = AsyncMock(return_value=({"Items": [_video_item("v1", "A")], "TotalRecordCount": 21}, ""))

    with patch("mdcx.tools.emby_video_manager.manager.acquire_computed", return_value=_make_lease(fake_client)):
        items, total = await get_video_items("lib-1", start_index=200, limit=100, keyword="ABC-1")

    assert total == 21
    assert items[0]["Id"] == "v1"
    url = fake_client.get_json.await_args.args[0]
    assert "/emby/Items?" in url
    for frag in ("ParentId=lib-1", "Recursive=true", "IncludeItemTypes=Movie%2CEpisode%2CVideo%2CMusicVideo"):
        assert frag in url, url
    assert "StartIndex=200" in url and "Limit=100" in url
    assert "SearchTerm=ABC-1" in url


@pytest.mark.asyncio
async def test_get_video_items_searchterm_encoded(server_config):
    from mdcx.tools.emby_video_manager import get_video_items

    fake_client = MagicMock()
    fake_client.get_json = AsyncMock(return_value=({"Items": [], "TotalRecordCount": 0}, ""))

    with patch("mdcx.tools.emby_video_manager.manager.acquire_computed", return_value=_make_lease(fake_client)):
        await get_video_items("lib-1", keyword="A B")

    url = fake_client.get_json.await_args.args[0]
    assert "SearchTerm=A+B" in url


@pytest.mark.asyncio
async def test_get_video_items_include_types_override(server_config):
    """电视剧库传 include_types="Series" 按剧归组。"""
    from mdcx.tools.emby_video_manager import get_video_items

    fake_client = MagicMock()
    fake_client.get_json = AsyncMock(return_value=({"Items": [_video_item("s1", "剧")], "TotalRecordCount": 1}, ""))

    with patch("mdcx.tools.emby_video_manager.manager.acquire_computed", return_value=_make_lease(fake_client)):
        await get_video_items("lib-tv", include_types="Series")

    url = fake_client.get_json.await_args.args[0]
    assert "IncludeItemTypes=Series" in url
    assert "Episode" not in url


@pytest.mark.asyncio
async def test_get_video_items_failure_raises(server_config):
    from mdcx.tools.emby_video_manager import get_video_items

    fake_client = MagicMock()
    fake_client.get_json = AsyncMock(return_value=(None, "HTTP 502"))

    with patch("mdcx.tools.emby_video_manager.manager.acquire_computed", return_value=_make_lease(fake_client)):
        with pytest.raises(RuntimeError, match="HTTP 502"):
            await get_video_items("lib-1")


@pytest.mark.asyncio
async def test_get_video_items_jellyfin_branch(monkeypatch):
    from mdcx.config.manager import manager
    from mdcx.tools.emby_video_manager import get_video_items

    monkeypatch.setattr(manager.config, "api_key", "test-token")
    monkeypatch.setattr(manager.config, "emby_url", "http://jf:8096")
    monkeypatch.setattr(manager.config, "server_type", "ln")
    monkeypatch.setattr(manager.config, "user_id", "user-1")

    fake_client = MagicMock()
    fake_client.get_json = AsyncMock(return_value=({"Items": [_video_item("v1", "A")], "TotalRecordCount": 1}, ""))

    with patch("mdcx.tools.emby_video_manager.manager.acquire_computed", return_value=_make_lease(fake_client)):
        items, total = await get_video_items("lib-2")

    assert total == 1 and items[0]["Id"] == "v1"
    url = fake_client.get_json.await_args.args[0]
    assert url.startswith("http://jf:8096/Items?")
    assert "userId=user-1" in url
    assert "/emby/" not in url


@pytest.mark.asyncio
async def test_get_media_libraries_failure_raises(server_config):
    from mdcx.tools.emby_video_manager import get_media_libraries

    fake_client = MagicMock()
    fake_client.get_json = AsyncMock(return_value=(None, "connect timeout"))

    with patch("mdcx.tools.emby_video_manager.manager.acquire_computed", return_value=_make_lease(fake_client)):
        with pytest.raises(RuntimeError, match="connect timeout"):
            await get_media_libraries()


def test_video_image_url_emby(server_config):
    from mdcx.tools.emby_video_manager import video_image_url

    url = video_image_url("v1", "imgtag")
    assert url.startswith("http://test:8096/emby/Items/v1/Images/Primary?")
    assert "api_key=test-token" in url and "tag=imgtag" in url and "maxWidth=200" in url


def test_video_image_url_jellyfin(monkeypatch):
    from mdcx.config.manager import manager
    from mdcx.tools.emby_video_manager import video_image_url

    monkeypatch.setattr(manager.config, "api_key", "test-token")
    monkeypatch.setattr(manager.config, "emby_url", "http://jf:8096")
    monkeypatch.setattr(manager.config, "server_type", "ln")

    url = video_image_url("v1")
    assert url.startswith("http://jf:8096/Items/v1/Images/Primary?")
    assert "/emby/" not in url


def test_map_video():
    from mdcx.webapp.routers import emby as router_module

    item = _video_item("v1", "A")
    mapped = router_module._map_video(item)
    assert mapped == {
        "id": "v1",
        "name": "A",
        "type": "Movie",
        "number": mapped["number"],  # 番号提取单独断言
        "year": 2024,
        "path": "/media/A.mp4",
        "size": 1024 * 1024 * 1024,
        "provider_ids": {"imdb": "tt0000001"},
        "date_created": "2026-09-20",
        "has_image": True,
        "thumb": mapped["thumb"],  # URL 形态单独断言
        "image": mapped["image"],
    }
    assert "/api/emby/video-image?item_id=v1&max_width=200&tag=imgtag" == mapped["thumb"]
    assert "/api/emby/video-image?item_id=v1&max_width=1200&tag=imgtag" == mapped["image"]

    no_image = router_module._map_video({**item, "ImageTags": {}, "Id": None})
    assert no_image["has_image"] is False and no_image["thumb"] == "" and no_image["image"] == ""
    assert no_image["id"] == "" and no_image["path"] == "/media/A.mp4"


def test_extract_number():
    from mdcx.webapp.routers import emby

    assert emby._extract_number("/media/av/IPX-917-xxx.mp4").startswith("IPX-917")
    assert emby._extract_number("/media/av/FC2PPV-3902060-C/FC2PPV-3902060-C.mp4") == "FC2-PPV-3902060-C"
    assert emby._extract_number("") == ""
    # 中文名也走国产识别规则（与刮削一致），能提取就不抛异常
    assert emby._extract_number("/media/电视剧/艾米丽在巴黎 (2020)") == "艾米丽在巴黎"


def test_number_sort_key():
    from mdcx.webapp.routers.emby import _number_sort_key, _sort_videos

    assert _number_sort_key("IPX-9") < _number_sort_key("IPX-100")
    rows = [
        {"number": "", "name": "B片"},
        {"number": "IPX-100", "name": "x"},
        {"number": "IPX-9", "name": "y"},
        {"number": "", "name": "A片"},
    ]
    _sort_videos(rows)
    assert [r["number"] or r["name"] for r in rows] == ["IPX-9", "IPX-100", "A片", "B片"]


def test_filter_duplicates():
    """番号在整库出现多次才保留；大小写不敏感；无番号不参与。"""
    from mdcx.webapp.routers.emby import _filter_duplicates

    rows = [
        {"number": "ABP-001", "name": "a"},
        {"number": "abp-001", "name": "b"},
        {"number": "IPX-9", "name": "c"},
        {"number": "", "name": "d"},
        {"number": "", "name": "e"},
    ]
    dup = _filter_duplicates(rows)
    assert [r["name"] for r in dup] == ["a", "b"]  # 保持缓存顺序，同番号相邻


@pytest.mark.asyncio
async def test_videos_duplicates_only(monkeypatch):
    from mdcx.webapp.routers import emby as router_module

    rows = [
        {"id": "1", "number": "ABP-001", "name": "a", "has_image": False},
        {"id": "2", "number": "ABP-001", "name": "b", "has_image": False},
        {"id": "3", "number": "IPX-9", "name": "c", "has_image": False},
    ]
    monkeypatch.setattr(router_module, "_default_library_id", lambda: "lib-1")
    monkeypatch.setattr(router_module.video_cache, "get_videos", lambda lib: (123.0, "", rows))

    r = await router_module.videos(
        parent_id="lib-1", start_index=0, limit=200, keyword="", library_type="", duplicates_only=True
    )
    assert r["total"] == 2
    assert [v["id"] for v in r["videos"]] == ["1", "2"]

    r2 = await router_module.videos(
        parent_id="lib-1", start_index=0, limit=200, keyword="", library_type="", duplicates_only=False
    )
    assert r2["total"] == 3


@pytest.mark.asyncio
async def test_get_all_video_items_pages(monkeypatch):
    """满页 1000 继续拉，不足即止。"""
    import mdcx.tools.emby_video_manager as emv

    batches = [[{"Id": str(i)} for i in range(1000)], [{"Id": "1000"}, {"Id": "1001"}]]
    calls: list[int] = []

    async def fake_get(parent_id, start_index=0, limit=200, keyword="", include_types=None):
        calls.append(start_index)
        return batches[len(calls) - 1], 1002

    monkeypatch.setattr(emv, "get_video_items", fake_get)
    items = await emv.get_all_video_items("lib-1")
    assert len(items) == 1002
    assert calls == [0, 1000]


# ===== 删除（Emby DELETE + 缓存移除 + router 守卫）=====


@pytest.mark.asyncio
async def test_delete_video_item_emby(server_config):
    from mdcx.tools.emby_video_manager import delete_video_item

    fake_client = MagicMock()
    fake_client.request = AsyncMock(return_value=(MagicMock(status_code=204), ""))

    with patch("mdcx.tools.emby_video_manager.manager.acquire_computed", return_value=_make_lease(fake_client)):
        ok, msg = await delete_video_item("v1")

    assert ok is True and "删除" in msg
    method, url = fake_client.request.await_args.args
    assert method == "DELETE"
    assert url == "http://test:8096/emby/Items/v1"


@pytest.mark.asyncio
async def test_delete_video_item_jellyfin(monkeypatch):
    from mdcx.config.manager import manager
    from mdcx.tools.emby_video_manager import delete_video_item

    monkeypatch.setattr(manager.config, "api_key", "test-token")
    monkeypatch.setattr(manager.config, "emby_url", "http://jf:8096")
    monkeypatch.setattr(manager.config, "server_type", "ln")

    fake_client = MagicMock()
    fake_client.request = AsyncMock(return_value=(MagicMock(status_code=200), ""))

    with patch("mdcx.tools.emby_video_manager.manager.acquire_computed", return_value=_make_lease(fake_client)):
        ok, _msg = await delete_video_item("v2")

    assert ok is True
    assert fake_client.request.await_args.args[1] == "http://jf:8096/Items/v2"


@pytest.mark.asyncio
async def test_delete_video_item_http_error(server_config):
    from mdcx.tools.emby_video_manager import delete_video_item

    fake_client = MagicMock()
    fake_client.request = AsyncMock(return_value=(MagicMock(status_code=500), ""))

    with patch("mdcx.tools.emby_video_manager.manager.acquire_computed", return_value=_make_lease(fake_client)):
        ok, msg = await delete_video_item("v1")

    assert ok is False and "500" in msg


@pytest.mark.asyncio
async def test_delete_video_item_network_error(server_config):
    from mdcx.tools.emby_video_manager import delete_video_item

    fake_client = MagicMock()
    fake_client.request = AsyncMock(return_value=(None, "connect timeout"))

    with patch("mdcx.tools.emby_video_manager.manager.acquire_computed", return_value=_make_lease(fake_client)):
        ok, msg = await delete_video_item("v1")

    assert ok is False and "connect timeout" in msg


# ===== 图片代理（浏览器不直连 emby_url）=====


def test_video_image_proxy_url():
    from mdcx.webapp.routers.emby import _video_image_proxy_url

    assert _video_image_proxy_url("v1") == "/api/emby/video-image?item_id=v1&max_width=200"
    assert _video_image_proxy_url("v1", "tag1", 1200) == "/api/emby/video-image?item_id=v1&max_width=1200&tag=tag1"
    assert "item_id=a%2Fb" in _video_image_proxy_url("a/b")


def test_fix_cached_image_urls():
    """旧缓存的绝对图片地址就地改写为代理地址（保留 tag）；已是相对路径的不动。"""
    from mdcx.webapp.routers.emby import _fix_cached_image_urls

    abs_url = "http://127.0.0.1:18096/emby/Items/v1/Images/Primary?maxWidth=200&api_key=x&tag=t1"
    rows = [
        {"id": "v1", "has_image": True, "thumb": abs_url, "image": abs_url.replace("200", "1200")},
        {
            "id": "v2",
            "has_image": True,
            "thumb": "/api/emby/video-image?item_id=v2&max_width=200&tag=t2",
            "image": "/api/emby/video-image?item_id=v2&max_width=1200&tag=t2",
        },
        {"id": "v3", "has_image": False, "thumb": "", "image": ""},
        {"id": "", "has_image": True, "thumb": "http://x/y", "image": "http://x/y"},
    ]
    _fix_cached_image_urls(rows)
    assert rows[0]["thumb"] == "/api/emby/video-image?item_id=v1&max_width=200&tag=t1"
    assert rows[0]["image"] == "/api/emby/video-image?item_id=v1&max_width=1200&tag=t1"
    assert rows[1]["thumb"] == "/api/emby/video-image?item_id=v2&max_width=200&tag=t2"
    assert rows[2]["thumb"] == "" and rows[3]["thumb"] == "http://x/y"


@pytest.mark.asyncio
async def test_fetch_video_image_success(server_config):
    from mdcx.tools.emby_video_manager import fetch_video_image

    fake_client = MagicMock()
    resp = MagicMock(status_code=200, headers={"Content-Type": "image/jpeg"}, content=b"img-bytes")
    fake_client.request = AsyncMock(return_value=(resp, ""))

    with patch("mdcx.tools.emby_video_manager.manager.acquire_computed", return_value=_make_lease(fake_client)):
        data, ctype, err = await fetch_video_image("v1", 200, "tag1")

    assert data == b"img-bytes" and ctype == "image/jpeg" and err == ""
    method, url = fake_client.request.await_args.args
    assert method == "GET"
    assert "/emby/Items/v1/Images/Primary" in url
    assert "maxWidth=200" in url and "tag=tag1" in url


@pytest.mark.asyncio
async def test_fetch_video_image_http_error(server_config):
    from mdcx.tools.emby_video_manager import fetch_video_image

    fake_client = MagicMock()
    resp = MagicMock(status_code=404, headers={}, content=b"")
    fake_client.request = AsyncMock(return_value=(resp, ""))

    with patch("mdcx.tools.emby_video_manager.manager.acquire_computed", return_value=_make_lease(fake_client)):
        data, _ctype, err = await fetch_video_image("v1")

    assert data is None and "404" in err


@pytest.mark.asyncio
async def test_fetch_video_image_network_error(server_config):
    from mdcx.tools.emby_video_manager import fetch_video_image

    fake_client = MagicMock()
    fake_client.request = AsyncMock(return_value=(None, "connect timeout"))

    with patch("mdcx.tools.emby_video_manager.manager.acquire_computed", return_value=_make_lease(fake_client)):
        data, _ctype, err = await fetch_video_image("v1")

    assert data is None and "connect timeout" in err


@pytest.mark.asyncio
async def test_video_image_proxy_endpoint(monkeypatch):
    from mdcx.webapp.routers import emby as router_module

    async def fake_fetch(item_id, max_width=200, tag=""):
        assert item_id == "v1" and max_width == 200 and tag == "t1"
        return b"img-bytes", "image/jpeg", ""

    monkeypatch.setattr(router_module.emv, "fetch_video_image", fake_fetch)
    resp = await router_module.video_image(item_id="v1", max_width=200, tag="t1")
    assert resp.body == b"img-bytes"
    assert resp.media_type == "image/jpeg"
    assert resp.headers["cache-control"] == "public, max-age=86400"


def test_video_cache_remove_video(monkeypatch, tmp_path):
    from mdcx.webapp import video_cache

    monkeypatch.setattr(video_cache, "_cache_path", lambda lib: tmp_path / f"{lib}.json")
    video_cache.set_videos("lib-1", [{"id": "v1", "name": "A"}, {"id": "v2", "name": "B"}])
    assert video_cache.remove_video("lib-1", "v1") is True
    _ts, _types, rows = video_cache.get_videos("lib-1")
    assert [r["id"] for r in rows] == ["v2"]
    # 未命中或无缓存时不改动文件
    assert video_cache.remove_video("lib-1", "nope") is False
    assert video_cache.remove_video("lib-none", "v1") is False


@pytest.mark.asyncio
async def test_videos_delete_rejects_non_default_library(monkeypatch):
    """未配置视频库 / 非配置库一律 400。"""
    from fastapi import HTTPException

    from mdcx.config.manager import manager
    from mdcx.webapp.routers import emby as router_module

    monkeypatch.setattr(manager.config, "video_library_id", "lib-1")
    with pytest.raises(HTTPException) as exc:
        await router_module.videos_delete(router_module.VideoDelete(parent_id="other", item_id="v1"))
    assert exc.value.status_code == 400

    monkeypatch.setattr(manager.config, "video_library_id", "")
    with pytest.raises(HTTPException) as exc:
        await router_module.videos_delete(router_module.VideoDelete(parent_id="lib-1", item_id="v1"))
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_videos_delete_updates_cache(monkeypatch):
    from mdcx.config.manager import manager
    from mdcx.webapp.routers import emby as router_module

    monkeypatch.setattr(manager.config, "video_library_id", "lib-1")
    deleted: list[str] = []
    removed: list[tuple[str, str]] = []

    async def fake_delete(item_id: str):
        deleted.append(item_id)
        return True, "已从 Emby 删除"

    def fake_remove(lib: str, item_id: str) -> bool:
        removed.append((lib, item_id))
        return True

    monkeypatch.setattr(router_module.emv, "delete_video_item", fake_delete)
    monkeypatch.setattr(router_module.video_cache, "remove_video", fake_remove)

    r = await router_module.videos_delete(router_module.VideoDelete(parent_id="lib-1", item_id="v1"))
    assert r == {"ok": True, "message": "已从 Emby 删除"}
    assert deleted == ["v1"]
    assert removed == [("lib-1", "v1")]


@pytest.mark.asyncio
async def test_videos_delete_emby_failure(monkeypatch):
    """Emby 侧删除失败时映射为 502，且不动缓存。"""
    from fastapi import HTTPException

    from mdcx.config.manager import manager
    from mdcx.webapp.routers import emby as router_module

    monkeypatch.setattr(manager.config, "video_library_id", "lib-1")

    async def fake_delete(item_id: str):
        return False, "删除失败: HTTP 500"

    removed: list[tuple[str, str]] = []

    def fake_remove(lib: str, item_id: str) -> bool:
        removed.append((lib, item_id))
        return True

    monkeypatch.setattr(router_module.emv, "delete_video_item", fake_delete)
    monkeypatch.setattr(router_module.video_cache, "remove_video", fake_remove)

    with pytest.raises(HTTPException) as exc:
        await router_module.videos_delete(router_module.VideoDelete(parent_id="lib-1", item_id="v1"))
    assert exc.value.status_code == 502
    assert removed == []
