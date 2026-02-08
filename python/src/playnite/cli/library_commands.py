"""Library management CLI commands."""
from __future__ import annotations

import json
import sys

import click

from ..library.organisation import LibraryManager, NotFoundError
from ..library.filters import FilterSpec

# Consistent exit codes for scripting
_EXIT_NOT_FOUND = 1
_EXIT_INVALID = 2
_EXIT_USAGE = 64


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _output(data, as_json: bool) -> None:
    """Print *data* as JSON or as human-readable text."""
    if as_json:
        click.echo(json.dumps(data, indent=2, default=str))
        return
    if isinstance(data, list):
        if not data:
            click.echo("  (none)")
            return
        for item in data:
            _print_item(item)
    elif isinstance(data, dict):
        _print_item(data)
    else:
        click.echo(str(data))


def _print_item(item: dict) -> None:
    if "name" in item:
        click.echo(f"  [{item.get('id', '?')[:8]}] {item['name']}")
    else:
        for k, v in item.items():
            click.echo(f"  {k}: {v}")


def _manager(ctx: click.Context) -> LibraryManager:
    return LibraryManager(ctx.obj["db_url"])


# ---------------------------------------------------------------------------
# Root group
# ---------------------------------------------------------------------------


@click.group()
def library() -> None:
    """Library management commands."""


# ===========================================================================
# Games
# ===========================================================================


@library.group()
def games() -> None:
    """Game CRUD and bulk operations."""


@games.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
@click.option("--sort", default="name", show_default=True, help="Sort field")
@click.option("--order", default="asc", show_default=True, type=click.Choice(["asc", "desc"]))
@click.option("--group", default=None, help="Group by field")
@click.option("--show-hidden", is_flag=True, help="Include hidden games")
@click.option("--platform", multiple=True, help="Filter by platform (repeatable)")
@click.option("--genre", multiple=True, help="Filter by genre (repeatable)")
@click.option("--tag", multiple=True, help="Filter by tag (repeatable)")
@click.option("--status", multiple=True, help="Completion status (repeatable)")
@click.option("--favorite", is_flag=True, default=False, help="Only favourites")
@click.option("--min-playtime", type=int, default=None, help="Minimum playtime in hours")
@click.option("--max-playtime", type=int, default=None, help="Maximum playtime in hours")
@click.option("--min-year", type=int, default=None, help="Minimum release year")
@click.option("--max-year", type=int, default=None, help="Maximum release year")
@click.option("--developer", default=None, help="Filter by developer (partial match)")
@click.option("--publisher", default=None, help="Filter by publisher (partial match)")
@click.option("--preset", default=None, help="Apply a saved view preset")
@click.option("--limit", type=int, default=None, help="Maximum results to return")
@click.option("--offset", type=int, default=0, show_default=True, help="Results to skip (for pagination)")
@click.pass_context
def games_list(
    ctx, as_json, sort, order, group, show_hidden, platform, genre, tag, status,
    favorite, min_playtime, max_playtime, min_year, max_year, developer, publisher,
    preset, limit, offset
) -> None:
    """List games in the library."""
    mgr = _manager(ctx)
    if preset:
        try:
            result = mgr.list_games_with_preset(preset)
        except NotFoundError as exc:
            click.echo(f"Error: {exc}", err=True)
            sys.exit(_EXIT_NOT_FOUND)
        _output(result, as_json)
        return
    spec = FilterSpec(
        platforms=list(platform) or None,
        genres=list(genre) or None,
        tags=list(tag) or None,
        completion_statuses=list(status) or None,
        is_favorite=True if favorite else None,
        is_hidden=None if show_hidden else False,
        playtime_min=min_playtime * 3600 if min_playtime is not None else None,
        playtime_max=max_playtime * 3600 if max_playtime is not None else None,
        release_year_min=min_year,
        release_year_max=max_year,
        developer=developer or None,
        publisher=publisher or None,
    )
    try:
        result = mgr.list_games(
            sort_by=sort, sort_order=order, group_by=group,
            include_hidden=show_hidden, filter_spec=spec,
            limit=limit, offset=offset,
        )
    except ValueError as exc:
        click.echo(f"Invalid argument: {exc}", err=True)
        sys.exit(_EXIT_INVALID)
    _output(result, as_json)


@games.command("add")
@click.option("--name", required=True, help="Game title")
@click.option("--platform", multiple=True)
@click.option("--genre", multiple=True)
@click.option("--tag", multiple=True)
@click.option("--category", multiple=True)
@click.option("--developer", default=None)
@click.option("--publisher", default=None)
@click.option("--year", type=int, default=None, help="Release year")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def games_add(ctx, name, platform, genre, tag, category, developer, publisher, year, as_json) -> None:
    """Add a game to the library."""
    try:
        result = _manager(ctx).add_game(
            name=name,
            developer=developer,
            publisher=publisher,
            release_year=year,
            platforms=list(platform) or None,
            genres=list(genre) or None,
            tags=list(tag) or None,
            categories=list(category) or None,
        )
    except ValueError as exc:
        click.echo(f"Invalid argument: {exc}", err=True)
        sys.exit(_EXIT_INVALID)
    _output(result, as_json)


@games.command("get")
@click.argument("game_id")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def games_get(ctx, game_id, as_json) -> None:
    """Get full details of a game."""
    try:
        _output(_manager(ctx).get_game(game_id), as_json)
    except NotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(_EXIT_NOT_FOUND)


@games.command("update")
@click.argument("game_id")
@click.option("--name")
@click.option("--developer")
@click.option("--publisher")
@click.option("--year", type=int)
@click.option("--status")
@click.option("--score", type=int)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def games_update(ctx, game_id, name, developer, publisher, year, status, score, as_json) -> None:
    """Update game metadata."""
    kwargs = {}
    if name is not None:
        kwargs["name"] = name
    if developer is not None:
        kwargs["developer"] = developer
    if publisher is not None:
        kwargs["publisher"] = publisher
    if year is not None:
        kwargs["release_year"] = year
    if status is not None:
        kwargs["completion_status"] = status
    if score is not None:
        kwargs["user_score"] = score
    try:
        _output(_manager(ctx).update_game(game_id, **kwargs), as_json)
    except NotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(_EXIT_NOT_FOUND)


@games.command("delete")
@click.argument("game_id")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def games_delete(ctx, game_id, as_json) -> None:
    """Delete a game permanently."""
    try:
        _manager(ctx).delete_game(game_id)
        _output({"ok": True, "id": game_id}, as_json) if as_json else click.echo(f"Deleted {game_id}")
    except NotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(_EXIT_NOT_FOUND)


@games.command("search")
@click.argument("query")
@click.option("--json", "as_json", is_flag=True)
@click.option("--threshold", type=int, default=60, show_default=True)
@click.option("--no-fuzzy", is_flag=True)
@click.pass_context
def games_search(ctx, query, as_json, threshold, no_fuzzy) -> None:
    """Search games by title, developer, or tags."""
    results = _manager(ctx).search(query, fuzzy=not no_fuzzy, threshold=threshold)
    _output(results, as_json)


@games.command("favorite")
@click.argument("game_id")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def games_favorite(ctx, game_id, as_json) -> None:
    """Pin a game as favourite."""
    _output(_manager(ctx).pin_game(game_id), as_json)


@games.command("unfavorite")
@click.argument("game_id")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def games_unfavorite(ctx, game_id, as_json) -> None:
    """Remove a game from favourites."""
    _output(_manager(ctx).unpin_game(game_id), as_json)


@games.command("hide")
@click.argument("game_id")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def games_hide(ctx, game_id, as_json) -> None:
    """Hide a game from the library view."""
    result = _manager(ctx).hide_game(game_id)
    _output(result, as_json) if as_json else click.echo(f"Hidden {game_id}")


@games.command("unhide")
@click.argument("game_id")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def games_unhide(ctx, game_id, as_json) -> None:
    """Unhide a game."""
    result = _manager(ctx).unhide_game(game_id)
    _output(result, as_json) if as_json else click.echo(f"Unhidden {game_id}")


@games.command("apply-tag")
@click.argument("game_id")
@click.option("--tag", "tag_name", required=True)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def games_apply_tag(ctx, game_id, tag_name, as_json) -> None:
    """Apply a tag to a single game."""
    try:
        _output(_manager(ctx).apply_tag(game_id, tag_name), as_json)
    except NotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(_EXIT_NOT_FOUND)


@games.command("remove-tag")
@click.argument("game_id")
@click.option("--tag", "tag_name", required=True)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def games_remove_tag(ctx, game_id, tag_name, as_json) -> None:
    """Remove a tag from a single game."""
    try:
        _output(_manager(ctx).remove_tag(game_id, tag_name), as_json)
    except NotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(_EXIT_NOT_FOUND)


@games.command("bulk-tag")
@click.argument("game_ids", nargs=-1, required=True)
@click.option("--tag", "tag_name", required=True)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def games_bulk_tag(ctx, game_ids, tag_name, as_json) -> None:
    """Apply a tag to multiple games."""
    if not game_ids:
        click.echo("Warning: no game IDs provided", err=True)
        sys.exit(_EXIT_USAGE)
    results = _manager(ctx).bulk_tag(list(game_ids), tag_name)
    _output({"updated": len(results), "tag": tag_name}, as_json)


@games.command("bulk-categorize")
@click.argument("game_ids", nargs=-1, required=True)
@click.option("--category", "cat_name", required=True)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def games_bulk_categorize(ctx, game_ids, cat_name, as_json) -> None:
    """Apply a category to multiple games."""
    results = _manager(ctx).bulk_categorize(list(game_ids), cat_name)
    _output({"updated": len(results), "category": cat_name}, as_json)


@games.command("bulk-update")
@click.argument("game_ids", nargs=-1, required=True)
@click.option("--status", default=None)
@click.option("--score", type=int, default=None)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def games_bulk_update(ctx, game_ids, status, score, as_json) -> None:
    """Update fields on multiple games at once."""
    kwargs = {}
    if status is not None:
        kwargs["completion_status"] = status
    if score is not None:
        kwargs["user_score"] = score
    results = _manager(ctx).bulk_update(list(game_ids), **kwargs)
    _output({"updated": len(results)}, as_json)


@games.command("bulk-delete")
@click.argument("game_ids", nargs=-1, required=True)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def games_bulk_delete(ctx, game_ids, as_json) -> None:
    """Delete multiple games at once."""
    count = _manager(ctx).bulk_delete(list(game_ids))
    _output({"deleted": count}, as_json)


@games.command("bulk-hide")
@click.argument("game_ids", nargs=-1, required=True)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def games_bulk_hide(ctx, game_ids, as_json) -> None:
    """Hide multiple games at once."""
    results = _manager(ctx).bulk_hide(list(game_ids))
    _output({"hidden": len(results)}, as_json)


@games.command("bulk-unhide")
@click.argument("game_ids", nargs=-1, required=True)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def games_bulk_unhide(ctx, game_ids, as_json) -> None:
    """Unhide multiple games at once."""
    results = _manager(ctx).bulk_unhide(list(game_ids))
    _output({"unhidden": len(results)}, as_json)


# ===========================================================================
# Tags
# ===========================================================================


@library.group()
def tags() -> None:
    """Tag management."""


@tags.command("list")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def tags_list(ctx, as_json) -> None:
    """List all tags."""
    _output(_manager(ctx).list_tags(), as_json)


@tags.command("get")
@click.argument("tag_id")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def tags_get(ctx, tag_id, as_json) -> None:
    """Get a tag by ID."""
    try:
        _output(_manager(ctx).get_tag(tag_id), as_json)
    except NotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(_EXIT_NOT_FOUND)


@tags.command("add")
@click.argument("name")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def tags_add(ctx, name, as_json) -> None:
    """Create a tag."""
    _output(_manager(ctx).add_tag(name), as_json)


@tags.command("update")
@click.argument("tag_id")
@click.option("--name", required=True)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def tags_update(ctx, tag_id, name, as_json) -> None:
    """Rename a tag."""
    try:
        _output(_manager(ctx).update_tag(tag_id, name), as_json)
    except NotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(_EXIT_NOT_FOUND)


@tags.command("delete")
@click.argument("tag_id")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def tags_delete(ctx, tag_id, as_json) -> None:
    """Delete a tag."""
    try:
        _manager(ctx).delete_tag(tag_id)
        _output({"ok": True, "id": tag_id}, as_json) if as_json else click.echo(f"Deleted tag {tag_id}")
    except NotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(_EXIT_NOT_FOUND)


# ===========================================================================
# Categories
# ===========================================================================


@library.group()
def categories() -> None:
    """Category management."""


@categories.command("list")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def cats_list(ctx, as_json) -> None:
    """List all categories."""
    _output(_manager(ctx).list_categories(), as_json)


@categories.command("get")
@click.argument("category_id")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def cats_get(ctx, category_id, as_json) -> None:
    """Get a category by ID."""
    try:
        _output(_manager(ctx).get_category(category_id), as_json)
    except NotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(_EXIT_NOT_FOUND)


@categories.command("add")
@click.argument("name")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def cats_add(ctx, name, as_json) -> None:
    """Create a category."""
    _output(_manager(ctx).add_category(name), as_json)


@categories.command("update")
@click.argument("category_id")
@click.option("--name", required=True)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def cats_update(ctx, category_id, name, as_json) -> None:
    """Rename a category."""
    try:
        _output(_manager(ctx).update_category(category_id, name), as_json)
    except NotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(_EXIT_NOT_FOUND)


@categories.command("delete")
@click.argument("category_id")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def cats_delete(ctx, category_id, as_json) -> None:
    """Delete a category."""
    try:
        _manager(ctx).delete_category(category_id)
        _output({"ok": True, "id": category_id}, as_json) if as_json else click.echo(f"Deleted category {category_id}")
    except NotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(_EXIT_NOT_FOUND)


# ===========================================================================
# Genres (read-only — auto-created via game operations)
# ===========================================================================


@library.group()
def genres() -> None:
    """Genre listing (read-only; genres are created via game operations)."""


@genres.command("list")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def genres_list(ctx, as_json) -> None:
    """List all genres."""
    _output(_manager(ctx).list_genres(), as_json)


# ===========================================================================
# Platforms (read-only — auto-created via game operations)
# ===========================================================================


@library.group()
def platforms() -> None:
    """Platform listing (read-only; platforms are created via game operations)."""


@platforms.command("list")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def platforms_list(ctx, as_json) -> None:
    """List all platforms."""
    _output(_manager(ctx).list_platforms(), as_json)


# ===========================================================================
# Smart Collections
# ===========================================================================


@library.group()
def collections() -> None:
    """Smart collection management."""


@collections.command("list")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def cols_list(ctx, as_json) -> None:
    """List smart collections."""
    _output(_manager(ctx).list_smart_collections(), as_json)


@collections.command("create")
@click.argument("name")
@click.option("--rules", required=True, help="JSON array of rule objects")
@click.option("--logic", default="AND", type=click.Choice(["AND", "OR"]))
@click.option("--description", default=None)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def cols_create(ctx, name, rules, logic, description, as_json) -> None:
    """Create a smart collection with filter rules."""
    try:
        rules_data = json.loads(rules)
    except json.JSONDecodeError as exc:
        click.echo(f"Invalid JSON for --rules: {exc}", err=True)
        sys.exit(_EXIT_INVALID)
    _output(_manager(ctx).create_smart_collection(name, rules_data, logic, description), as_json)


@collections.command("update")
@click.argument("collection_id")
@click.option("--name")
@click.option("--rules", help="JSON array of rule objects")
@click.option("--logic", type=click.Choice(["AND", "OR"]))
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def cols_update(ctx, collection_id, name, rules, logic, as_json) -> None:
    """Update a smart collection."""
    kwargs = {}
    if name is not None:
        kwargs["name"] = name
    if rules is not None:
        try:
            kwargs["rules"] = json.loads(rules)
        except json.JSONDecodeError as exc:
            click.echo(f"Invalid JSON for --rules: {exc}", err=True)
            sys.exit(_EXIT_INVALID)
    if logic is not None:
        kwargs["logic"] = logic
    try:
        _output(_manager(ctx).update_smart_collection(collection_id, **kwargs), as_json)
    except NotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(_EXIT_NOT_FOUND)


@collections.command("games")
@click.argument("collection_id")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def cols_games(ctx, collection_id, as_json) -> None:
    """List games matching a smart collection."""
    try:
        _output(_manager(ctx).get_smart_collection_games(collection_id), as_json)
    except NotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(_EXIT_NOT_FOUND)


@collections.command("delete")
@click.argument("collection_id")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def cols_delete(ctx, collection_id, as_json) -> None:
    try:
        _manager(ctx).delete_smart_collection(collection_id)
        _output({"ok": True, "id": collection_id}, as_json) if as_json else click.echo(f"Deleted collection {collection_id}")
    except NotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(_EXIT_NOT_FOUND)


# ===========================================================================
# View Presets
# ===========================================================================


@library.group()
def presets() -> None:
    """View preset management."""


@presets.command("list")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def presets_list(ctx, as_json) -> None:
    """List all saved view presets."""
    _output(_manager(ctx).list_view_presets(), as_json)


@presets.command("save")
@click.argument("name")
@click.option("--sort", default="name", show_default=True)
@click.option("--order", default="asc", type=click.Choice(["asc", "desc"]))
@click.option("--group", default=None)
@click.option("--view", default="list", type=click.Choice(["list", "grid"]))
@click.option("--filters", default="{}", help="JSON filter spec")
@click.option("--columns", default="[]", help="JSON list of column names")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def presets_save(ctx, name, sort, order, group, view, filters, columns, as_json) -> None:
    """Save a view preset."""
    try:
        filter_data = json.loads(filters)
        col_data = json.loads(columns)
    except json.JSONDecodeError as exc:
        click.echo(f"Invalid JSON: {exc}", err=True)
        sys.exit(_EXIT_INVALID)
    result = _manager(ctx).save_view_preset(
        name, sort_by=sort, sort_order=order, group_by=group,
        view_type=view, filters=filter_data, columns=col_data,
    )
    _output(result, as_json)


@presets.command("load")
@click.argument("name")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def presets_load(ctx, name, as_json) -> None:
    """Load a saved view preset."""
    try:
        _output(_manager(ctx).load_view_preset(name), as_json)
    except NotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(_EXIT_NOT_FOUND)


@presets.command("delete")
@click.argument("name")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def presets_delete(ctx, name, as_json) -> None:
    try:
        _manager(ctx).delete_view_preset(name)
        _output({"ok": True, "name": name}, as_json) if as_json else click.echo(f"Deleted preset '{name}'")
    except NotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(_EXIT_NOT_FOUND)


# ===========================================================================
# Stats
# ===========================================================================


@library.command("stats")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def library_stats(ctx, as_json) -> None:
    """Show library statistics."""
    _output(_manager(ctx).get_stats(), as_json)
