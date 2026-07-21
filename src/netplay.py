import json
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup

URL = "https://github.com/AdrianCassar/xenia-canary/wiki/Netplay-Compatibility"
OUT_FILE = Path("netplay.json")

TITLE_ID_RE = re.compile(r"\b([0-9A-F]{8})\b", re.IGNORECASE)


def clean(text: str) -> str:
    return " ".join(text.replace("\xa0", " ").split())

def clean_column(cell):
    return clean(cell.get_text(" ", strip=True))

def extract_title_id(cell):
    # Visible text
    text = clean(cell.get_text(" ", strip=True))

    match = TITLE_ID_RE.search(text)
    if match:
        return match.group(1).upper()

    # Links
    for link in cell.find_all("a", href=True):
        href = link["href"]

        match = TITLE_ID_RE.search(href)
        if match:
            return match.group(1).upper()

    return None

def parse_table(table):
    rows = table.find_all("tr")

    if not rows:
        return []

    # Get headers
    headers = [
        clean_column(cell)
        for cell in rows[0].find_all(["th", "td"])
    ]

    games = []

    for row in rows[1:]:
        cells = row.find_all(["td", "th"])

        if not cells:
            continue

        values = [
            clean_column(cell)
            for cell in cells
        ]

        # Pad missing columns
        while len(values) < len(headers):
            values.append("")

        game = dict(zip(headers, values))

        # Extract title id from ALL cells including links
        title_id = None

        for cell in cells:
            title_id = extract_title_id(cell)
            if title_id:
                break

        game["title_id"] = title_id

        # Normalise the game name
        game["title"] = game.get("Game", "")

        games.append(game)

    return games


def build_json():
    r = requests.get(URL, timeout=30)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    # GitHub wiki pages use markdown-body for rendered content
    content = soup.select_one(".markdown-body")
    if not content:
        raise RuntimeError("Could not find markdown-body")

    tables = content.find_all("table")
    if not tables:
        raise RuntimeError("No tables found on page")

    for table in tables:
        print(table.prettify()[:2000])
        break

    all_games = []
    for table in tables:
        all_games.extend(parse_table(table))

    # Remove duplicates by title
    dedup = {}
    for game in all_games:
        dedup[game["title"]] = game

    games = sorted(dedup.values(), key=lambda g: g["title"].lower())

    data = {
        "source": URL,
        "version": "2026-07-21",
        "count": len(games),
        "games": games,
    }

    OUT_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Wrote {len(games)} games to {OUT_FILE}")


if __name__ == "__main__":
    build_json()