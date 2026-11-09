# PiDash

One page that shows what your Raspberry Pi is running, how much memory and CPU each app is using, and lets you start, stop or restart each app, or choose whether it starts on boot.

## Install

1. Copy this folder to the Pi (GitHub + `git clone`, or `scp -r pidash you@raspberrypi.local:~/`).
2. `cd ~/pidash && bash install.sh`
3. Open `http://raspberrypi.local:8000`.

## Make your Minecraft server controllable

PiDash controls apps that run as **systemd services** (the Pi's built-in way of running background programs). DealPi already does. If your Minecraft server currently runs in a terminal, `screen` or `tmux`, switch it over once:

1. Open `systemd/minecraft.service.example` and edit the lines marked **CHANGE ME**: your username, your server folder, the jar name and the memory limit.
2. Stop the server the old way (type `stop` in its console).
3. Install it:
   ```
   sudo cp systemd/minecraft.service.example /etc/systemd/system/minecraft.service
   sudo systemctl daemon-reload
   sudo systemctl enable --now minecraft
   ```
4. Refresh the dashboard. The Minecraft card should say **Running**.

Stopping from the dashboard saves the world first, just like typing `stop`. To see the server's console output, run `journalctl -u minecraft -f`.

If your server already runs as a service with a different name, just put that name in `apps.yaml` instead.

## Adding another app or automation

1. Make it a systemd service (and a `.timer` if it should run on a schedule; DealPi's `systemd/` folder has examples).
2. Add it to `apps.yaml`:
   ```yaml
     - id: myscript
       name: My script
       description: What it does
       units: [myscript.service]
       ram_mb: 100
   ```
3. Run `bash install.sh` again. It updates the list of services the dashboard is allowed to control.

## Safety

- The dashboard can only start, stop, restart, enable or disable the exact services listed in `apps.yaml`. `install.sh` writes that allowlist to `/etc/sudoers.d/pidash`. It can't run any other command as admin.
- Anyone on your Wi-Fi can open the page. To require a password, put `PIDASH_PASSWORD=something` in a `.env` file in this folder and run `sudo systemctl restart pidash`. (Don't commit `.env` to GitHub; it's already in `.gitignore`.)
- Before starting an app, the dashboard warns you if there's less free memory than its `ram_mb`.

## Commands

| What | Command |
|---|---|
| Dashboard log | `journalctl -u pidash -f` |
| Restart the dashboard | `sudo systemctl restart pidash` |
| Try it on a computer with fake services | `PIDASH_FAKE=1 python -m pidash.app` |
| Run tests | `.venv/bin/pip install pytest && .venv/bin/python -m pytest -q tests` |
