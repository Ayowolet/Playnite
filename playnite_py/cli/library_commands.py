"""Library management CLI commands."""

import click
import json
from datetime import datetime

from ..database import get_session, GameOperations, LibraryOperations
from ..organisation import GameFilter, GameSearch, SmartCollectionManager, BulkOperations
from ..models import Game


def output_json(ctx, data):
    """Output data as JSON if json_output flag is set."""
    if ctx.obj.get('json_output'):
        click.echo(json.dumps(data, indent=2, default=str))
        return True
    return False


def format_game(game: Game) -> dict:
    """Format game as dictionary for output."""
    return {
        'id': game.id,
        'name': game.name,
        'platforms': [p.name for p in game.platforms],
        'genres': [g.name for g in game.genres],
        'developers': [d.name for d in game.developers],
        'publishers': [p.name for p in game.publishers],
        'release_date': game.release_date.isoformat() if game.release_date else None,
        'playtime': game.playtime,
        'is_favorite': game.is_favorite,
        'is_hidden': game.is_hidden,
        'tags': [t.name for t in game.tags],
        'categories': [c.name for c in game.categories],
    }


@click.group()
def library():
    """Manage game library."""
    pass


@library.command()
@click.argument('name')
@click.option('--platform', multiple=True, help='Platform(s)')
@click.option('--genre', multiple=True, help='Genre(s)')
@click.option('--developer', help='Developer')
@click.option('--publisher', help='Publisher')
@click.option('--release-date', help='Release date (YYYY-MM-DD)')
@click.pass_context
def add(ctx, name, platform, genre, developer, publisher, release_date):
    """Add a new game to the library."""
    session = get_session()
    ops = GameOperations(session)

    try:
        # Parse release date
        release_date_obj = None
        if release_date:
            release_date_obj = datetime.strptime(release_date, '%Y-%m-%d').date()

        game = ops.create_game(name, release_date=release_date_obj)

        # Add platforms
        for plat in platform:
            ops.add_platform_to_game(game.id, plat)

        # Add genres
        for gen in genre:
            ops.add_genre_to_game(game.id, gen)

        if not output_json(ctx, format_game(game)):
            click.echo(f"Added game: {game.name} (ID: {game.id})")

    except Exception as e:
        click.echo(f"Error adding game: {e}", err=True)
        ctx.exit(1)
    finally:
        session.close()


@library.command()
@click.option('--limit', default=50, help='Maximum results to show')
@click.option('--sort-by', default='name', help='Field to sort by')
@click.option('--sort-desc', is_flag=True, help='Sort descending')
@click.pass_context
def list(ctx, limit, sort_by, sort_desc):
    """List all games in the library."""
    session = get_session()
    game_filter = GameFilter(session)

    try:
        games = game_filter.filter_games(
            {},
            sort_by=sort_by,
            sort_desc=sort_desc,
            limit=limit
        )

        if output_json(ctx, [format_game(g) for g in games]):
            return

        click.echo(f"Found {len(games)} games:")
        for game in games:
            platforms = ", ".join([p.name for p in game.platforms])
            click.echo(f"  [{game.id}] {game.name} ({platforms})")

    except Exception as e:
        click.echo(f"Error listing games: {e}", err=True)
        ctx.exit(1)
    finally:
        session.close()


@library.command()
@click.argument('game_id', type=int)
@click.pass_context
def show(ctx, game_id):
    """Show detailed information about a game."""
    session = get_session()
    ops = GameOperations(session)

    try:
        game = ops.get_game(game_id)
        if not game:
            click.echo(f"Game with ID {game_id} not found", err=True)
            ctx.exit(1)

        if output_json(ctx, format_game(game)):
            return

        click.echo(f"\nGame: {game.name}")
        click.echo(f"ID: {game.id}")
        click.echo(f"Platforms: {', '.join([p.name for p in game.platforms])}")
        click.echo(f"Genres: {', '.join([g.name for g in game.genres])}")
        click.echo(f"Developers: {', '.join([d.name for d in game.developers])}")
        click.echo(f"Publishers: {', '.join([p.name for p in game.publishers])}")
        click.echo(f"Tags: {', '.join([t.name for t in game.tags])}")
        click.echo(f"Categories: {', '.join([c.name for c in game.categories])}")
        click.echo(f"Release Date: {game.release_date or 'Unknown'}")
        click.echo(f"Playtime: {game.playtime} minutes")
        click.echo(f"Favorite: {'Yes' if game.is_favorite else 'No'}")
        click.echo(f"Hidden: {'Yes' if game.is_hidden else 'No'}")

    except Exception as e:
        click.echo(f"Error showing game: {e}", err=True)
        ctx.exit(1)
    finally:
        session.close()


@library.command()
@click.argument('query')
@click.option('--fuzzy/--no-fuzzy', default=True, help='Enable fuzzy matching')
@click.option('--limit', default=20, help='Maximum results')
@click.pass_context
def search(ctx, query, fuzzy, limit):
    """Search for games."""
    session = get_session()
    search_engine = GameSearch(session)

    try:
        results = search_engine.search(query, fuzzy=fuzzy, limit=limit)

        if output_json(ctx, [{'game': format_game(g), 'score': s} for g, s in results]):
            return

        click.echo(f"Found {len(results)} games matching '{query}':")
        for game, score in results:
            click.echo(f"  [{game.id}] {game.name} (score: {score:.2f})")

    except Exception as e:
        click.echo(f"Error searching games: {e}", err=True)
        ctx.exit(1)
    finally:
        session.close()


@library.command()
@click.option('--platform', multiple=True, help='Filter by platform')
@click.option('--genre', multiple=True, help='Filter by genre')
@click.option('--tag', multiple=True, help='Filter by tag')
@click.option('--category', multiple=True, help='Filter by category')
@click.option('--favorite', is_flag=True, help='Show only favorites')
@click.option('--installed', is_flag=True, help='Show only installed games')
@click.option('--playtime-min', type=int, help='Minimum playtime (minutes)')
@click.option('--release-year-min', type=int, help='Minimum release year')
@click.option('--release-year-max', type=int, help='Maximum release year')
@click.option('--limit', default=50, help='Maximum results')
@click.pass_context
def filter(ctx, platform, genre, tag, category, favorite, installed,
           playtime_min, release_year_min, release_year_max, limit):
    """Filter games by various criteria."""
    session = get_session()
    game_filter = GameFilter(session)

    try:
        filter_config = {}

        if platform:
            filter_config['platforms'] = [*platform]
        if genre:
            filter_config['genres'] = [*genre]
        if tag:
            filter_config['tags'] = [*tag]
        if category:
            filter_config['categories'] = [*category]
        if favorite:
            filter_config['is_favorite'] = True
        if installed:
            filter_config['is_installed'] = True
        if playtime_min:
            filter_config['playtime_min'] = playtime_min
        if release_year_min:
            filter_config['release_year_min'] = release_year_min
        if release_year_max:
            filter_config['release_year_max'] = release_year_max

        games = game_filter.filter_games(filter_config, limit=limit)

        if output_json(ctx, [format_game(g) for g in games]):
            return

        click.echo(f"Found {len(games)} games matching filters:")
        for game in games:
            click.echo(f"  [{game.id}] {game.name}")

    except Exception as e:
        click.echo(f"Error filtering games: {e}", err=True)
        ctx.exit(1)
    finally:
        session.close()


@library.command()
@click.argument('game_id', type=int)
@click.pass_context
def delete(ctx, game_id):
    """Delete a game from the library."""
    session = get_session()
    ops = GameOperations(session)

    try:
        game = ops.get_game(game_id)
        if not game:
            click.echo(f"Game with ID {game_id} not found", err=True)
            ctx.exit(1)

        if click.confirm(f"Delete '{game.name}'?"):
            ops.delete_game(game_id)
            click.echo(f"Deleted game: {game.name}")

    except Exception as e:
        click.echo(f"Error deleting game: {e}", err=True)
        ctx.exit(1)
    finally:
        session.close()


@library.command()
@click.argument('game_ids', type=int, nargs=-1, required=True)
@click.option('--tag', 'tags', multiple=True, help='Tags to add')
@click.option('--category', 'categories', multiple=True, help='Categories to add')
@click.option('--favorite', is_flag=True, help='Mark as favorite')
@click.option('--hide', is_flag=True, help='Hide games')
@click.pass_context
def bulk_edit(ctx, game_ids, tags, categories, favorite, hide):
    """Edit multiple games at once."""
    session = get_session()
    bulk_ops = BulkOperations(session)

    try:
        count = 0

        if tags:
            count = bulk_ops.bulk_add_tags([*game_ids], [*tags])
            click.echo(f"Added tags to {count} games")

        if categories:
            count = bulk_ops.bulk_add_categories([*game_ids], [*categories])
            click.echo(f"Added categories to {count} games")

        if favorite:
            count = bulk_ops.bulk_set_favorite([*game_ids], True)
            click.echo(f"Marked {count} games as favorite")

        if hide:
            count = bulk_ops.bulk_set_hidden([*game_ids], True)
            click.echo(f"Hidden {count} games")

    except Exception as e:
        click.echo(f"Error in bulk edit: {e}", err=True)
        ctx.exit(1)
    finally:
        session.close()


@library.command()
@click.argument('name')
@click.option('--platform', multiple=True, help='Filter by platform')
@click.option('--genre', multiple=True, help='Filter by genre')
@click.option('--tag', multiple=True, help='Filter by tag')
@click.option('--playtime-min', type=int, help='Minimum playtime')
@click.pass_context
def create_smart_collection(ctx, name, platform, genre, tag, playtime_min):
    """Create a smart collection with auto-update rules."""
    session = get_session()
    manager = SmartCollectionManager(session)

    try:
        rules = {}
        if platform:
            rules['platforms'] = [*platform]
        if genre:
            rules['genres'] = [*genre]
        if tag:
            rules['tags'] = [*tag]
        if playtime_min:
            rules['playtime_min'] = playtime_min

        collection = manager.create_smart_collection(name, rules)
        game_count = len(collection.games)

        if output_json(ctx, {'name': name, 'game_count': game_count, 'rules': rules}):
            return

        click.echo(f"Created smart collection '{name}' with {game_count} games")

    except Exception as e:
        click.echo(f"Error creating smart collection: {e}", err=True)
        ctx.exit(1)
    finally:
        session.close()


@library.command()
@click.pass_context
def stats(ctx):
    """Show library statistics."""
    session = get_session()
    lib_ops = LibraryOperations(session)
    ops = GameOperations(session)

    try:
        games = ops.get_all_games()
        platforms = lib_ops.get_all_platforms()
        genres = lib_ops.get_all_genres()
        tags = lib_ops.get_all_tags()

        favorites = sum(1 for g in games if g.is_favorite)
        total_playtime = sum(g.playtime for g in games if g.playtime)

        stats_data = {
            'total_games': len(games),
            'platforms': len(platforms),
            'genres': len(genres),
            'tags': len(tags),
            'favorites': favorites,
            'total_playtime_hours': round(total_playtime / 60, 2)
        }

        if output_json(ctx, stats_data):
            return

        click.echo("\nLibrary Statistics:")
        click.echo(f"  Total Games: {stats_data['total_games']}")
        click.echo(f"  Platforms: {stats_data['platforms']}")
        click.echo(f"  Genres: {stats_data['genres']}")
        click.echo(f"  Tags: {stats_data['tags']}")
        click.echo(f"  Favorites: {stats_data['favorites']}")
        click.echo(f"  Total Playtime: {stats_data['total_playtime_hours']} hours")

    except Exception as e:
        click.echo(f"Error getting stats: {e}", err=True)
        ctx.exit(1)
    finally:
        session.close()


@library.command()
@click.argument('game_id', type=int)
@click.option('--name', help='New game name')
@click.option('--playtime', type=int, help='Playtime in minutes')
@click.option('--release-date', help='Release date (YYYY-MM-DD)')
@click.option('--user-score', type=int, help='User score (0-100)')
@click.option('--favorite/--no-favorite', default=None, help='Set favorite status')
@click.option('--hidden/--no-hidden', default=None, help='Set hidden status')
@click.pass_context
def update_game(ctx, game_id, name, playtime, release_date, user_score, favorite, hidden):
    """Update game fields."""
    session = get_session()
    ops = GameOperations(session)

    try:
        game = ops.get_game(game_id)
        if not game:
            click.echo(f"Game with ID {game_id} not found", err=True)
            ctx.exit(1)

        # Build updates dictionary
        updates = {}
        if name is not None:
            updates['name'] = name
        if playtime is not None:
            updates['playtime'] = playtime
        if release_date is not None:
            from datetime import date
            updates['release_date'] = date.fromisoformat(release_date)
        if user_score is not None:
            updates['user_score'] = user_score
        if favorite is not None:
            updates['is_favorite'] = favorite
        if hidden is not None:
            updates['is_hidden'] = hidden

        if not updates:
            click.echo("No updates specified", err=True)
            ctx.exit(1)

        ops.update_game(game_id, **updates)

        if output_json(ctx, {'id': game_id, 'updated': True}):
            return

        click.echo(f"Updated game: {game.name} (ID: {game_id})")

    except Exception as e:
        click.echo(f"Error updating game: {e}", err=True)
        ctx.exit(1)
    finally:
        session.close()


@library.command()
@click.argument('old_name')
@click.argument('new_name')
@click.pass_context
def rename_tag(ctx, old_name, new_name):
    """Rename a tag."""
    session = get_session()
    lib_ops = LibraryOperations(session)

    try:
        # Check if old tag exists
        old_tag = lib_ops.get_tag_by_name(old_name)
        if not old_tag:
            click.echo(f"Tag '{old_name}' not found", err=True)
            ctx.exit(1)

        # Check if new tag name already exists
        existing = lib_ops.get_tag_by_name(new_name)
        if existing:
            click.echo(f"Tag '{new_name}' already exists", err=True)
            ctx.exit(1)

        # Update tag name
        old_tag.name = new_name
        session.commit()

        if output_json(ctx, {'old_name': old_name, 'new_name': new_name}):
            return

        click.echo(f"Renamed tag: '{old_name}' -> '{new_name}'")

    except Exception as e:
        click.echo(f"Error renaming tag: {e}", err=True)
        ctx.exit(1)
    finally:
        session.close()


@library.command()
@click.argument('old_name')
@click.argument('new_name')
@click.pass_context
def rename_category(ctx, old_name, new_name):
    """Rename a category."""
    session = get_session()
    lib_ops = LibraryOperations(session)

    try:
        # Check if old category exists
        old_category = lib_ops.get_category_by_name(old_name)
        if not old_category:
            click.echo(f"Category '{old_name}' not found", err=True)
            ctx.exit(1)

        # Check if new category name already exists
        existing = lib_ops.get_category_by_name(new_name)
        if existing:
            click.echo(f"Category '{new_name}' already exists", err=True)
            ctx.exit(1)

        # Update category name
        old_category.name = new_name
        session.commit()

        if output_json(ctx, {'old_name': old_name, 'new_name': new_name}):
            return

        click.echo(f"Renamed category: '{old_name}' -> '{new_name}'")

    except Exception as e:
        click.echo(f"Error renaming category: {e}", err=True)
        ctx.exit(1)
    finally:
        session.close()


@library.command()
@click.argument('collection_id', type=int)
@click.option('--name', help='New collection name')
@click.option('--description', help='New description')
@click.pass_context
def update_collection(ctx, collection_id, name, description):
    """Update collection metadata."""
    session = get_session()
    lib_ops = LibraryOperations(session)

    try:
        collection = lib_ops.get_collection(collection_id)
        if not collection:
            click.echo(f"Collection with ID {collection_id} not found", err=True)
            ctx.exit(1)

        # Build updates
        updates = {}
        if name is not None:
            updates['name'] = name
        if description is not None:
            updates['description'] = description

        if not updates:
            click.echo("No updates specified", err=True)
            ctx.exit(1)

        # Update collection
        for key, value in updates.items():
            setattr(collection, key, value)
        session.commit()

        if output_json(ctx, {'id': collection_id, 'updated': True}):
            return

        click.echo(f"Updated collection: {collection.name} (ID: {collection_id})")

    except Exception as e:
        click.echo(f"Error updating collection: {e}", err=True)
        ctx.exit(1)
    finally:
        session.close()


@library.command()
@click.argument('collection_id', type=int)
@click.option('--platform', multiple=True, help='Platform filter')
@click.option('--genre', multiple=True, help='Genre filter')
@click.option('--tag', multiple=True, help='Tag filter')
@click.option('--favorite/--no-favorite', default=None, help='Filter favorites')
@click.option('--playtime-min', type=int, help='Minimum playtime')
@click.pass_context
def update_smart_collection_rules(ctx, collection_id, platform, genre, tag, favorite, playtime_min):
    """Update smart collection filter rules."""
    session = get_session()
    lib_ops = LibraryOperations(session)
    smart_manager = SmartCollectionManager(session)

    try:
        collection = lib_ops.get_collection(collection_id)
        if not collection:
            click.echo(f"Collection with ID {collection_id} not found", err=True)
            ctx.exit(1)

        if not collection.is_smart:
            click.echo(f"Collection '{collection.name}' is not a smart collection", err=True)
            ctx.exit(1)

        # Build new rules
        rules = {}
        if platform:
            rules['platforms'] = [*platform]
        if genre:
            rules['genres'] = [*genre]
        if tag:
            rules['tags'] = [*tag]
        if favorite is not None:
            rules['is_favorite'] = favorite
        if playtime_min is not None:
            rules['playtime_min'] = playtime_min

        if not rules:
            click.echo("No rules specified", err=True)
            ctx.exit(1)

        # Update rules
        count = smart_manager.modify_smart_collection_rules(collection_id, rules)

        if output_json(ctx, {'id': collection_id, 'game_count': count}):
            return

        click.echo(f"Updated smart collection: {collection.name}")
        click.echo(f"  Matching games: {count}")

    except Exception as e:
        click.echo(f"Error updating smart collection: {e}", err=True)
        ctx.exit(1)
    finally:
        session.close()
