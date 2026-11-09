# CLAUDE.md

## What this is

PiDash is a small control dashboard for the owner's **Raspberry Pi 4**. It shows whole-Pi stats (memory, CPU, temperature, storage) and one card per app, with live RAM/CPU, start/stop/restart, and a start-on-boot toggle. The Pi runs a **Minecraft server** and **DealPi** (a deal tracker, separate repo), and both compete for RAM, so the owner uses this to choose what runs. More automations will be added over time, each as a new entry in `apps.yaml`.

The owner is learning; keep config comments and docs beginner-friendly.

## How it works

- `apps.yaml`: the apps. Each has `units` (systemd units the buttons control, in start order), optional `measure` (units counted toward its resources but not directly controlled, e.g. a oneshot service a timer runs), `ram_mb` (start warning threshold), `link`, `confirm_stop`.
- `pidash/system.py`:
  - `unit_status()` calls `systemctl show` and parses key=value output.
  - Per-unit memory and CPU come from reading every PID in the unit's cgroup (`/sys/fs/cgroup/<ControlGroup>/cgroup.procs`, including sub-groups) and summing psutil RSS and CPU%. This deliberately avoids systemd's `MemoryCurrent`, because Raspberry Pi OS kernels may have the memory cgroup controller disabled.
  - psutil `Process` objects are cached so `cpu_percent` has a previous sample to compare against.
  - `FakeSystem` (`PIDASH_FAKE=1`) simulates services for development without systemd.
- `pidash/app.py`: Flask app served by waitress (port 8000 by default).
  - `GET /api/status` returns everything as JSON.
  - `POST /api/apps/<id>/<start|stop|restart|enable|disable>` acts on that app. Stop and disable run in reverse unit order, and stop also stops `measure` units (failures there are ignored).
  - Optional HTTP basic auth when `PIDASH_PASSWORD` is set in `.env`.
- `pidash/templates/index.html`: one page, plain JS that polls `/api/status` every `refresh_seconds`. No build step, no frameworks. Must work on a phone.
- Privileges: the dashboard runs as the normal user and calls `sudo -n systemctl <action> <unit>`. `install.sh` generates `/etc/sudoers.d/pidash` from `apps.yaml` with an exact allowlist (validated with `visudo -cf` before installing), and unit names are checked against a strict regex. **Never** broaden this to arbitrary commands or wildcards, and never pass user input to a shell. Only units listed in `apps.yaml` can be controlled.

## Commands

```bash
PIDASH_FAKE=1 python -m pidash.app          # dev on any machine, http://localhost:8000
python -m pytest -q tests                   # tests use the fake backend
bash install.sh                             # on the Pi; re-run after editing apps.yaml
journalctl -u pidash -f
```

## Conventions

- Keep it light: it runs next to a Minecraft server. Dependencies are flask, waitress, psutil and pyyaml only.
- New controllable things must be systemd units; add templates under `systemd/` (see `minecraft.service.example`, which stops via SIGTERM so the server saves the world).
- Secrets go in `.env` (gitignored), never in `apps.yaml`.
- Add tests for new API behavior in `tests/test_pidash.py` using the fake backend.

## Ideas

- Show recent log lines per app (`journalctl -u <unit> -n 50`, through the same allowlist approach).
- Memory history sparkline per app (sample every minute into SQLite).
- Online player count for Minecraft (server list ping on port 25565).
- "Profiles": one click to switch between e.g. "Gaming" (Minecraft on, DealPi off) and "Normal".
