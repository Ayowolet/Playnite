"""Controller management CLI commands."""
from __future__ import annotations

import json
import sys
import time

import click

from ..controller.detection import ControllerDetector
from ..controller.input_handler import ControllerInputHandler
from ..controller.mapping import ButtonMapping
from ..controller.navigation import NavigationStateMachine, UIState
from ..controller.simulation import ControllerSimulator, VibrationController


def _output(data, as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(data, indent=2, default=str))
        return
    if isinstance(data, dict):
        for k, v in data.items():
            click.echo(f"  {k}: {v}")
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                for k, v in item.items():
                    click.echo(f"  {k}: {v}")
                click.echo()
            else:
                click.echo(f"  {item}")
    else:
        click.echo(str(data))


@click.group()
def controller() -> None:
    """Controller detection, input, and navigation commands."""


# ===========================================================================
# Detection
# ===========================================================================


@controller.command("detect")
@click.option("--json", "as_json", is_flag=True)
def ctrl_detect(as_json) -> None:
    """Scan for connected game controllers."""
    detector = ControllerDetector()
    devices = detector.scan()
    _output(
        {
            "count": len(devices),
            "controllers": [d.to_dict() for d in devices],
            "available_backends": detector.available_backends,
        },
        as_json,
    )


# ===========================================================================
# Input testing
# ===========================================================================


@controller.command("test")
@click.option("--device", default=None, help="Device ID to listen on")
@click.option("--timeout", default=10.0, type=float, show_default=True, help="Seconds to listen")
@click.option("--json", "as_json", is_flag=True)
def ctrl_test(device, timeout, as_json) -> None:
    """Listen for raw controller input events."""
    handler = ControllerInputHandler(device_id=device)
    received = []

    def on_event(event):
        received.append(event.to_dict())
        if not as_json:
            click.echo(f"  {event.event_type:6s} {event.code:20s} = {event.value}")

    handler.on_any(on_event)
    handler.start()
    if not as_json:
        click.echo(f"Listening for {timeout}s — press buttons on the controller...")
    try:
        time.sleep(timeout)
    except KeyboardInterrupt:
        pass
    finally:
        handler.stop()

    if as_json:
        _output({"events_received": len(received), "events": received}, as_json)
    else:
        click.echo(f"Total events received: {len(received)}")


# ===========================================================================
# Simulation
# ===========================================================================


@controller.command("simulate")
@click.argument("button")
@click.option("--repeat", default=1, type=int, show_default=True)
@click.option("--json", "as_json", is_flag=True)
def ctrl_simulate(button, repeat, as_json) -> None:
    """Simulate controller button presses (for testing)."""
    sim = ControllerSimulator()
    events = []
    for _ in range(repeat):
        events.extend(e.to_dict() for e in sim.tap_button(button))
    _output({"button": button, "repeat": repeat, "events": events}, as_json)


# ===========================================================================
# Navigation state machine
# ===========================================================================


@controller.command("navigate")
@click.argument("action")
@click.option("--state", "initial", default="main_menu", show_default=True)
@click.option("--json", "as_json", is_flag=True)
def ctrl_navigate(action, initial, as_json) -> None:
    """Send a navigation action to the state machine."""
    try:
        nav = NavigationStateMachine(UIState(initial))
    except ValueError:
        click.echo(f"Unknown state '{initial}'. Valid: {[s.value for s in UIState]}", err=True)
        sys.exit(1)
    transitioned = nav.navigate(action)
    _output(
        {"action": action, "transitioned": transitioned, "state": nav.get_state()},
        as_json,
    )


@controller.command("state")
@click.option("--state", "initial", default="main_menu", show_default=True)
@click.option("--json", "as_json", is_flag=True)
def ctrl_state(initial, as_json) -> None:
    """Show navigation state information."""
    try:
        nav = NavigationStateMachine(UIState(initial))
    except ValueError:
        click.echo(f"Unknown state '{initial}'.", err=True)
        sys.exit(1)
    _output(nav.get_state(), as_json)


@controller.command("run")
@click.option("--mapping-file", default=None, help="Button mapping JSON/YAML file")
@click.option("--device", default=None)
@click.option("--json", "as_json", is_flag=True)
def ctrl_run(mapping_file, device, as_json) -> None:
    """Interactive controller-driven navigation session."""
    mapping = ButtonMapping.load_from_file(mapping_file) if mapping_file else ButtonMapping()
    handler = ControllerInputHandler(device_id=device)
    nav = NavigationStateMachine()

    def on_event(event):
        action = mapping.map_input(event)
        if action:
            transitioned = nav.navigate(action)
            info = {
                "input": event.code,
                "action": action,
                "transitioned": transitioned,
                "state": nav.state_name,
            }
            if as_json:
                click.echo(json.dumps(info))
            else:
                click.echo(f"  {event.code} -> {action} -> {nav.state_name}")

    handler.on_any(on_event)
    handler.start()
    if not as_json:
        click.echo(f"Controller session started (state: {nav.state_name}). Ctrl+C to stop.")
    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        handler.stop()
    if not as_json:
        click.echo(f"Final state: {nav.state_name}")


# ===========================================================================
# Button mapping
# ===========================================================================


@controller.command("mapping")
@click.option("--load", "load_path", default=None, help="Load mapping from file")
@click.option("--save", "save_path", default=None, help="Save mapping to file")
@click.option("--show-default", is_flag=True, help="Print default mapping")
@click.option("--json", "as_json", is_flag=True)
def ctrl_mapping(load_path, save_path, show_default, as_json) -> None:
    """Load, save, or display controller button mappings."""
    if load_path:
        try:
            mapping = ButtonMapping.load_from_file(load_path)
        except FileNotFoundError:
            click.echo(f"File not found: {load_path}", err=True)
            sys.exit(1)
        if not as_json:
            click.echo(f"Loaded mapping from {load_path}")
        _output(mapping.to_dict(), as_json)
    elif save_path:
        ButtonMapping().save_to_file(save_path)
        if not as_json:
            click.echo(f"Default mapping saved to {save_path}")
        else:
            _output({"saved": save_path}, as_json)
    elif show_default:
        _output(ButtonMapping().to_dict(), as_json)
    else:
        click.echo("Provide --load, --save, or --show-default", err=True)
        sys.exit(1)


# ===========================================================================
# Vibration
# ===========================================================================


@controller.command("vibrate")
@click.option("--intensity", default=0.5, type=float, show_default=True)
@click.option("--duration", default=0.5, type=float, show_default=True)
@click.option("--json", "as_json", is_flag=True)
def ctrl_vibrate(intensity, duration, as_json) -> None:
    """Trigger controller vibration / rumble."""
    vib = VibrationController()
    hw_supported = vib.vibrate(intensity, duration)
    _output(
        {"intensity": intensity, "duration": duration, "hardware_supported": hw_supported},
        as_json,
    )
