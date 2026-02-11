"""Read and write native Playnite JSON library directories."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from ..models.game import Game
from ..models.game_action import GameAction, GameActionType, TrackingMode
from ..models.game_rom import GameRom
from ..models.link import Link
from ..models.lookup_tables import (
    AgeRating, Category, Company, CompletionStatus, GameFeature,
    GameSource, Genre, Platform, Region, Series,
)
from ..models.release_date import ReleaseDate

_EMPTY_UUID = uuid.UUID(int=0)


def _to_snake_case(name: str) -> str:
    """Convert PascalCase to snake_case."""
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    return s.lower()


def _to_pascal_case(name: str) -> str:
    """Convert snake_case to PascalCase."""
    return "".join(word.capitalize() for word in name.split("_"))


def _safe_uuid(val: Any) -> uuid.UUID:
    if val is None:
        return _EMPTY_UUID
    if isinstance(val, uuid.UUID):
        return val
    try:
        return uuid.UUID(str(val))
    except (ValueError, AttributeError):
        return _EMPTY_UUID


def _safe_uuid_list(val: Any) -> list[uuid.UUID] | None:
    if val is None:
        return None
    if not isinstance(val, list):
        return None
    return [_safe_uuid(v) for v in val]


def _safe_dt(val: Any) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


class PlayniteLibraryReader:
    """Reads a native Playnite library directory structure."""

    def __init__(self, library_path: str | Path):
        self.library_path = Path(library_path)

    def read_all_games(self) -> list[Game]:
        games_dir = self.library_path / "games"
        if not games_dir.exists():
            return []
        games: list[Game] = []
        for fp in games_dir.glob("*.json"):
            try:
                with open(fp, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
                games.append(self._parse_game_json(data))
            except (json.JSONDecodeError, KeyError):
                continue
        return games

    def read_all_platforms(self) -> list[Platform]:
        return self._read_lookup_dir("platforms", Platform, self._parse_platform)

    def read_all_sources(self) -> list[GameSource]:
        return self._read_lookup_dir("sources", GameSource)

    def read_all_companies(self) -> list[Company]:
        return self._read_lookup_dir("companies", Company)

    def read_all_genres(self) -> list[Genre]:
        return self._read_lookup_dir("genres", Genre)

    def read_all_categories(self) -> list[Category]:
        return self._read_lookup_dir("categories", Category)

    def read_all_tags(self) -> list[Tag]:
        from ..models.lookup_tables import Tag
        return self._read_lookup_dir("tags", Tag)

    def read_all_features(self) -> list[GameFeature]:
        return self._read_lookup_dir("features", GameFeature)

    def read_all_series(self) -> list[Series]:
        return self._read_lookup_dir("series", Series)

    def read_all_age_ratings(self) -> list[AgeRating]:
        return self._read_lookup_dir("ageratings", AgeRating)

    def read_all_regions(self) -> list[Region]:
        return self._read_lookup_dir("regions", Region)

    def read_all_completion_statuses(self) -> list[CompletionStatus]:
        return self._read_lookup_dir("completionstatuses", CompletionStatus)

    def _read_lookup_dir(self, dirname: str, cls: type, parser=None) -> list:
        d = self.library_path / dirname
        if not d.exists():
            return []
        items = []
        for fp in d.glob("*.json"):
            try:
                with open(fp, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
                if parser:
                    items.append(parser(data))
                else:
                    items.append(cls(
                        id=_safe_uuid(data.get("Id")),
                        name=data.get("Name", ""),
                    ))
            except (json.JSONDecodeError, KeyError):
                continue
        return items

    @staticmethod
    def _parse_platform(data: dict) -> Platform:
        return Platform(
            id=_safe_uuid(data.get("Id")),
            name=data.get("Name", ""),
            specification_id=data.get("SpecificationId", ""),
            icon=data.get("Icon", ""),
            cover=data.get("Cover", ""),
            background=data.get("Background", ""),
        )

    @staticmethod
    def _parse_game_json(data: dict) -> Game:
        rd_raw = data.get("ReleaseDate")
        release_date = None
        if rd_raw and isinstance(rd_raw, str):
            try:
                release_date = ReleaseDate.deserialize(rd_raw)
            except (ValueError, IndexError):
                pass
        elif rd_raw and isinstance(rd_raw, dict):
            release_date = ReleaseDate(
                year=rd_raw.get("Year", 0),
                month=rd_raw.get("Month"),
                day=rd_raw.get("Day"),
            )

        links = None
        raw_links = data.get("Links")
        if raw_links and isinstance(raw_links, list):
            links = [Link(name=lk.get("Name", ""), url=lk.get("Url", "")) for lk in raw_links]

        game_actions = None
        raw_actions = data.get("GameActions")
        if raw_actions and isinstance(raw_actions, list):
            game_actions = []
            for a in raw_actions:
                game_actions.append(GameAction(
                    type=GameActionType(a.get("Type", 0)),
                    name=a.get("Name", ""),
                    path=a.get("Path", ""),
                    working_dir=a.get("WorkingDir", ""),
                    arguments=a.get("Arguments", ""),
                    additional_arguments=a.get("AdditionalArguments", ""),
                    override_default_args=a.get("OverrideDefaultArgs", False),
                    is_play_action=a.get("IsPlayAction", False),
                    emulator_id=_safe_uuid(a.get("EmulatorId")),
                    emulator_profile_id=a.get("EmulatorProfileId", ""),
                    tracking_mode=TrackingMode(a.get("TrackingMode", 0)),
                    tracking_path=a.get("TrackingPath", ""),
                    script=a.get("Script", ""),
                    initial_tracking_delay=a.get("InitialTrackingDelay", 0),
                    tracking_frequency=a.get("TrackingFrequency", 2000),
                ))

        roms = None
        raw_roms = data.get("Roms")
        if raw_roms and isinstance(raw_roms, list):
            roms = [GameRom(name=r.get("Name", ""), path=r.get("Path", "")) for r in raw_roms]

        return Game(
            id=_safe_uuid(data.get("Id")),
            name=data.get("Name", ""),
            game_id=data.get("GameId", ""),
            plugin_id=_safe_uuid(data.get("PluginId")),
            sorting_name=data.get("SortingName"),
            description=data.get("Description", ""),
            notes=data.get("Notes", ""),
            hidden=data.get("Hidden", False),
            favorite=data.get("Favorite", False),
            is_installed=data.get("IsInstalled", False),
            is_installing=data.get("IsInstalling", False),
            is_uninstalling=data.get("IsUninstalling", False),
            is_launching=data.get("IsLaunching", False),
            is_running=data.get("IsRunning", False),
            override_install_state=data.get("OverrideInstallState", False),
            include_library_plugin_action=data.get("IncludeLibraryPluginAction", True),
            enable_system_hdr=data.get("EnableSystemHdr", False),
            platform_ids=_safe_uuid_list(data.get("PlatformIds")),
            developer_ids=_safe_uuid_list(data.get("DeveloperIds")),
            publisher_ids=_safe_uuid_list(data.get("PublisherIds")),
            genre_ids=_safe_uuid_list(data.get("GenreIds")),
            category_ids=_safe_uuid_list(data.get("CategoryIds")),
            tag_ids=_safe_uuid_list(data.get("TagIds")),
            feature_ids=_safe_uuid_list(data.get("FeatureIds")),
            series_ids=_safe_uuid_list(data.get("SeriesIds")),
            age_rating_ids=_safe_uuid_list(data.get("AgeRatingIds")),
            region_ids=_safe_uuid_list(data.get("RegionIds")),
            source_id=_safe_uuid(data.get("SourceId")),
            completion_status_id=_safe_uuid(data.get("CompletionStatusId")),
            release_date=release_date,
            last_activity=_safe_dt(data.get("LastActivity")),
            added=_safe_dt(data.get("Added")),
            modified=_safe_dt(data.get("Modified")),
            last_size_scan_date=_safe_dt(data.get("LastSizeScanDate")),
            playtime=data.get("Playtime", 0),
            play_count=data.get("PlayCount", 0),
            install_size=data.get("InstallSize"),
            user_score=data.get("UserScore"),
            critic_score=data.get("CriticScore"),
            community_score=data.get("CommunityScore"),
            icon=data.get("Icon"),
            cover_image=data.get("CoverImage"),
            background_image=data.get("BackgroundImage"),
            install_directory=data.get("InstallDirectory"),
            version=data.get("Version"),
            manual=data.get("Manual", ""),
            pre_script=data.get("PreScript", ""),
            post_script=data.get("PostScript", ""),
            game_started_script=data.get("GameStartedScript", ""),
            use_global_pre_script=data.get("UseGlobalPreScript", True),
            use_global_post_script=data.get("UseGlobalPostScript", True),
            use_global_game_started_script=data.get("UseGlobalGameStartedScript", True),
            links=links,
            game_actions=game_actions,
            roms=roms,
        )

    def import_to_database(self, db: Any) -> int:
        """Import entire Playnite library into a GameDatabase. Returns game count."""
        from .database import GameDatabase
        assert isinstance(db, GameDatabase)

        # Import lookup tables first
        for platform in self.read_all_platforms():
            db.add_lookup(platform)
        for source in self.read_all_sources():
            db.add_lookup(source)
        for company in self.read_all_companies():
            db.add_lookup(company)
        for genre in self.read_all_genres():
            db.add_lookup(genre)
        for category in self.read_all_categories():
            db.add_lookup(category)
        for tag in self.read_all_tags():
            db.add_lookup(tag)
        for feature in self.read_all_features():
            db.add_lookup(feature)
        for series in self.read_all_series():
            db.add_lookup(series)
        for age_rating in self.read_all_age_ratings():
            db.add_lookup(age_rating)
        for region in self.read_all_regions():
            db.add_lookup(region)
        for cs in self.read_all_completion_statuses():
            db.add_lookup(cs)

        games = self.read_all_games()
        if games:
            db.add_games_batch(games)
        return len(games)


class PlayniteLibraryWriter:
    """Writes games back to Playnite JSON directory format."""

    @staticmethod
    def _uuid_to_json(u: uuid.UUID) -> str | None:
        if u == _EMPTY_UUID:
            return None
        return str(u)

    @staticmethod
    def _uuid_list_to_json(ids: list[uuid.UUID] | None) -> list[str] | None:
        if ids is None:
            return None
        return [str(u) for u in ids]

    @classmethod
    def _game_to_json_dict(cls, game: Game) -> dict:
        """Convert Game dataclass to PascalCase dict matching Playnite JSON format."""
        d: dict[str, Any] = {}

        def _set(key: str, val: Any) -> None:
            if val is not None and val != "" and val != 0 and val is not False:
                d[key] = val
            elif val is False and key not in ("Hidden", "Favorite", "IsInstalled"):
                pass  # Skip false booleans except meaningful ones
            elif isinstance(val, bool):
                d[key] = val

        d["Id"] = str(game.id)
        d["Name"] = game.name
        _set("GameId", game.game_id)
        _set("PluginId", cls._uuid_to_json(game.plugin_id))
        _set("SortingName", game.sorting_name)
        _set("Description", game.description)
        _set("Notes", game.notes)
        d["Hidden"] = game.hidden
        d["Favorite"] = game.favorite
        d["IsInstalled"] = game.is_installed

        _set("PlatformIds", cls._uuid_list_to_json(game.platform_ids))
        _set("DeveloperIds", cls._uuid_list_to_json(game.developer_ids))
        _set("PublisherIds", cls._uuid_list_to_json(game.publisher_ids))
        _set("GenreIds", cls._uuid_list_to_json(game.genre_ids))
        _set("CategoryIds", cls._uuid_list_to_json(game.category_ids))
        _set("TagIds", cls._uuid_list_to_json(game.tag_ids))
        _set("FeatureIds", cls._uuid_list_to_json(game.feature_ids))
        _set("SeriesIds", cls._uuid_list_to_json(game.series_ids))
        _set("AgeRatingIds", cls._uuid_list_to_json(game.age_rating_ids))
        _set("RegionIds", cls._uuid_list_to_json(game.region_ids))
        _set("SourceId", cls._uuid_to_json(game.source_id))
        _set("CompletionStatusId", cls._uuid_to_json(game.completion_status_id))

        if game.release_date:
            d["ReleaseDate"] = game.release_date.serialize()
        _set("LastActivity", game.last_activity.isoformat() if game.last_activity else None)
        _set("Added", game.added.isoformat() if game.added else None)
        _set("Modified", game.modified.isoformat() if game.modified else None)

        _set("Playtime", game.playtime)
        _set("PlayCount", game.play_count)
        _set("InstallSize", game.install_size)
        _set("UserScore", game.user_score)
        _set("CriticScore", game.critic_score)
        _set("CommunityScore", game.community_score)

        _set("Icon", game.icon)
        _set("CoverImage", game.cover_image)
        _set("BackgroundImage", game.background_image)
        _set("InstallDirectory", game.install_directory)
        _set("Version", game.version)

        if game.links:
            d["Links"] = [{"Name": lk.name, "Url": lk.url} for lk in game.links]
        if game.game_actions:
            d["GameActions"] = [
                {
                    "Type": int(a.type), "Name": a.name, "Path": a.path,
                    "IsPlayAction": a.is_play_action,
                }
                for a in game.game_actions
            ]
        if game.roms:
            d["Roms"] = [{"Name": r.name, "Path": r.path} for r in game.roms]

        return d

    @classmethod
    def write_game(cls, game: Game, library_path: str | Path) -> None:
        lp = Path(library_path)
        games_dir = lp / "games"
        games_dir.mkdir(parents=True, exist_ok=True)
        fp = games_dir / f"{game.id}.json"
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(cls._game_to_json_dict(game), f, indent=2, ensure_ascii=False)

    @classmethod
    def write_all(cls, db: Any, library_path: str | Path) -> None:
        from .database import GameDatabase
        assert isinstance(db, GameDatabase)
        for game in db.get_all_games():
            cls.write_game(game, library_path)
