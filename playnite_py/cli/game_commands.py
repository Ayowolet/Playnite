"""CLI handlers for game library operations."""

from __future__ import annotations

import argparse

from playnite_py.cli._util import _build_app, _output


def cmd_db_stats(args: argparse.Namespace) -> None:
    """Display database statistics (total games, playtime, etc.)."""
    db, _, _ = _build_app(args.data_dir)
    _output(db.get_stats(), args.json)


def cmd_game_list(args: argparse.Namespace) -> None:
    """List all games in the library."""
    db, _, _ = _build_app(args.data_dir)
    games = db.get_all_games()
    if args.json:
        _output([g.to_dict() for g in games], True)
    else:
        if not games:
            print("No games in library.")
            return
        for g in games:
            status = "installed" if g.is_installed else "not installed"
            print(f"  [{g.id[:8]}] {g.name} ({status})")


def cmd_game_add(args: argparse.Namespace) -> None:
    """Add a new game to the library."""
    from playnite_py.models.game import Game
    db, _, _ = _build_app(args.data_dir)
    game = Game(
        name=args.name,
        source=args.source or "",
        is_installed=args.installed,
    )
    db.add_game(game)
    db.save()
    _output({"id": game.id, "name": game.name, "message": "Game added"}, args.json)


def cmd_game_show(args: argparse.Namespace) -> None:
    """Show detailed information about a game."""
    db, _, _ = _build_app(args.data_dir)
    game = db.get_game(args.id)
    if not game:
        # Try partial ID match
        for g in db.get_all_games():
            if g.id.startswith(args.id):
                game = g
                break
    if game:
        _output(game.to_dict(), args.json)
    else:
        _output({"error": f"Game '{args.id}' not found"}, args.json)


def cmd_game_remove(args: argparse.Namespace) -> None:
    """Remove a game from the library."""
    db, _, _ = _build_app(args.data_dir)
    if db.remove_game(args.id):
        db.save()
        _output({"message": f"Game '{args.id}' removed"}, args.json)
    else:
        _output({"error": f"Game '{args.id}' not found"}, args.json)


def cmd_game_update(args: argparse.Namespace) -> None:
    """Update fields on an existing game."""
    db, _, _ = _build_app(args.data_dir)
    game = db.get_game(args.id)
    if not game:
        _output({"error": f"Game '{args.id}' not found"}, args.json)
        return
    if args.name:
        game.name = args.name
    if args.set_installed is not None:
        game.is_installed = args.set_installed
    if args.notes:
        game.notes = args.notes
    db.update_game(game)
    db.save()
    _output({"message": f"Game '{game.name}' updated", "id": game.id}, args.json)
