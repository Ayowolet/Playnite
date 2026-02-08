"""Controller management CLI commands."""

import click
import json
from pathlib import Path

from ..controller import (
    ControllerManager, InputHandler, ControllerSimulator,
    ControllerConfig
)


def output_json(ctx, data):
    """Output data as JSON if json_output flag is set."""
    if ctx.obj.get('json_output'):
        click.echo(json.dumps(data, indent=2, default=str))
        return True
    return False


@click.group()
def controller():
    """Controller and input management."""
    pass


@controller.command()
@click.pass_context
def detect(ctx):
    """Detect connected controllers."""
    manager = ControllerManager(headless=False)

    try:
        controllers = manager.detect_controllers()

        if output_json(ctx, [c.to_dict() for c in controllers]):
            return

        if controllers:
            click.echo(f"Found {len(controllers)} controller(s):")
            for ctrl in controllers:
                click.echo(f"  [{ctrl.id}] {ctrl.name}")
                click.echo(f"      Buttons: {ctrl.joystick.get_numbuttons()}")
                click.echo(f"      Axes: {ctrl.joystick.get_numaxes()}")
                click.echo(f"      Hats: {ctrl.joystick.get_numhats()}")
        else:
            click.echo("No controllers detected")

    except Exception as e:
        click.echo(f"Error detecting controllers: {e}", err=True)
        ctx.exit(1)
    finally:
        manager.shutdown()


@controller.command()
@click.argument('controller_id', type=int, default=0)
@click.pass_context
def test_input(ctx, controller_id):
    """Test controller input (press buttons to see events)."""
    manager = ControllerManager(headless=False)
    input_handler = InputHandler(headless=False)

    try:
        controllers = manager.detect_controllers()
        if not controllers:
            click.echo("No controllers detected", err=True)
            ctx.exit(1)

        if controller_id >= len(controllers):
            click.echo(f"Controller {controller_id} not found", err=True)
            ctx.exit(1)

        click.echo(f"Testing controller [{controller_id}] {controllers[controller_id].name}")
        click.echo("Press buttons (Ctrl+C to stop)...")

        try:
            while True:
                events = input_handler.process_events()
                for event in events:
                    if event.controller_id == controller_id:
                        click.echo(f"  {event.input_type.value}: button={event.button_id}, "
                                   f"axis={event.axis_id}, value={event.axis_value}")
        except KeyboardInterrupt:
            click.echo("\nStopped testing")

    except Exception as e:
        click.echo(f"Error testing input: {e}", err=True)
        ctx.exit(1)
    finally:
        manager.shutdown()


@controller.command()
@click.option('--controller-id', default=0, help='Controller ID')
@click.option('--low-freq', default=0.5, type=float, help='Low frequency (0-1)')
@click.option('--high-freq', default=0.5, type=float, help='High frequency (0-1)')
@click.option('--duration', default=500, type=int, help='Duration in ms')
@click.pass_context
def rumble(ctx, controller_id, low_freq, high_freq, duration):
    """Test controller rumble/vibration."""
    manager = ControllerManager(headless=False)

    try:
        controllers = manager.detect_controllers()
        if not controllers or controller_id >= len(controllers):
            click.echo("Controller not found", err=True)
            ctx.exit(1)

        click.echo(f"Rumbling controller {controller_id}...")
        manager.rumble_controller(controller_id, low_freq, high_freq, duration)
        click.echo("Done")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(1)
    finally:
        manager.shutdown()


@controller.command()
@click.option('--format', type=click.Choice(['json', 'yaml']), default='yaml',
              help='Output format')
@click.option('--output', type=click.Path(), help='Output file')
@click.pass_context
def export_mappings(ctx, format, output):
    """Export default controller mappings."""
    config = ControllerConfig()

    try:
        if output:
            output_path = Path(output)
            config.save_to_file(output_path, format=format)
            click.echo(f"Mappings exported to {output}")
        else:
            data = config.to_dict()
            if format == 'json':
                click.echo(json.dumps(data, indent=2))
            else:
                import yaml
                click.echo(yaml.dump(data, default_flow_style=False))

    except Exception as e:
        click.echo(f"Error exporting mappings: {e}", err=True)
        ctx.exit(1)


@controller.command()
@click.argument('config_file', type=click.Path(exists=True))
@click.pass_context
def show_mapping(ctx, config_file):
    """Show controller mapping from config file."""
    config = ControllerConfig(Path(config_file))

    try:
        data = config.to_dict()

        if output_json(ctx, data):
            return

        click.echo(f"\nController Mappings from {config_file}:")
        click.echo(f"Default Mapping: {data['default_mapping']}")
        click.echo("\nAvailable Mappings:")
        for name in data['mappings']:
            click.echo(f"  - {name}")

    except Exception as e:
        click.echo(f"Error loading mapping: {e}", err=True)
        ctx.exit(1)


@controller.group()
def simulate():
    """Simulate controller input for testing."""
    pass


@simulate.command()
@click.option('--controller-id', default=0, help='Virtual controller ID')
@click.option('--button', type=int, required=True, help='Button ID')
@click.pass_context
def button_press(ctx, controller_id, button):
    """Simulate a button press."""
    input_handler = InputHandler(headless=True)
    simulator = ControllerSimulator(input_handler)

    # Create virtual controller if needed
    if controller_id >= len(simulator.virtual_controllers):
        simulator.add_virtual_controller()

    simulator.simulate_button_click(controller_id, button)

    events = input_handler.get_event_history(limit=2)

    if output_json(ctx, [e.to_dict() for e in events]):
        return

    click.echo(f"Simulated button {button} press on controller {controller_id}")
    for event in events:
        click.echo(f"  Event: {event.input_type.value}")


@simulate.command()
@click.option('--controller-id', default=0, help='Virtual controller ID')
@click.argument('sequence_file', type=click.Path(exists=True))
@click.pass_context
def sequence(ctx, controller_id, sequence_file):
    """Simulate a sequence of inputs from JSON file."""
    input_handler = InputHandler(headless=True)
    simulator = ControllerSimulator(input_handler)

    # Create virtual controller
    simulator.add_virtual_controller()

    try:
        with open(sequence_file, 'r') as f:
            sequence = json.load(f)

        simulator.simulate_sequence(controller_id, sequence)

        events = input_handler.get_event_history()

        if output_json(ctx, [e.to_dict() for e in events]):
            return

        click.echo(f"Simulated {len(events)} input events:")
        for event in events:
            click.echo(f"  {event.input_type.value}: button={event.button_id}")

    except Exception as e:
        click.echo(f"Error simulating sequence: {e}", err=True)
        ctx.exit(1)


# Add simulate subgroup to controller group
controller.add_command(simulate)
