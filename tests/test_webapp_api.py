"""webapp API/WS 测试。

conftest 会把 mdcx.signals / mdcx.config.manager 整体替换为测试桩（供桌面层测试用），
而 webapp 需要真实实现，因此本测试在子进程中运行：子进程里把 MARK_FILE 指向临时目录
实现配置隔离，然后用 starlette TestClient 覆盖 REST + WebSocket 行为。
"""

import subprocess
import sys

PROBE = r"""
import json
import tempfile
from pathlib import Path

# 隔离配置：MARK_FILE 指向临时目录（必须在导入 mdcx.config.manager 之前设置）
tmp = Path(tempfile.mkdtemp(prefix="mdcx-web-test-"))
(tmp / "MDCx.config").write_text(str(tmp / "config.json"), encoding="utf-8")
import mdcx.consts as consts  # noqa: E402

consts.MARK_FILE = tmp / "MDCx.config"

from fastapi.testclient import TestClient  # noqa: E402
from mdcx.signals import signal  # noqa: E402
from mdcx.webapp.app import app  # noqa: E402

with TestClient(app) as client:  # with 触发 lifespan（hub.attach）
    # 系统信息
    r = client.get("/api/system/version")
    assert r.status_code == 200, r.text
    assert r.json()["version_name"].startswith("v")
    assert r.json()["local_version"] > 0

    # 配置读写
    r = client.get("/api/config")
    assert r.status_code == 200, r.text
    cfg = r.json()["config"]
    assert "main_mode" in cfg and "thread_number" in cfg

    cfg["main_mode"] = 3
    r = client.put("/api/config", json={"config": cfg})
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True

    r = client.get("/api/config")
    assert r.json()["config"]["main_mode"] == 3

    saved = json.loads((tmp / "config.json").read_text(encoding="utf-8"))
    assert saved["main_mode"] == 3, "配置应原子落盘到临时目录"

    # 校验失败 → 422
    bad = dict(cfg)
    bad["thread_number"] = {"not": "an int"}
    r = client.put("/api/config", json={"config": bad})
    assert r.status_code == 422, r.text

    # 配置文件列表 & 重置
    r = client.get("/api/config/files")
    assert r.status_code == 200 and "config.json" in r.json()["files"]
    r = client.post("/api/config/reset")
    assert r.status_code == 200, r.text

    # 刮削任务状态（未启动）
    r = client.get("/api/scrape/status")
    assert r.json()["state"] == "idle"
    r = client.get("/api/scrape/resume-info")
    assert r.json() == {"available": False}
    r = client.get("/api/scrape/results")
    assert r.json() == {"items": []}

    # 网络检测状态
    r = client.get("/api/network/results")
    assert r.json()["running"] is False

    # 媒体路径越界 → 403
    r = client.get("/api/media/file", params={"path": "/etc/passwd"})
    assert r.status_code == 403, r.text

    # WebSocket：hello + 总线事件实时推送
    with client.websocket_connect("/ws") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello", hello
        signal.show_log_text("ws-test-log-123")
        event = ws.receive_json()
        assert event["type"] == "event" and event["event"] == "log_text", event
        assert "ws-test-log-123" in event["args"][0]

print("WEBAPP API TESTS OK")
"""


def test_webapp_api():
    result = subprocess.run([sys.executable, "-c", PROBE], capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "WEBAPP API TESTS OK" in result.stdout
