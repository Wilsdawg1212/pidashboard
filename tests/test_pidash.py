"""Run with:  python -m pytest -q tests   (uses fake services, no systemd needed)"""

import os

os.environ["PIDASH_FAKE"] = "1"

from pidash.app import app  # noqa: E402
from pidash.system import _parse_systemd_time, parse_show  # noqa: E402


def test_parse_show():
    s = parse_show("ActiveState=active\nSubState=running\nControlGroup=/system.slice/x.service\nMainPID=42\n")
    assert s["ActiveState"] == "active" and s["ControlGroup"] == "/system.slice/x.service"


def test_parse_time():
    assert _parse_systemd_time("Mon 2026-11-09 02:40:00 EST") is not None
    assert _parse_systemd_time("n/a") is None
    assert _parse_systemd_time("") is None


def test_status_and_toggle():
    c = app.test_client()
    st = c.get("/api/status").get_json()
    apps = {a["id"]: a for a in st["apps"]}
    assert apps["minecraft"]["state"] == "running"
    assert apps["dealpi"]["mem_bytes"] > 0 and apps["dealpi"]["next_run"]

    assert c.post("/api/apps/dealpi/stop").get_json()["app"]["state"] == "stopped"
    assert c.post("/api/apps/dealpi/start").get_json()["app"]["state"] == "running"
    assert c.post("/api/apps/minecraft/disable").get_json()["app"]["on_boot"] is False


def test_rejects_unknown():
    c = app.test_client()
    assert c.post("/api/apps/nope/start").status_code == 404
    assert c.post("/api/apps/dealpi/rm-rf").status_code == 400
