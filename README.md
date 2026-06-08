# Xenia SQLite Launcher

A lightweight PySide6 launcher for Xbox 360 games running through Xenia Canary.

The launcher imports your Xenia Manager `games.json`, stores game metadata in SQLite, provides title cleanup tools, favourites, search, sorting, multi-disc support, and play tracking.

---

# Features

## Library Management

- Import games from Xenia Manager `games.json`
- Store metadata in SQLite
- Search games instantly
- Sort by any column
- Alternate row colours
- Refresh library

## Title Cleanup

- Remove duplicate suffixes:

```text
Halo 3 (1)
Halo 3 (2)
```

becomes:

```text
Halo 3
```

- Fix ALL CAPS names:

```text
FORZA MOTORSPORT 4
```

becomes:

```text
Forza Motorsport 4
```

- Fix mixed uppercase names:

```text
NARUTO SHIPPUDEN Ultimate Ninja STORM Generations
```

becomes:

```text
Naruto Shippuden Ultimate Ninja Storm Generations
```

- Export corrected titles back to Xenia Manager

## Favourites

Click the ⭐ column to toggle favourites.

```text
⭐ Favourite
☆ Not Favourite
```

Favourites are stored in SQLite.

## Launching

Double-click any game to launch it using Xenia Canary.

Launches:

```text
xenia_canary.exe "game.zar"
```

Tracks:

- Last Played
- Play Count

## Multi-Disc Support

Supports:

- Story swap discs
- Install/play discs
- Campaign/multiplayer discs

Examples:

### Lost Odyssey

```text
Disc 1 - Story Start
Disc 2 - Story Continuation
Disc 3 - Story Continuation
Disc 4 - Story End
```

### GTA V

```text
Disc 1 - Install Disc
Disc 2 - Play Disc
```

### Halo 3 ODST

```text
Disc 1 - Campaign
Disc 2 - Multiplayer
```

---

# Folder Structure

```text
xenia_sqlite_launcher/
│
├── main.py
├── db.py
├── model.py
├── ui.py
├── utils.py
├── import_multidisc.py
│
├── games.db
│
└── multidisc.json
```

---

# Requirements

Python 3.10+

Install dependencies:

```bash
pip install pyside6
```

or

```bash
uv add pyside6
```

---

# Configuration

Edit the paths in `ui.py`.

## Xenia Canary

```python
XENIA_EXE = (
    r"D:\RetroBat\emulators\Xenia Canary\xenia_canary.exe"
)
```

## games.json

```python
GAMES_JSON = (
    r"D:\RetroBat\emulators\xenia-manager\Config\games.json"
)
```

---

# First Run

Create database:

```bash
python main.py
```

Import library:

```text
Import games.json
```

The database will be populated from:

```text
D:\RetroBat\emulators\xenia-manager\Config\games.json
```

---

# Database Schema

## games

```sql
CREATE TABLE games
(
    game_id TEXT PRIMARY KEY,
    title TEXT,
    file_path TEXT,

    favourite INTEGER DEFAULT 0,

    last_played TEXT,
    play_count INTEGER DEFAULT 0,

    disc_count INTEGER DEFAULT 1,
    disc_type TEXT,

    xenia_disc_swap_required INTEGER DEFAULT 0
);
```

## discs

```sql
CREATE TABLE discs
(
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    title_id TEXT,
    disc_index INTEGER,

    label TEXT,
    file_path TEXT
);
```

---

# Toolbar Functions

## Import games.json

Imports the current Xenia Manager library.

## Rebuild DB

Deletes and recreates the SQLite database.

## Fix Titles

Cleans imported game names.

## Update games.json

Writes corrected titles back into Xenia Manager.

## Refresh

Reloads all data from SQLite.

---

# Usage

## Launch a game

Double-click a row.

## Search

Use the search box.

## Favourite

Click the ⭐ column.

## Sort

Click any column heading.

---

# Planned Features

- Box art thumbnails
- Game details dialog
- Disc grouping UI
- Multi-disc launch wizard
- Custom emulator per game
- Recent games view
- Favourite filter
- Dark/light themes
- RetroBat integration
- Compatibility status import
- Automatic title database lookups

---

# Troubleshooting

## No games displayed

Verify:

```text
D:\RetroBat\emulators\xenia-manager\Config\games.json
```

exists.

Re-import using:

```text
Import games.json
```

---

## SQLite error

Delete:

```text
games.db
```

then:

```text
Rebuild DB
```

---

## Xenia does not launch

Verify:

```text
D:\RetroBat\emulators\Xenia Canary\xenia_canary.exe
```

exists.

---

# License

Personal use project.

## Third-Party Projects

This software integrates with:

- Xenia Canary
- Xenia Manager

All trademarks, copyrights, and intellectual property remain the property of their respective owners.

This project is an independent companion utility and is not affiliated with or endorsed by the Xenia or Xenia Manager development teams.

# Credits

## Xenia

This launcher is designed to work with the Xenia Canary Xbox 360 emulator.

Xenia is an open-source Xbox 360 emulator developed by the Xenia project contributors.

Project:
https://github.com/xenia-project/xenia

## Xenia Manager

This launcher imports and updates the Xenia Manager game library database (`games.json`).

Special thanks to the Xenia Manager project for providing a user-friendly frontend and game management system for Xenia.

Project:
https://github.com/xenia-manager/xenia-manager

This application is intended as a companion utility and is not affiliated with, endorsed by, or maintained by the Xenia Manager developers.

## Microsoft

Xbox 360, Xbox, and related trademarks are property of Microsoft Corporation.

## This Project

Xenia SQLite Launcher

Created by Paul Mortlock

Provides:

- SQLite-backed game library
- Advanced title cleanup
- Favourites
- Search and sorting
- Play tracking
- Multi-disc metadata support
- Integration with Xenia Manager libraries
