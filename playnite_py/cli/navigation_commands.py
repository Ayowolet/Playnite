"""Navigation system CLI commands."""

import click
import json

from ..navigation import NavigationStateMachine, UIState, NavigationCommand


def output_json(ctx, data):
    """Output data as JSON if json_output flag is set."""
    if ctx.obj.get('json_output'):
        click.echo(json.dumps(data, indent=2, default=str))
        return True
    return False


@click.group()
def navigation():
    """UI navigation system (headless)."""
    pass


@navigation.command()
@click.option('--state', type=click.Choice(['game_grid', 'game_list', 'game_details',
                                             'main_menu', 'filter_menu', 'search']),
              default='game_grid', help='Initial UI state')
@click.pass_context
def init_state(ctx, state):
    """Initialize navigation state machine."""
    state_map = {
        'game_grid': UIState.GAME_GRID,
        'game_list': UIState.GAME_LIST,
        'game_details': UIState.GAME_DETAILS,
        'main_menu': UIState.MAIN_MENU,
        'filter_menu': UIState.FILTER_MENU,
        'search': UIState.SEARCH,
    }

    nav = NavigationStateMachine(state_map[state])
    context = nav.get_context()

    if output_json(ctx, context.to_dict()):
        return

    click.echo(f"Navigation initialized at state: {context.current_state.value}")
    click.echo(f"Cursor position: {context.cursor_position}")
    click.echo(f"Total items: {context.total_items}")


@navigation.command()
@click.option('--columns', default=4, help='Grid columns')
@click.option('--rows', default=3, help='Grid rows')
@click.option('--total-items', default=100, help='Total items')
@click.option('--command', 'commands', multiple=True,
              type=click.Choice(['up', 'down', 'left', 'right', 'select', 'back']),
              help='Navigation commands to execute')
@click.pass_context
def test_navigation(ctx, columns, rows, total_items, commands):
    """Test navigation state machine with commands."""
    nav = NavigationStateMachine(UIState.GAME_GRID)
    nav.set_grid_layout(columns, rows)
    nav.set_total_items(total_items)

    command_map = {
        'up': NavigationCommand.UP,
        'down': NavigationCommand.DOWN,
        'left': NavigationCommand.LEFT,
        'right': NavigationCommand.RIGHT,
        'select': NavigationCommand.SELECT,
        'back': NavigationCommand.BACK,
    }

    results = []
    for cmd_str in commands:
        cmd = command_map[cmd_str]
        handled = nav.handle_command(cmd)
        context = nav.get_context()

        results.append({
            'command': cmd_str,
            'handled': handled,
            'state': context.current_state.value,
            'cursor_position': context.cursor_position,
            'grid_position': context.get_grid_position()
        })

    if output_json(ctx, results):
        return

    click.echo(f"\nNavigation Test (Grid: {columns}x{rows}, Items: {total_items})")
    click.echo("Starting position: 0\n")

    for result in results:
        click.echo(f"Command: {result['command']}")
        click.echo(f"  State: {result['state']}")
        click.echo(f"  Position: {result['cursor_position']} "
                   f"(Row: {result['grid_position'][0]}, Col: {result['grid_position'][1]})")
        click.echo()


@navigation.command()
@click.option('--columns', default=4, help='Grid columns')
@click.option('--rows', default=3, help='Grid rows')
@click.option('--total-items', default=100, help='Total items')
@click.option('--start-pos', default=0, help='Starting position')
@click.pass_context
def show_grid(ctx, columns, rows, total_items, start_pos):
    """Show grid navigation state."""
    nav = NavigationStateMachine(UIState.GAME_GRID)
    nav.set_grid_layout(columns, rows)
    nav.set_total_items(total_items)
    nav.set_cursor_position(start_pos)

    context = nav.get_context()

    if output_json(ctx, context.to_dict()):
        return

    row, col = context.get_grid_position()
    page = row // rows

    click.echo("\nGrid Navigation State:")
    click.echo(f"  Layout: {columns} columns x {rows} rows")
    click.echo(f"  Total Items: {total_items}")
    click.echo(f"  Cursor Position: {start_pos}")
    click.echo(f"  Grid Position: Row {row}, Column {col}")
    click.echo(f"  Current Page: {page}")


@navigation.command()
@click.option('--total-items', default=100, help='Total items')
@click.option('--page-size', default=20, help='Page size')
@click.option('--start-pos', default=0, help='Starting position')
@click.option('--command', 'commands', multiple=True,
              type=click.Choice(['up', 'down', 'page_up', 'page_down']),
              help='Navigation commands')
@click.pass_context
def test_list_navigation(ctx, total_items, page_size, start_pos, commands):
    """Test list navigation."""
    nav = NavigationStateMachine(UIState.GAME_LIST)
    nav.set_view_mode('list')
    nav.set_total_items(total_items)
    nav.context.page_size = page_size
    nav.set_cursor_position(start_pos)

    command_map = {
        'up': NavigationCommand.UP,
        'down': NavigationCommand.DOWN,
        'page_up': NavigationCommand.PAGE_UP,
        'page_down': NavigationCommand.PAGE_DOWN,
    }

    results = []
    for cmd_str in commands:
        cmd = command_map[cmd_str]
        handled = nav.handle_command(cmd)
        context = nav.get_context()

        results.append({
            'command': cmd_str,
            'handled': handled,
            'cursor_position': context.cursor_position,
            'current_page': context.cursor_position // page_size
        })

    if output_json(ctx, results):
        return

    click.echo(f"\nList Navigation Test (Items: {total_items}, Page Size: {page_size})")
    click.echo(f"Starting position: {start_pos}\n")

    for result in results:
        click.echo(f"Command: {result['command']}")
        click.echo(f"  Position: {result['cursor_position']}")
        click.echo(f"  Page: {result['current_page']}")
        click.echo()


@navigation.command()
@click.pass_context
def show_states(ctx):
    """Show available UI states."""
    states = [state.value for state in UIState]

    if output_json(ctx, {'states': states}):
        return

    click.echo("\nAvailable UI States:")
    for state in states:
        click.echo(f"  - {state}")


@navigation.command()
@click.pass_context
def show_commands(ctx):
    """Show available navigation commands."""
    commands = [cmd.value for cmd in NavigationCommand]

    if output_json(ctx, {'commands': commands}):
        return

    click.echo("\nAvailable Navigation Commands:")
    for cmd in commands:
        click.echo(f"  - {cmd}")
