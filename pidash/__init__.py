"""PiDash: a small dashboard to see and control services on a Raspberry Pi."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def load_config(path: str | Path | None = None) -> dict:
    with open(path or ROOT / "apps.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    seen = set()
    for app in cfg.get("apps", []):
        if app["id"] in seen:
            raise ValueError(f"Duplicate app id: {app['id']}")
        seen.add(app["id"])
        app.setdefault("measure", [])
        app.setdefault("ram_mb", 0)
        app.setdefault("confirm_stop", False)
    return cfg
