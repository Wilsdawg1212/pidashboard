"""Reading and controlling systemd services, plus whole-Pi stats.

Memory and CPU per service are measured by finding every process in the
service's control group (/sys/fs/cgroup/...) and adding up their usage with
psutil. This works even on Raspberry Pi OS builds where the kernel's memory
accounting for services is switched off.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

import psutil

SYSTEMCTL = shutil.which("systemctl") or "/usr/bin/systemctl"
CGROUP_ROOT = Path("/sys/fs/cgroup")
PROPS = ["ActiveState", "SubState", "UnitFileState", "LoadState", "ActiveEnterTimestamp",
         "ControlGroup", "MainPID", "NextElapseUSecRealtime", "LastTriggerUSec"]

# psutil needs to see a process twice to measure its CPU %, so keep them around
_proc_cache: dict[int, psutil.Process] = {}


def _run(args: list[str], timeout: int = 15) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def parse_show(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k] = v
    return out


def _parse_systemd_time(s: str) -> float | None:
    """'Mon 2026-11-09 02:40:00 EST' -> unix time. Empty/'n/a' -> None."""
    if not s or s in ("n/a", "0"):
        return None
    parts = s.split()
    if len(parts) >= 3:
        try:
            # the timezone abbreviation is the Pi's own, so local time is right
            return datetime.strptime(f"{parts[1]} {parts[2]}", "%Y-%m-%d %H:%M:%S").timestamp()
        except ValueError:
            return None
    return None


def _pids(control_group: str) -> list[int]:
    if not control_group:
        return []
    procs = CGROUP_ROOT / control_group.lstrip("/") / "cgroup.procs"
    pids = []
    try:
        pids += [int(p) for p in procs.read_text().split()]
    except OSError:
        return []
    # include nested groups (some services start children in sub-groups)
    for sub in (CGROUP_ROOT / control_group.lstrip("/")).glob("*/cgroup.procs"):
        try:
            pids += [int(p) for p in sub.read_text().split()]
        except OSError:
            pass
    return pids


def _usage(pids: list[int]) -> tuple[int, float]:
    """(resident memory bytes, CPU % of the whole Pi) for a set of processes."""
    rss, cpu = 0, 0.0
    for pid in pids:
        p = _proc_cache.get(pid)
        try:
            if p is None:
                p = psutil.Process(pid)
                p.cpu_percent(None)  # first call primes the counter
                _proc_cache[pid] = p
            rss += p.memory_info().rss
            cpu += p.cpu_percent(None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            _proc_cache.pop(pid, None)
    return rss, cpu / (psutil.cpu_count() or 1)


def unit_status(unit: str) -> dict:
    r = _run([SYSTEMCTL, "show", unit, *[f"--property={p}" for p in PROPS]])
    s = parse_show(r.stdout)
    pids = _pids(s.get("ControlGroup", ""))
    rss, cpu = _usage(pids)
    return {
        "unit": unit,
        "exists": s.get("LoadState") not in (None, "", "not-found"),
        "active": s.get("ActiveState", "unknown"),
        "sub": s.get("SubState", ""),
        "enabled": s.get("UnitFileState", ""),
        "since": _parse_systemd_time(s.get("ActiveEnterTimestamp", "")),
        "next_run": _parse_systemd_time(s.get("NextElapseUSecRealtime", "")),
        "last_run": _parse_systemd_time(s.get("LastTriggerUSec", "")),
        "mem_bytes": rss,
        "cpu_percent": round(cpu, 1),
        "pids": len(pids),
    }


def control(unit: str, action: str) -> tuple[bool, str]:
    """Start/stop/restart/enable/disable one unit through the sudo allowlist."""
    r = _run(["sudo", "-n", SYSTEMCTL, action, unit], timeout=90)
    msg = (r.stderr or r.stdout).strip()
    return r.returncode == 0, msg


def system_stats() -> dict:
    vm = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk = psutil.disk_usage("/")
    temp = None
    try:
        temp = int(Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1000
    except (OSError, ValueError):
        pass
    load1, load5, _ = os.getloadavg()
    return {
        "cpu_percent": psutil.cpu_percent(None),
        "cpu_count": psutil.cpu_count(),
        "load": [round(load1, 2), round(load5, 2)],
        "mem_total": vm.total,
        "mem_used": vm.total - vm.available,
        "mem_available": vm.available,
        "swap_used": swap.used,
        "swap_total": swap.total,
        "disk_used": disk.used,
        "disk_total": disk.total,
        "temp_c": temp,
        "uptime": time.time() - psutil.boot_time(),
        "hostname": os.uname().nodename,
    }


class FakeSystem:
    """Pretend services for trying the page on a computer without systemd.
    Turn on with PIDASH_FAKE=1."""

    def __init__(self):
        self.state = {"minecraft.service": True, "dealpi-web.service": True, "dealpi-collect.timer": True}
        self.enabled = {u: True for u in self.state}
        self.started = {u: time.time() - 3 * 3600 for u in self.state}

    def unit_status(self, unit: str) -> dict:
        on = self.state.get(unit, False)
        mem = {"minecraft.service": 1_650_000_000, "dealpi-web.service": 290_000_000}.get(unit, 0)
        timer = unit.endswith(".timer")
        return {
            "unit": unit, "exists": unit in self.state or unit == "dealpi-collect.service",
            "active": "active" if on else "inactive", "sub": ("waiting" if timer else "running") if on else "dead",
            "enabled": "enabled" if self.enabled.get(unit) else ("static" if unit not in self.state else "disabled"),
            "since": self.started.get(unit) if on else None,
            "next_run": time.time() + 420 if timer and on else None,
            "last_run": time.time() - 180 if timer else None,
            "mem_bytes": mem if on else 0, "cpu_percent": (21.5 if "minecraft" in unit else 0.4) if on else 0.0,
            "pids": 1 if on and not timer else 0,
        }

    def control(self, unit: str, action: str) -> tuple[bool, str]:
        if action in ("start", "restart"):
            self.state[unit], self.started[unit] = True, time.time()
        elif action == "stop":
            self.state[unit] = False
        elif action in ("enable", "disable"):
            self.enabled[unit] = action == "enable"
        return True, ""

    def system_stats(self) -> dict:
        s = system_stats()
        used = sum(self.unit_status(u)["mem_bytes"] for u in self.state) + 450_000_000
        total = 4 * 1024**3
        s.update(mem_total=total, mem_used=used, mem_available=total - used, temp_c=s["temp_c"] or 52.1, hostname="raspberrypi")
        return s
