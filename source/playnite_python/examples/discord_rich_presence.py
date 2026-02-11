"""
Discord Rich Presence extension script.

Automatically updates your Discord status when you start or stop playing a
game managed by Playnite Python.

Setup
-----
1. Copy this file to your extensions directory.
2. Create a Discord application at https://discord.com/developers/applications
3. Copy the Application ID and paste it below.
4. Install pypresence: add ``dependencies: [pypresence]`` to the companion
   ``.yaml`` config.

Config (discord_rich_presence.yaml)
------------------------------------
enabled: true
timeout: 10
sandbox_level: standard
dependencies:
  - pypresence
metadata:
  author: Playnite Python Contributors
  version: 1.0
  description: Discord Rich Presence integration
"""

# ---------------------------------------------------------------------------
# Configuration — edit this
# ---------------------------------------------------------------------------

DISCORD_APP_ID = "YOUR_APPLICATION_ID"  # Replace with your Discord App ID

# ---------------------------------------------------------------------------
# Script globals
# ---------------------------------------------------------------------------

_rpc = None        # pypresence.Presence instance
_connected = False

# ---------------------------------------------------------------------------
# Lifecycle hooks
# ---------------------------------------------------------------------------

def on_script_loaded():
    __logger.Info("Discord Rich Presence script loaded.")
    _connect()


def on_game_starting(game):
    """Update Discord status when a game is starting."""
    if not _connected:
        _connect()
    try:
        _rpc.update(
            state="Loading…",
            details=game.name,
            large_image="playnite_logo",
            large_text="Playnite Python",
        )
        __logger.Info(f"Discord status updated: {game.name}")
    except Exception as exc:
        __logger.Warning(f"Could not update Discord status: {exc}")


def on_game_started(game):
    """Refine status once the game is confirmed running."""
    if not _connected:
        return
    try:
        import time
        _rpc.update(
            state="In Game",
            details=game.name,
            start=int(time.time()),
            large_image="playnite_logo",
            large_text="Playnite Python",
        )
    except Exception as exc:
        __logger.Warning(f"Rich presence update failed: {exc}")


def on_game_stopped(game, elapsed_seconds):
    """Clear the Discord status when the game closes."""
    if not _connected:
        return
    try:
        _rpc.clear()
        h = int(elapsed_seconds // 3600)
        m = int((elapsed_seconds % 3600) // 60)
        __logger.Info(f"Session ended: {game.name} ({h}h {m}m)")
    except Exception as exc:
        __logger.Warning(f"Could not clear Discord status: {exc}")


def on_application_stopped():
    """Disconnect cleanly when Playnite closes."""
    global _rpc, _connected
    if _connected and _rpc:
        try:
            _rpc.close()
        except Exception:
            pass
        _connected = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _connect():
    global _rpc, _connected
    try:
        import pypresence  # type: ignore[import]
        _rpc = pypresence.Presence(DISCORD_APP_ID)
        _rpc.connect()
        _connected = True
        __logger.Info("Connected to Discord RPC.")
    except ImportError:
        __logger.Warning(
            "pypresence not installed. Add 'pypresence' to dependencies in the YAML config."
        )
    except Exception as exc:
        __logger.Warning(f"Discord connection failed: {exc}")
