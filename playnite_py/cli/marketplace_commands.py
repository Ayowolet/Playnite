"""CLI handlers for script marketplace operations."""

from __future__ import annotations

import argparse
import os

from playnite_py.cli._util import _output


def cmd_marketplace_search(args: argparse.Namespace) -> None:
    """Search the script marketplace for available extensions."""
    from playnite_py.scripting.marketplace import ScriptMarketplace
    data_dir = args.data_dir
    ext_dir = os.path.join(data_dir, "extensions")
    mp = ScriptMarketplace(ext_dir, repo_url=args.repo_url or "")
    if args.refresh:
        result = mp.refresh_index()
        if not result["success"]:
            _output(result, args.json)
            return
    results = mp.search(query=args.query or "")
    _output(results, args.json)


def cmd_marketplace_install(args: argparse.Namespace) -> None:
    """Install a script from the marketplace by ID."""
    from playnite_py.scripting.marketplace import ScriptMarketplace
    data_dir = args.data_dir
    ext_dir = os.path.join(data_dir, "extensions")
    mp = ScriptMarketplace(ext_dir, repo_url=args.repo_url or "")
    result = mp.install_script(args.id)
    _output(result, args.json)
