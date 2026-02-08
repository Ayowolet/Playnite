"""CLI commands for view preset management."""

import click
import json

from ..database import get_session, ViewConfigOperations


def output_json(ctx, data):
    """Output data as JSON if json_output flag is set."""
    if ctx.obj.get('json_output'):
        click.echo(json.dumps(data, indent=2, default=str))
        return True
    return False


@click.group()
def view():
    """Manage view presets."""
    pass


@view.command()
@click.argument('name')
@click.option('--description', help='Description of the view preset')
@click.option('--view-mode', default='grid', type=click.Choice(['grid', 'list', 'details']),
              help='View mode')
@click.option('--grid-size', default='medium', type=click.Choice(['small', 'medium', 'large', 'extra_large']),
              help='Grid size (for grid view)')
@click.option('--sort-by', default='name', help='Field to sort by')
@click.option('--sort-dir', default='asc', type=click.Choice(['asc', 'desc']),
              help='Sort direction')
@click.option('--group-by', help='Field to group by')
@click.option('--big-picture', is_flag=True, help='This is a big picture mode preset')
@click.pass_context
def save(ctx, name, description, view_mode, grid_size, sort_by, sort_dir, group_by, big_picture):
    """Save a new view preset."""
    session = get_session()
    ops = ViewConfigOperations(session)

    try:
        # Check if already exists
        existing = ops.get_view_config_by_name(name)
        if existing:
            click.echo(f"Error: View preset '{name}' already exists. Use 'update' to modify it.", err=True)
            ctx.exit(1)

        # Create view config
        config = ops.create_view_config(
            name=name,
            description=description,
            view_mode=view_mode,
            grid_size=grid_size,
            sort_field=sort_by,
            sort_direction=sort_dir,
            group_by=group_by,
            is_big_picture_mode=big_picture
        )

        if output_json(ctx, {
            'id': config.id,
            'name': config.name,
            'view_mode': config.view_mode,
            'sort_field': config.sort_field
        }):
            return

        click.echo(f"Saved view preset: {config.name}")
        click.echo(f"  ID: {config.id}")
        click.echo(f"  View mode: {config.view_mode}")
        click.echo(f"  Sort by: {config.sort_field} ({config.sort_direction})")

    except Exception as e:
        click.echo(f"Error saving view preset: {e}", err=True)
        ctx.exit(1)
    finally:
        session.close()


@view.command()
@click.argument('name')
@click.pass_context
def load(ctx, name):
    """Load and display a view preset."""
    session = get_session()
    ops = ViewConfigOperations(session)

    try:
        config = ops.get_view_config_by_name(name)
        if not config:
            click.echo(f"View preset '{name}' not found", err=True)
            ctx.exit(1)

        config_dict = ops.apply_view_config(config.id)

        if output_json(ctx, config_dict):
            return

        click.echo(f"\nView Preset: {config.name}")
        click.echo(f"ID: {config.id}")
        if config.description:
            click.echo(f"Description: {config.description}")
        click.echo(f"View Mode: {config.view_mode}")
        click.echo(f"Grid Size: {config.grid_size}")
        click.echo(f"Sort By: {config.sort_field} ({config.sort_direction})")
        if config.group_by:
            click.echo(f"Group By: {config.group_by}")
        click.echo(f"Big Picture Mode: {'Yes' if config.is_big_picture_mode else 'No'}")

    except Exception as e:
        click.echo(f"Error loading view preset: {e}", err=True)
        ctx.exit(1)
    finally:
        session.close()


@view.command()
@click.option('--big-picture', is_flag=True, help='Show only big picture mode presets')
@click.pass_context
def list(ctx, big_picture):
    """List all view presets."""
    session = get_session()
    ops = ViewConfigOperations(session)

    try:
        configs = ops.get_all_view_configs(big_picture_only=big_picture)

        if output_json(ctx, [{
            'id': c.id,
            'name': c.name,
            'view_mode': c.view_mode,
            'sort_field': c.sort_field,
            'is_big_picture': c.is_big_picture_mode
        } for c in configs]):
            return

        if not configs:
            click.echo("No view presets found")
            return

        click.echo(f"\nView Presets ({len(configs)}):")
        for config in configs:
            mode_label = " [Big Picture]" if config.is_big_picture_mode else ""
            click.echo(f"  [{config.id}] {config.name}{mode_label}")
            click.echo(f"      Mode: {config.view_mode}, Sort: {config.sort_field} ({config.sort_direction})")

    except Exception as e:
        click.echo(f"Error listing view presets: {e}", err=True)
        ctx.exit(1)
    finally:
        session.close()


@view.command()
@click.argument('name')
@click.pass_context
def show(ctx, name):
    """Show detailed information about a view preset."""
    session = get_session()
    ops = ViewConfigOperations(session)

    try:
        config = ops.get_view_config_by_name(name)
        if not config:
            click.echo(f"View preset '{name}' not found", err=True)
            ctx.exit(1)

        display_settings = config.get_display_settings()

        data = {
            'id': config.id,
            'name': config.name,
            'description': config.description,
            'view_mode': config.view_mode,
            'grid_size': config.grid_size,
            'sort_field': config.sort_field,
            'sort_direction': config.sort_direction,
            'group_by': config.group_by,
            'is_big_picture_mode': config.is_big_picture_mode,
            'display_settings': display_settings,
            'created_at': config.created_at.isoformat() if config.created_at else None,
            'updated_at': config.updated_at.isoformat() if config.updated_at else None
        }

        if output_json(ctx, data):
            return

        click.echo(f"\nView Preset Details: {config.name}")
        click.echo(f"{'=' * 50}")
        click.echo(f"ID: {config.id}")
        if config.description:
            click.echo(f"Description: {config.description}")
        click.echo(f"View Mode: {config.view_mode}")
        click.echo(f"Grid Size: {config.grid_size}")
        click.echo(f"Sort Field: {config.sort_field}")
        click.echo(f"Sort Direction: {config.sort_direction}")
        if config.group_by:
            click.echo(f"Group By: {config.group_by}")
        click.echo(f"Big Picture Mode: {'Yes' if config.is_big_picture_mode else 'No'}")

        if display_settings:
            click.echo("\nDisplay Settings:")
            for key, value in display_settings.items():
                click.echo(f"  {key}: {value}")

    except Exception as e:
        click.echo(f"Error showing view preset: {e}", err=True)
        ctx.exit(1)
    finally:
        session.close()


@view.command()
@click.argument('name')
@click.pass_context
def delete(ctx, name):
    """Delete a view preset."""
    session = get_session()
    ops = ViewConfigOperations(session)

    try:
        config = ops.get_view_config_by_name(name)
        if not config:
            click.echo(f"View preset '{name}' not found", err=True)
            ctx.exit(1)

        if click.confirm(f"Delete view preset '{name}'?"):
            ops.delete_view_config(config.id)
            click.echo(f"Deleted view preset: {name}")

    except Exception as e:
        click.echo(f"Error deleting view preset: {e}", err=True)
        ctx.exit(1)
    finally:
        session.close()


@view.command()
@click.argument('name')
@click.option('--description', help='New description')
@click.option('--view-mode', type=click.Choice(['grid', 'list', 'details']), help='New view mode')
@click.option('--grid-size', type=click.Choice(['small', 'medium', 'large', 'extra_large']), help='New grid size')
@click.option('--sort-by', help='New sort field')
@click.option('--sort-dir', type=click.Choice(['asc', 'desc']), help='New sort direction')
@click.option('--group-by', help='New group by field')
@click.pass_context
def update(ctx, name, description, view_mode, grid_size, sort_by, sort_dir, group_by):
    """Update an existing view preset."""
    session = get_session()
    ops = ViewConfigOperations(session)

    try:
        config = ops.get_view_config_by_name(name)
        if not config:
            click.echo(f"View preset '{name}' not found", err=True)
            ctx.exit(1)

        # Build updates dictionary
        updates = {}
        if description is not None:
            updates['description'] = description
        if view_mode:
            updates['view_mode'] = view_mode
        if grid_size:
            updates['grid_size'] = grid_size
        if sort_by:
            updates['sort_field'] = sort_by
        if sort_dir:
            updates['sort_direction'] = sort_dir
        if group_by is not None:
            updates['group_by'] = group_by

        if not updates:
            click.echo("No updates specified", err=True)
            ctx.exit(1)

        ops.update_view_config(config.id, **updates)
        click.echo(f"Updated view preset: {name}")

    except Exception as e:
        click.echo(f"Error updating view preset: {e}", err=True)
        ctx.exit(1)
    finally:
        session.close()
