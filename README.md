# Xenia Game Launcher

A lightweight PySide6 launcher for Xbox 360 games running through Xenia Canary and Xenia Manager.

The launcher imports your Xenia Manager `games.json`, stores game metadata in SQLite, provides title cleanup tools, favourites, search, sorting, multi-disc support, play tracking and downloading title updates from xboxunity.net for games in the list.

---

# Features

## Library Management

- Import games from Xenia Manager `games.json`
- Identify Multi Disc games
- Search games
- Sort by any column
- Download Title Updates from xboxunity.net for games in the list

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

## Launching

Double-click any game to launch it using Xenia Canary.

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

# Sidebar Functions

## Login to XboxUnity.Net

### Getting XboxUnity API Key
1. **Register** at [XboxUnity.net](https://xboxunity.net)
2. **Go to your profile settings**
3. **Generate an API Key**
4. **Copy and paste** into X360 TU Manager

## Import Xenia Manager library

Imports the current Xenia Manager library.


## Fix Titles

Cleans imported game names.

## Update Xenia Manager library

Writes corrected titles back into Xenia Manager.

## Refresh

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


## X360 TU Manager

X360 TU Manager is a Python GUI tool for managing and downloading Title Updates (TUs) for Xbox 360 games from XboxUnity, using each game's MediaID and TitleID.

Project:
https://github.com/Wamphyre/X360-TU-Manager

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
