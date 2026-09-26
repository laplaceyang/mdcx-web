"""Emby/Jellyfin 视频管理：媒体库与视频条目查询（视频整理功能的服务端数据层）。

连接参数复用「服务器」配置（server_type/emby_url/api_key/user_id），
请求方式与 emby_actor_manager 一致（manager.acquire_computed + get_json）。
"""

from __future__ import annotations

from mdcx.config.manager import manager
from mdcx.tools.emby_shared import _append_query, _build_jellyfin_headers

# 视频条目类型过滤：排除 Folder/Series/Season 等容器，库里的实际视频无论入库为哪种类型都能列出
VIDEO_INCLUDE_TYPES = "Movie,Episode,Video,MusicVideo"

VIDEO_FIELDS = "Path,ProviderIds,ProductionYear,Size,DateCreated"


def _require_api_key() -> None:
    if not manager.config.api_key:
        raise RuntimeError("Emby API 密钥未填写，请在「软件设置 → 服务器」页填写")


async def get_media_libraries() -> list[dict]:
    """媒体库（顶层）列表，失败抛 RuntimeError（区别于空库）。"""
    _require_api_key()
    base_url = str(manager.config.emby_url).rstrip("/")
    headers = _build_jellyfin_headers()
    if "emby" == manager.config.server_type:
        url = f"{base_url}/emby/Library/MediaFolders"
    else:
        url = f"{base_url}/Library/MediaFolders"
    async with manager.acquire_computed() as computed:
        response, error = await computed.async_client.get_json(url, headers=headers, use_proxy=False)
    if response is None:
        raise RuntimeError(f"获取媒体库列表失败: {error}")
    return response.get("Items", [])


async def get_video_items(
    parent_id: str,
    start_index: int = 0,
    limit: int = 200,
    keyword: str = "",
    include_types: str | None = None,
) -> tuple[list[dict], int]:
    """分页拉取媒体库下的视频条目，返回 (items, total)。

    include_types 为空时用默认视频类型集合；电视剧库传 "Series" 按剧归组。
    total 取服务器 TotalRecordCount；个别服务器不带该字段时用已取条数近似。
    """
    _require_api_key()
    base_url = str(manager.config.emby_url).rstrip("/")
    headers = _build_jellyfin_headers()
    params: dict[str, str | None] = {
        "ParentId": parent_id,
        "Recursive": "true",
        "IncludeItemTypes": include_types or VIDEO_INCLUDE_TYPES,
        "fields": VIDEO_FIELDS,
        "enableImages": "true",
        "SortBy": "SortName",
        "SortOrder": "Ascending",
        "StartIndex": str(max(0, start_index)),
        "Limit": str(max(1, limit)),
    }
    if keyword.strip():
        params["SearchTerm"] = keyword.strip()
    if "emby" == manager.config.server_type:
        url = _append_query(f"{base_url}/emby/Items", params)
    else:
        params["userId"] = manager.config.user_id
        url = _append_query(f"{base_url}/Items", params)
    async with manager.acquire_computed() as computed:
        response, error = await computed.async_client.get_json(url, headers=headers, use_proxy=False)
    if response is None:
        raise RuntimeError(f"获取视频列表失败: {error}")
    items = response.get("Items", [])
    total = int(response.get("TotalRecordCount") or 0)
    if not total and items:
        total = start_index + len(items) + (1 if len(items) >= limit else 0)
    return items, total


async def get_all_video_items(parent_id: str, include_types: str | None = None) -> list[dict]:
    """全量拉取媒体库下的视频条目（1000/批循环直到取完），供列表缓存刷新用。"""
    all_items: list[dict] = []
    start = 0
    while True:
        items, _total = await get_video_items(parent_id, start_index=start, limit=1000, include_types=include_types)
        all_items.extend(items)
        if len(items) < 1000:
            return all_items
        start += 1000


async def delete_video_item(item_id: str) -> tuple[bool, str]:
    """从 Emby 删除条目（DELETE /Items/{id}），返回 (是否成功, 提示信息)。

    源媒体文件是否一并删除取决于 Emby/Jellyfin 服务器自身的删除设置。
    """
    _require_api_key()
    base_url = str(manager.config.emby_url).rstrip("/")
    headers = _build_jellyfin_headers()
    if "emby" == manager.config.server_type:
        url = f"{base_url}/emby/Items/{item_id}"
    else:
        url = f"{base_url}/Items/{item_id}"
    async with manager.acquire_computed() as computed:
        response, error = await computed.async_client.request("DELETE", url, headers=headers, use_proxy=False)
    if response is None:
        return False, f"删除请求失败: {error}"
    if response.status_code >= 400:
        return False, f"删除失败: HTTP {response.status_code}"
    return True, "已从 Emby 删除"


async def fetch_video_image(item_id: str, max_width: int = 200, tag: str = "") -> tuple[bytes | None, str, str]:
    """服务端拉取条目图片，返回 (图片字节, content-type, 错误信息)。

    供 webapp 图片代理端点用：浏览器不直连 emby_url（可能是 127.0.0.1/容器内
    地址），由后端转发。
    """
    _require_api_key()
    url = video_image_url(item_id, tag, max_width)
    headers = _build_jellyfin_headers()
    async with manager.acquire_computed() as computed:
        response, error = await computed.async_client.request("GET", url, headers=headers, use_proxy=False)
    if response is None:
        return None, "", error
    if response.status_code >= 400:
        return None, "", f"HTTP {response.status_code}"
    headers_map = {str(k).lower(): str(v) for k, v in (response.headers.items() if response.headers else [])}
    return response.content, headers_map.get("content-type", ""), ""


def video_image_url(item_id: str, tag: str = "", max_width: int = 200) -> str:
    """条目主图缩略 URL（带 api_key，可直接作 <img> src）；预览大图传更大的 max_width。"""
    base_url = str(manager.config.emby_url).rstrip("/")
    if "emby" == manager.config.server_type:
        url = f"{base_url}/emby/Items/{item_id}/Images/Primary"
    else:
        url = f"{base_url}/Items/{item_id}/Images/Primary"
    params: dict[str, str | None] = {"maxWidth": str(max_width), "api_key": manager.config.api_key}
    if tag:
        params["tag"] = tag
    return _append_query(url, params)
