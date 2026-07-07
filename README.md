# Xenia Game Launcher

A lightweight PySide6 launcher for Xbox 360 games running through Xenia Canary and Xenia Manager.
The launcher imports your Xenia Manager `games.json`, stores game metadata in SQLite, provides title cleanup tools, favourites, search, sorting, multi-disc support, play tracking and downloading title updates from xboxunity.net for games in the list.

---

# Features

## Library Management

- Import games from Xenia Manager `games.json` or Xenia Edge Game List
- Identify Multi Disc games
- Add Favourites
- Download Title Updates from xboxunity.net for games in the list
- Optimize Xenia Edge Games 
- Title Cleanup
- Extract Downloaded Archives
- Unify content folders for all Xenia Forks

---
# License
Personal use project.
## Third-Party Projects

This software integrates with:

- Xenia Manager / Netplay / Mousehook and Canary
- Xenia Edge

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
