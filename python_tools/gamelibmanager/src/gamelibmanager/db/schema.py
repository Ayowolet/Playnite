"""SQLite schema definitions for the game library database."""

SCHEMA_VERSION = 2

GAMES_TABLE = """
CREATE TABLE IF NOT EXISTS games (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    game_id TEXT,
    plugin_id TEXT,
    sorting_name TEXT,
    description TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    hidden INTEGER DEFAULT 0,
    favorite INTEGER DEFAULT 0,
    is_installed INTEGER DEFAULT 0,
    is_installing INTEGER DEFAULT 0,
    is_uninstalling INTEGER DEFAULT 0,
    is_launching INTEGER DEFAULT 0,
    is_running INTEGER DEFAULT 0,
    override_install_state INTEGER DEFAULT 0,
    include_library_plugin_action INTEGER DEFAULT 1,
    enable_system_hdr INTEGER DEFAULT 0,
    platform_ids TEXT,
    developer_ids TEXT,
    publisher_ids TEXT,
    genre_ids TEXT,
    category_ids TEXT,
    tag_ids TEXT,
    feature_ids TEXT,
    series_ids TEXT,
    age_rating_ids TEXT,
    region_ids TEXT,
    source_id TEXT,
    completion_status_id TEXT,
    release_date TEXT,
    last_activity TEXT,
    added TEXT,
    modified TEXT,
    last_size_scan_date TEXT,
    playtime INTEGER DEFAULT 0,
    play_count INTEGER DEFAULT 0,
    install_size INTEGER,
    user_score INTEGER,
    critic_score INTEGER,
    community_score INTEGER,
    icon TEXT,
    cover_image TEXT,
    background_image TEXT,
    install_directory TEXT,
    version TEXT,
    manual TEXT DEFAULT '',
    pre_script TEXT DEFAULT '',
    post_script TEXT DEFAULT '',
    game_started_script TEXT DEFAULT '',
    use_global_pre_script INTEGER DEFAULT 1,
    use_global_post_script INTEGER DEFAULT 1,
    use_global_game_started_script INTEGER DEFAULT 1,
    links TEXT,
    game_actions TEXT,
    roms TEXT,
    _normalized_name TEXT
)
"""

PLATFORMS_TABLE = """
CREATE TABLE IF NOT EXISTS platforms (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    specification_id TEXT DEFAULT '',
    icon TEXT DEFAULT '',
    cover TEXT DEFAULT '',
    background TEXT DEFAULT ''
)
"""

_SIMPLE_LOOKUP_TABLES = [
    "genres", "companies", "tags", "categories", "features",
    "sources", "series", "age_ratings", "regions", "completion_statuses",
]

DUPLICATE_HISTORY_TABLE = """
CREATE TABLE IF NOT EXISTS duplicate_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    action TEXT NOT NULL,
    master_game_id TEXT NOT NULL,
    duplicate_game_ids TEXT NOT NULL,
    details TEXT
)
"""

MERGE_HISTORY_TABLE = """
CREATE TABLE IF NOT EXISTS merge_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    source_library TEXT NOT NULL,
    target_library TEXT NOT NULL,
    strategy TEXT NOT NULL,
    games_added INTEGER DEFAULT 0,
    games_updated INTEGER DEFAULT 0,
    games_skipped INTEGER DEFAULT 0,
    conflicts_resolved INTEGER DEFAULT 0,
    backup_path TEXT,
    details TEXT
)
"""

SCHEMA_META_TABLE = """
CREATE TABLE IF NOT EXISTS _schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT
)
"""

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_games_normalized_name ON games(_normalized_name)",
    "CREATE INDEX IF NOT EXISTS idx_games_plugin_game_id ON games(plugin_id, game_id)",
    "CREATE INDEX IF NOT EXISTS idx_games_source_id ON games(source_id)",
    "CREATE INDEX IF NOT EXISTS idx_games_name ON games(name)",
]


def get_all_ddl() -> list[str]:
    """Return all DDL statements needed to initialise the database."""
    stmts: list[str] = [
        SCHEMA_META_TABLE,
        GAMES_TABLE,
        PLATFORMS_TABLE,
    ]
    for tbl in _SIMPLE_LOOKUP_TABLES:
        stmts.append(
            f"CREATE TABLE IF NOT EXISTS {tbl} "
            f"(id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '')"
        )
    stmts.append(DUPLICATE_HISTORY_TABLE)
    stmts.append(MERGE_HISTORY_TABLE)
    stmts.extend(INDEXES)
    return stmts
