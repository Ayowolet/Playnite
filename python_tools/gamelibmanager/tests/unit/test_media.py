"""Tests for MediaHandler."""

import os

import pytest
from gamelibmanager.merger.media import MediaHandler
from gamelibmanager.models.game import Game


class TestMediaHandler:
    def _setup_libs(self, tmp_path):
        source = tmp_path / "source"
        target = tmp_path / "target"
        (source / "files").mkdir(parents=True)
        (target / "files").mkdir(parents=True)
        return source, target

    def test_copy_media_files(self, tmp_path):
        source, target = self._setup_libs(tmp_path)
        (source / "files" / "cover.jpg").write_bytes(b"cover data")
        (source / "files" / "bg.png").write_bytes(b"bg data")

        src_game = Game(name="Game", cover_image="cover.jpg", background_image="bg.png")
        tgt_game = Game(name="Game")

        handler = MediaHandler(source, target)
        copied = handler.copy_media(src_game, tgt_game)

        assert copied == 2
        assert (target / "files" / "cover.jpg").exists()
        assert (target / "files" / "bg.png").exists()

    def test_skip_identical_files(self, tmp_path):
        source, target = self._setup_libs(tmp_path)
        (source / "files" / "cover.jpg").write_bytes(b"same data")
        (target / "files" / "cover.jpg").write_bytes(b"same data")

        src_game = Game(name="Game", cover_image="cover.jpg")
        tgt_game = Game(name="Game")

        handler = MediaHandler(source, target)
        copied = handler.copy_media(src_game, tgt_game)
        assert copied == 0

    def test_skip_http_urls(self, tmp_path):
        source, target = self._setup_libs(tmp_path)
        src_game = Game(name="Game", cover_image="https://example.com/cover.jpg")
        tgt_game = Game(name="Game")

        handler = MediaHandler(source, target)
        copied = handler.copy_media(src_game, tgt_game)
        assert copied == 0

    def test_skip_missing_source_file(self, tmp_path):
        source, target = self._setup_libs(tmp_path)
        src_game = Game(name="Game", cover_image="nonexistent.jpg")
        tgt_game = Game(name="Game")

        handler = MediaHandler(source, target)
        copied = handler.copy_media(src_game, tgt_game)
        assert copied == 0

    def test_count_media_to_copy(self, tmp_path):
        source, target = self._setup_libs(tmp_path)
        (source / "files" / "icon.png").write_bytes(b"icon")
        (source / "files" / "cover.jpg").write_bytes(b"cover")

        game = Game(name="Game", icon="icon.png", cover_image="cover.jpg")
        handler = MediaHandler(source, target)
        assert handler.count_media_to_copy(game) == 2

    def test_skip_http_urls_case_insensitive(self, tmp_path):
        """HTTP/HTTPS check should be case-insensitive."""
        source, target = self._setup_libs(tmp_path)
        src_game = Game(name="Game", cover_image="HTTPS://example.com/cover.jpg")
        tgt_game = Game(name="Game")

        handler = MediaHandler(source, target)
        copied = handler.copy_media(src_game, tgt_game)
        assert copied == 0

    def test_self_copy_skipped(self, tmp_path):
        """When source and target point to the same directory, no copy occurs."""
        lib = tmp_path / "lib"
        (lib / "files").mkdir(parents=True)
        (lib / "files" / "cover.jpg").write_bytes(b"data")

        src_game = Game(name="Game", cover_image="cover.jpg")
        tgt_game = Game(name="Game")

        handler = MediaHandler(lib, lib)
        copied = handler.copy_media(src_game, tgt_game)
        assert copied == 0
