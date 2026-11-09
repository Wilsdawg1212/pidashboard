"""The dashboard web page and its small JSON API."""

from __future__ import annotations

import os
import secrets
import time

from flask import Flask, Response, abort, jsonify, render_template, request

from . import load_config
from . import system as real_system
from .system import FakeSystem

app = Flask(__name__)
CFG = load_config(os.environ.get("PIDASH_CONFIG"))
SYS = FakeSystem() if os.environ.get("PIDASH_FAKE") == "1" else real_system
PASSWORD = os.environ.get("PIDASH_PASSWORD", "")
ACTIONS = {"start", "stop", "restart", "enable", "disable"}


@app.before_request
def _auth():
    """Optional password: set PIDASH_PASSWORD in .env to require it."""
    if not PASSWORD:
        return None
    a = request.authorization
    if a and secrets.compare_digest(a.password or "", PASSWORD):
        return None
    return Response("Password required", 401, {"WWW-Authenticate": 'Basic realm="PiDash"'})


def _app(app_id: str) -> dict:
    for a in CFG.get("apps", []):
        if a["id"] == app_id:
            return a
    abort(404)


def app_status(a: dict) -> dict:
    units = [SYS.unit_status(u) for u in a["units"]]
    measured = [SYS.unit_status(u) for u in a["measure"]]
    every = units + measured
    running = any(u["active"] in ("active", "activating", "reloading") for u in units)
    partly = running and not all(u["active"] == "active" for u in units)
    failed = any(u["active"] == "failed" for u in units)
    missing = [u["unit"] for u in units if not u["exists"]]
    # a service keeps the "enabled" state; timers/services are what start on boot
    on_boot = all(u["enabled"] in ("enabled", "static", "alias") for u in units)
    starts = [u["since"] for u in units if u["since"] and u["active"] == "active"]
    timers = [u for u in units if u["unit"].endswith(".timer")]
    return {
        "id": a["id"],
        "name": a["name"],
        "description": a.get("description", ""),
        "link": (a.get("link") or "").replace("{host}", request.host.split(":")[0]) or None,
        "ram_mb": a["ram_mb"],
        "confirm_stop": a["confirm_stop"],
        "state": "missing" if missing else "failed" if failed else "partial" if partly else "running" if running else "stopped",
        "missing": missing,
        "on_boot": on_boot,
        "since": min(starts) if starts else None,
        "mem_bytes": sum(u["mem_bytes"] for u in every),
        "cpu_percent": round(sum(u["cpu_percent"] for u in every), 1),
        "next_run": min((t["next_run"] for t in timers if t["next_run"]), default=None),
        "units": every,
    }


@app.get("/")
def index():
    return render_template("index.html", refresh=CFG.get("web", {}).get("refresh_seconds", 3))


@app.get("/api/status")
def api_status():
    return jsonify({
        "time": time.time(),
        "system": SYS.system_stats(),
        "apps": [app_status(a) for a in CFG.get("apps", [])],
    })


@app.post("/api/apps/<app_id>/<action>")
def api_control(app_id: str, action: str):
    if action not in ACTIONS:
        abort(400)
    a = _app(app_id)
    # stop in reverse order so e.g. a timer stops before the thing it triggers
    units = list(reversed(a["units"])) if action in ("stop", "disable") else a["units"]
    if action == "stop":
        units = list(reversed(a["measure"])) + units  # also end any job that's mid-run
    errors = []
    for u in units:
        ok, msg = SYS.control(u, action)
        if not ok and not (action == "stop" and u in a["measure"]):
            errors.append(f"{u}: {msg or 'failed'}")
    if errors:
        return jsonify({"ok": False, "error": "; ".join(errors)}), 500
    return jsonify({"ok": True, "app": app_status(a)})


def main():
    from waitress import serve

    w = CFG.get("web", {})
    serve(app, host=w.get("host", "0.0.0.0"), port=int(w.get("port", 8000)), threads=4)


if __name__ == "__main__":
    main()
