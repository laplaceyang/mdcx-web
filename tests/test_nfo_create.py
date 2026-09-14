"""创建 NFO API 测试（POST /api/nfo/create）+ translate-test 按字段翻译。

与 test_webapp_api 相同：子进程运行，MARK_FILE 指向临时目录实现配置隔离。
"""

import subprocess
import sys

PROBE = r"""
import tempfile
from pathlib import Path

# 隔离配置：MARK_FILE 指向临时目录（必须在导入 mdcx.config.manager 之前设置）
tmp = Path(tempfile.mkdtemp(prefix="mdcx-nfo-create-test-"))
(tmp / "MDCx.config").write_text(str(tmp / "config.json"), encoding="utf-8")
import mdcx.consts as consts  # noqa: E402

consts.MARK_FILE = tmp / "MDCx.config"

import xml.etree.ElementTree as ET  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from mdcx.config.manager import manager  # noqa: E402
from mdcx.webapp.app import app  # noqa: E402

with TestClient(app) as client:  # with 触发 lifespan（hub.attach）
    # 默认保存目录（成功输出目录未配置 → 回退配置数据目录；macOS 上 /var 为符号链接需 resolve）
    default_dir = str(Path(manager.data_folder).resolve())

    # 完整字段：元素顺序与正常刮削流程（core/nfo.py）一致
    fields = {
        "number": "OFJE-536",
        "title": "OFJE-536 测试<标题>",
        "originaltitle": "OFJE-536 テスト",
        "originalplot": "あああ\nいいい",
        "plot": "中文简介\n第二行",
        "release": "2025-09-09",
        "countrycode": "JP",
        "actors": ["濑户环奈", "金松季步"],
        "series": "S1 GIRLS COLLECTION",
        "studio": "S1",
        "publisher": "S1",
        "genres": ["美少女", "精选合集"],
    }
    r = client.post("/api/nfo/create", json={"fields": fields})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["path"].endswith("OFJE-536.nfo"), d["path"]
    assert d["path"].startswith(default_dir), d["path"]

    root = ET.fromstring((Path(default_dir) / "OFJE-536.nfo").read_text(encoding="utf-8"))
    assert root.tag == "movie"
    tags = [el.tag for el in root]
    assert tags == [
        "plot", "originalplot", "tagline", "premiered", "releasedate", "release",
        "num", "title", "originaltitle", "countrycode",
        "actor", "actor", "series", "studio", "maker", "publisher", "label",
        "genre", "genre",
    ], tags
    assert root.findtext("tagline") == "发行日期 2025-09-09"  # 默认标语模板
    assert root.findtext("title") == "OFJE-536 测试<标题>"  # XML 转义后原样解析回来
    actor_names = [el.findtext("name") for el in root.findall("actor")]
    assert actor_names == ["濑户环奈", "金松季步"]
    assert all(el.findtext("type") == "Actor" for el in root.findall("actor"))
    assert root.findtext("studio") == root.findtext("maker") == "S1"
    assert root.findtext("publisher") == root.findtext("label") == "S1"
    assert [el.text for el in root.findall("genre")] == ["美少女", "精选合集"]

    # 显式 tagline 优先于默认模板
    r = client.post("/api/nfo/create", json={"fields": {"number": "TAG-001", "release": "2025-01-01", "tagline": "自定义标语"}})
    assert r.status_code == 200, r.text
    root = ET.fromstring(Path(r.json()["path"]).read_text(encoding="utf-8"))
    assert root.findtext("tagline") == "自定义标语"

    # 演员/标签传字符串（逗号/换行分隔）、文件名非法字符清洗、自动补 .nfo
    r = client.post(
        "/api/nfo/create",
        json={"filename": 'a/b:c?', "fields": {"actors": "演员A，演员B\n演员C", "genres": "标签1, 标签2"}},
    )
    assert r.status_code == 200, r.text
    assert Path(r.json()["path"]).name == "a_b_c_.nfo", r.json()["path"]
    root = ET.fromstring(Path(r.json()["path"]).read_text(encoding="utf-8"))
    assert [el.findtext("name") for el in root.findall("actor")] == ["演员A", "演员B", "演员C"]
    assert [el.text for el in root.findall("genre")] == ["标签1", "标签2"]

    # 全空字段：只生成空 movie 骨架（所有字段可选）
    r = client.post("/api/nfo/create", json={"filename": "empty", "fields": {}})
    assert r.status_code == 200, r.text
    root = ET.fromstring(Path(r.json()["path"]).read_text(encoding="utf-8"))
    assert len(list(root)) == 0

    # 文件名和番号都缺 → 422
    r = client.post("/api/nfo/create", json={"fields": {}})
    assert r.status_code == 422, r.text

    # 重复创建 → 409；overwrite=true → 覆盖
    r = client.post("/api/nfo/create", json={"filename": "empty", "fields": {}})
    assert r.status_code == 409, r.text
    r = client.post("/api/nfo/create", json={"filename": "empty", "overwrite": True, "fields": {}})
    assert r.status_code == 200, r.text

    # 目录越界 → 403
    r = client.post("/api/nfo/create", json={"dir": "/tmp", "filename": "x", "fields": {}})
    assert r.status_code == 403, r.text

    # 创建 NFO 补图：上传横图 → 与 NFO 同名基础名的 thumb + 竖版 poster
    import io  # noqa: E402

    from PIL import Image  # noqa: E402

    # 离线环境跳过人脸识别裁剪（YuNet 模型缺失时会联网下载、逐旋转重试 30s 超时），
    # 桩掉后 cut_thumb_to_poster 走居中裁剪回退
    import mdcx.core.image as _core_image  # noqa: E402

    _core_image.get_face_crop_left = lambda *args, **kwargs: None

    buf = io.BytesIO()
    Image.new("RGB", (800, 600), (200, 100, 100)).save(buf, format="JPEG")
    img = buf.getvalue()
    r = client.post("/api/nfo/create-cover?name=OFJE-536", content=img)
    assert r.status_code == 200, r.text
    d = r.json()
    assert Path(d["thumb"]).name == "OFJE-536-thumb.jpg", d
    assert Path(d["poster"]).name == "OFJE-536-poster.jpg", d
    assert str(Path(d["thumb"]).parent) == default_dir, d
    assert Path(d["thumb"]).is_file() and Path(d["poster"]).is_file()
    w, h = Image.open(d["poster"]).size
    assert h > w, (w, h)  # 横图裁出竖版 poster

    # 名字清洗与 /create 一致（非法字符 → _）
    r = client.post("/api/nfo/create-cover?name=a%2Fb%3Ac%3F", content=img)
    assert r.status_code == 200, r.text
    assert Path(r.json()["thumb"]).name == "a_b_c_-thumb.jpg", r.json()

    # 空数据 / 不支持的格式 / 缺 name → 422；目录越界 → 403
    r = client.post("/api/nfo/create-cover?name=x1", content=b"")
    assert r.status_code == 422, r.text
    r = client.post("/api/nfo/create-cover?name=x1&filename=a.gif", content=img)
    assert r.status_code == 422, r.text
    r = client.post("/api/nfo/create-cover", content=img)
    assert r.status_code == 422, r.text
    r = client.post("/api/nfo/create-cover?name=x2&dir=/tmp", content=img)
    assert r.status_code == 403, r.text

    # 重复上传（默认覆盖）→ 200
    r = client.post("/api/nfo/create-cover?name=OFJE-536", content=img)
    assert r.status_code == 200, r.text

    # 手动刮削：subfolder → NFO 落盘到 {默认目录}/{番号}/；subfolder 也走同一清洗规则
    r = client.post("/api/nfo/create", json={"subfolder": "SUB-001", "fields": {"number": "SUB-001"}})
    assert r.status_code == 200, r.text
    assert Path(r.json()["path"]).parent == Path(default_dir) / "SUB-001", r.json()["path"]
    r = client.post("/api/nfo/create", json={"subfolder": "A/B", "fields": {"number": "X"}})
    assert r.status_code == 200, r.text
    assert Path(r.json()["path"]).parent == Path(default_dir) / "A_B", r.json()["path"]

    # move-video：视频移入番号目录并改名为番号（保留扩展名），原文件移走
    src_video = Path(default_dir) / "old_name.mp4"
    src_video.write_bytes(b"fakevideo")
    r = client.post("/api/nfo/move-video", params={"src": str(src_video), "subfolder": "SUB-001", "name": "SUB-001"})
    assert r.status_code == 200, r.text
    moved = Path(r.json()["path"])
    assert moved == Path(default_dir) / "SUB-001" / "SUB-001.mp4", moved
    assert moved.is_file() and not src_video.exists()

    # 目标已存在 → 409；overwrite=True 覆盖；源文件不存在 → 404
    src_video.write_bytes(b"fakevideo2")
    r = client.post("/api/nfo/move-video", params={"src": str(src_video), "subfolder": "SUB-001", "name": "SUB-001"})
    assert r.status_code == 409, r.text
    r = client.post(
        "/api/nfo/move-video",
        params={"src": str(src_video), "subfolder": "SUB-001", "name": "SUB-001", "overwrite": True},
    )
    assert r.status_code == 200, r.text
    r = client.post("/api/nfo/move-video", params={"src": str(src_video), "subfolder": "SUB-001", "name": "SUB-001"})
    assert r.status_code == 404, r.text

    # extract-number：从文件名提取番号（手动刮削默认值）
    r = client.get("/api/nfo/extract-number", params={"path": "/media/movies/OFJE-536.mp4"})
    assert r.status_code == 200, r.text
    assert r.json()["number"] == "OFJE-536", r.json()

    # translate-test 按字段翻译：未配置翻译引擎时原样返回，不报错
    r = client.post("/api/tools/translate-test", json={"mode": "text", "text": "テスト", "field": "outline"})
    assert r.status_code == 200, r.text
    assert r.json()["content"] == "テスト"
    r = client.post("/api/tools/translate-test", json={"mode": "text", "text": "テスト", "field": "title"})
    assert r.status_code == 200 and r.json()["content"] == "テスト", r.text
    r = client.post("/api/tools/translate-test", json={"mode": "text", "text": "テスト"})
    assert r.status_code == 200 and r.json()["content"] == "テスト", r.text  # 默认 field=title
    r = client.post("/api/tools/translate-test", json={"mode": "text", "text": "x", "field": "bad"})
    assert r.status_code == 422, r.text

print("NFO CREATE TESTS OK")
"""


def test_nfo_create():
    result = subprocess.run([sys.executable, "-c", PROBE], capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "NFO CREATE TESTS OK" in result.stdout
