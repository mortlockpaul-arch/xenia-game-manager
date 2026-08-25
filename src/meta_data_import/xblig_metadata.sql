-- XBLIG metadata catalogue
--
-- This is a reference catalogue imported from the XBLIG XLSX dataset.
-- It intentionally does not overwrite the existing games table.
--
-- Run with your SQLite database:
--   sqlite3 your_database.db < xblig_metadata.sql

CREATE TABLE IF NOT EXISTS xblig_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    normalized_title TEXT NOT NULL,
    developer TEXT,
    developer_account TEXT,
    genre TEXT,
    release_date TEXT,
    user_rating REAL,
    rating_count INTEGER,
    file_size TEXT,
    available_on TEXT,
    links TEXT,
    notes TEXT,
    updates TEXT,
    category_scores TEXT,
    timecode TEXT,
    gamefaqs INTEGER NOT NULL DEFAULT 0,
    title_text_from_youtube TEXT,
    source_sheet TEXT NOT NULL DEFAULT 'XBLIG Games',
    source_file TEXT,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(normalized_title)
);

CREATE INDEX IF NOT EXISTS idx_xblig_metadata_title
    ON xblig_metadata(title);

CREATE INDEX IF NOT EXISTS idx_xblig_metadata_normalized_title
    ON xblig_metadata(normalized_title);

CREATE INDEX IF NOT EXISTS idx_xblig_metadata_developer
    ON xblig_metadata(developer_account);
