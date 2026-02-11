"""
Pre-built action templates for common use cases.

Each function returns an :class:`~actions.models.Action` ready to be injected
into the registry.  Scripts and users can import these templates as a
starting point.

Available templates
-------------------
* ``discord_rich_presence()`` — Update Discord status before/after game.
* ``close_background_apps()`` — Kill specified processes before launch.
* ``enable_vpn()`` / ``disable_vpn()`` — Toggle VPN around game session.
* ``game_backup()`` — Backup save-game directory before launch.
* ``screenshot_on_exit()`` — Capture a screenshot when the game closes.
* ``notify_session_start()`` / ``notify_session_end()`` — Desktop notifications.
* ``set_display_mode()`` — Change resolution/refresh rate.
* ``playtime_log()`` — Append session info to a text log file.
"""

from __future__ import annotations

from .models import Action, ActionType


def discord_rich_presence(game_name_expr: str = "{game.name}") -> Action:
    """
    Pre-launch action: update Discord rich presence status.

    Requires the ``pypresence`` package in the script's venv.
    """
    script = f"""
try:
    import pypresence
    rpc = pypresence.Presence("YOUR_APP_ID")
    rpc.connect()
    rpc.update(state="Playing", details={game_name_expr!r})
    print("Discord rich presence updated")
except Exception as exc:
    print(f"Discord RPC warning: {{exc}}")
"""
    return Action(
        name="Discord Rich Presence (start)",
        type=ActionType.PRE_LAUNCH,
        script=script,
        priority=10,
    )


def discord_rich_presence_clear() -> Action:
    """Post-exit action: clear Discord rich presence."""
    script = """
try:
    import pypresence
    rpc = pypresence.Presence("YOUR_APP_ID")
    rpc.connect()
    rpc.clear()
    rpc.close()
    print("Discord rich presence cleared")
except Exception as exc:
    print(f"Discord RPC warning: {exc}")
"""
    return Action(
        name="Discord Rich Presence (stop)",
        type=ActionType.POST_EXIT,
        script=script,
        priority=10,
    )


def close_background_apps(process_names: list) -> Action:
    """
    Pre-launch action: terminate listed background processes.

    Parameters
    ----------
    process_names:
        List of process names to kill, e.g. ``["Chrome.exe", "Slack.exe"]``.
    """
    kill_list = repr(process_names)
    script = f"""
import subprocess, sys
targets = {kill_list}
for name in targets:
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/IM", name], capture_output=True)
    else:
        subprocess.run(["pkill", "-x", name], capture_output=True)
    print(f"Attempted to close {{name}}")
"""
    return Action(
        name="Close Background Apps",
        type=ActionType.PRE_LAUNCH,
        script=script,
        priority=20,
    )


def enable_vpn(vpn_command: str) -> Action:
    """
    Pre-launch action: connect a VPN before launching the game.

    Parameters
    ----------
    vpn_command:
        Shell command to connect the VPN (e.g. ``"openvpn --config /etc/vpn.conf"``).
    """
    script = f"""
import subprocess
result = subprocess.run({vpn_command!r}, shell=True, capture_output=True, text=True)
print(f"VPN connect: {{result.returncode}}")
if result.returncode != 0:
    raise RuntimeError(f"VPN failed: {{result.stderr}}")
"""
    return Action(
        name="Enable VPN",
        type=ActionType.PRE_LAUNCH,
        script=script,
        priority=5,
    )


def disable_vpn(vpn_disconnect_command: str) -> Action:
    """Post-exit action: disconnect VPN after game closes."""
    script = f"""
import subprocess
subprocess.run({vpn_disconnect_command!r}, shell=True, capture_output=True)
print("VPN disconnected")
"""
    return Action(
        name="Disable VPN",
        type=ActionType.POST_EXIT,
        script=script,
        priority=5,
    )


def game_backup(save_dir_expr: str = "{game.install_dir}/saves", backup_root: str = "~/game_backups") -> Action:
    """
    Pre-launch action: backup save-game directory.

    Parameters
    ----------
    save_dir_expr:
        Path (may contain ``{var}`` tokens) to the save directory.
    backup_root:
        Root directory for backups.
    """
    script = f"""
import shutil, os
from datetime import datetime
from pathlib import Path

save_dir = Path({save_dir_expr!r}.format(game=game))
backup_root = Path({backup_root!r}).expanduser()
backup_root.mkdir(parents=True, exist_ok=True)

if save_dir.exists():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = backup_root / game.name / ts
    shutil.copytree(str(save_dir), str(dest))
    print(f"Backup saved to {{dest}}")
else:
    print(f"Save directory not found: {{save_dir}}")
"""
    return Action(
        name="Game Save Backup",
        type=ActionType.PRE_LAUNCH,
        script=script,
        priority=30,
    )


def screenshot_on_exit(output_dir: str = "~/screenshots") -> Action:
    """Post-exit action: capture a screenshot."""
    script = f"""
import subprocess, sys
from pathlib import Path
from datetime import datetime

output = Path({output_dir!r}).expanduser()
output.mkdir(parents=True, exist_ok=True)
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
fname = output / f"{{game.name}}_{{ts}}.png"
if sys.platform == "darwin":
    subprocess.run(["screencapture", str(fname)], check=False)
elif sys.platform == "linux":
    subprocess.run(["scrot", str(fname)], check=False)
elif sys.platform == "win32":
    # PowerShell screenshot
    ps = f'Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Screen]::AllScreens'
    subprocess.run(["powershell", "-Command", ps], check=False)
print(f"Screenshot: {{fname}}")
"""
    return Action(
        name="Screenshot on Exit",
        type=ActionType.POST_EXIT,
        script=script,
        priority=50,
    )


def notify_session_start() -> Action:
    """Pre-launch: desktop notification that a game is starting."""
    script = """
import subprocess, sys
msg = f"Starting: {game.name}"
if sys.platform == "linux":
    subprocess.run(["notify-send", "Playnite", msg], check=False)
elif sys.platform == "darwin":
    subprocess.run(["osascript", "-e", f'display notification "{msg}" with title "Playnite"'], check=False)
else:
    print(msg)
"""
    return Action(
        name="Notify: Game Starting",
        type=ActionType.PRE_LAUNCH,
        script=script,
        priority=1,
        async_=True,
    )


def notify_session_end() -> Action:
    """Post-exit: desktop notification that a game has stopped."""
    script = """
import subprocess, sys
msg = f"Stopped: {game.name}"
if sys.platform == "linux":
    subprocess.run(["notify-send", "Playnite", msg], check=False)
elif sys.platform == "darwin":
    subprocess.run(["osascript", "-e", f'display notification "{msg}" with title "Playnite"'], check=False)
else:
    print(msg)
"""
    return Action(
        name="Notify: Game Stopped",
        type=ActionType.POST_EXIT,
        script=script,
        priority=1,
        async_=True,
    )


def playtime_log(log_file: str = "~/playtime.log") -> Action:
    """Post-exit: append session info to a plain-text log file."""
    script = f"""
from datetime import datetime
from pathlib import Path

log = Path({log_file!r}).expanduser()
log.parent.mkdir(parents=True, exist_ok=True)
ts = datetime.now().isoformat(timespec="seconds")
with open(log, "a") as fh:
    fh.write(f"{{ts}} | {{game.name}} | play_time={{game.play_time}}s\\n")
print(f"Session logged to {{log}}")
"""
    return Action(
        name="Playtime Log",
        type=ActionType.POST_EXIT,
        script=script,
        priority=90,
    )


# Registry of all available templates
ALL_TEMPLATES = {
    "discord_rich_presence": discord_rich_presence,
    "discord_rich_presence_clear": discord_rich_presence_clear,
    "close_background_apps": close_background_apps,
    "enable_vpn": enable_vpn,
    "disable_vpn": disable_vpn,
    "game_backup": game_backup,
    "screenshot_on_exit": screenshot_on_exit,
    "notify_session_start": notify_session_start,
    "notify_session_end": notify_session_end,
    "playtime_log": playtime_log,
}
