"""手动刮削按设置里的命名规则渲染文件夹/文件名的回归测试。

对齐正常刮削流程：模板、后缀开关、长度上限读生效配置；
演员为空时命名上下文回退 actor_no_name（默认「未知演员」）。
"""

import importlib
import sys

import pytest

# conftest 给 mdcx.signals 装的桩没有 WebSignalBus（webapp.runtime 依赖它），
# 弹掉桩导入真身（与 test_webapp_job_reset 同法）
sys.modules.pop("mdcx.signals", None)
importlib.import_module("mdcx.signals")

from mdcx.webapp.routers.nfo import _create_base_name, _render_manual_scrape_names  # noqa: E402


@pytest.fixture()
def naming_cfg(monkeypatch):
    """固定模板与开关，隔离本机配置差异。"""
    from mdcx.config.manager import manager

    monkeypatch.setattr(manager.config, "folder_name", "{{ number }}-{{ actor }}", raising=False)
    monkeypatch.setattr(manager.config, "naming_file", "{{ number }}-{{ actor }}", raising=False)
    monkeypatch.setattr(manager.config, "folder_name_max", 60, raising=False)
    monkeypatch.setattr(manager.config, "file_name_max", 100, raising=False)
    return manager.config


def test_render_with_actor(naming_cfg):
    folder, file_base = _render_manual_scrape_names(
        {"number": "SIRO-1063", "actors": ["泷泽劳拉", "另一人"], "title": "标题"}
    )
    assert folder == "SIRO-1063-泷泽劳拉,另一人"
    assert file_base == "SIRO-1063-泷泽劳拉,另一人"


def test_render_without_actor_falls_back_to_unknown(naming_cfg):
    folder, file_base = _render_manual_scrape_names({"number": "SIRO-1063", "actors": []})
    assert folder == "SIRO-1063-未知演员"
    assert file_base == "SIRO-1063-未知演员"


def test_render_uses_first_actor_field(naming_cfg):
    # first_actor 模板变量取第一个演员
    monkeypatched = naming_cfg
    monkeypatched.naming_file = "{{ number }}-{{ first_actor }}"
    _, file_base = _render_manual_scrape_names({"number": "SIRO-1063", "actors": ["A", "B"]})
    assert file_base == "SIRO-1063-A"


def test_base_name_cleaned():
    assert _create_base_name("SIRO-1063-未知演员.nfo", "") == "SIRO-1063-未知演员"
