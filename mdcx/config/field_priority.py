"""字段级站点优先级的纯逻辑定义。

原属桌面 controllers/site_priority_dialog.py，web 设置页与配置迁移共用，
因此落在 config 包（无 Qt 依赖）。
"""

from mdcx.config.enums import Website
from mdcx.config.models import CrawlerResultFields, str_to_list

# 字段优先级矩阵可配置的字段清单（桌面版 16+3 字段）
FIELD_PRIORITY_FIELDS = (
    CrawlerResultFields.TITLE,
    CrawlerResultFields.ORIGINALTITLE,
    CrawlerResultFields.OUTLINE,
    CrawlerResultFields.ORIGINALPLOT,
    CrawlerResultFields.ACTORS,
    CrawlerResultFields.ALL_ACTORS,
    CrawlerResultFields.THUMB,
    CrawlerResultFields.POSTER,
    CrawlerResultFields.EXTRAFANART,
    CrawlerResultFields.TRAILER,
    CrawlerResultFields.TAGS,
    CrawlerResultFields.RELEASE,
    CrawlerResultFields.RUNTIME,
    CrawlerResultFields.SCORE,
    CrawlerResultFields.DIRECTORS,
    CrawlerResultFields.SERIES,
    CrawlerResultFields.STUDIO,
    CrawlerResultFields.PUBLISHER,
    CrawlerResultFields.WANTED,
)


def _sync_field_sites_after_type_sites_changed(
    current_sites: list[Website],
    previous_type_sites: list[Website],
    new_type_sites: list[Website],
) -> list[Website]:
    if not current_sites:
        return []
    new_type_set = set(new_type_sites)
    kept_sites = [site for site in current_sites if site in new_type_set]
    previous_type_set = set(previous_type_sites)
    added_sites = [site for site in new_type_sites if site not in previous_type_set and site not in kept_sites]
    return kept_sites + added_sites


def _parse_sites(text: str) -> list[Website]:
    return list(dict.fromkeys(Website(site) for site in str_to_list(text, ",") if site in Website))
