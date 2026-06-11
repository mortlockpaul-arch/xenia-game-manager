# utils.py

import re

DISC_PATTERNS = [
    r"\bdisc\s*(\d+)\b",
    r"\bdisk\s*(\d+)\b",
    r"\bdvd\s*(\d+)\b",
    r"\bcd\s*(\d+)\b",
]

import re

KEEP_UPPER = {
    "DLC", "HD", "XBLA", "USA", "PAL",
    "NTSC", "GTA", "NBA", "NHL", "UFC",
    "FIFA", "MX", "ATV","II","III","UGC","NFS", "IL"
}


def smart_title_case(title):
    title = re.sub(r"\s*\(\d+\)$", "", title)
    title = re.sub(r"\s+", " ", title).strip()

    words = []

    for word in title.split():

        # already normal mixed case
        if not word.isupper():
            words.append(word)
            continue

        # preserve acronyms
        if word in KEEP_UPPER:
            words.append(word)
            continue

        # convert shouting words
        words.append(word.capitalize())

    return " ".join(words)


def detect_disc_number(title: str):
    """
    Returns disc number if found.
    """

    if not title:
        return None

    lower = title.lower()

    for pattern in DISC_PATTERNS:
        match = re.search(pattern, lower)

        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None

    return None


def strip_disc_suffix(title: str):
    """
    Lost Odyssey Disc 1
    -> Lost Odyssey
    """

    if not title:
        return ""

    title = re.sub(
        r"\s*[-:]?\s*(disc|disk|dvd|cd)\s*\d+$",
        "",
        title,
        flags=re.IGNORECASE,
    )

    return title.strip()


def is_install_disc(label: str):
    if not label:
        return False

    label = label.lower()

    return any(
        word in label
        for word in [
            "install",
            "data",
            "content"
        ]
    )


def is_multiplayer_disc(label: str):
    if not label:
        return False

    label = label.lower()

    return "multiplayer" in label


def disc_role(label: str):
    """
    Human readable disc role.
    """

    if not label:
        return "Unknown"

    if is_install_disc(label):
        return "Install"

    if is_multiplayer_disc(label):
        return "Multiplayer"

    return "Story"


DISC_TYPE_LABELS = {
    "story_swap": "Story Campaign",
    "install_play": "Install + Play",
    "campaign_multiplayer": "Campaign + Multiplayer",
    "hybrid_story_content": "Hybrid Content",
    "play_install": "Install Disc",
}


def format_disc_type(disc_type: str):
    return DISC_TYPE_LABELS.get(
        disc_type,
        disc_type or "Single Disc"
    )

def star(value):
    try:
        return "⭐" if int(value) == 1 else "☆"
    except Exception:
        return "☆"

def format_play_count(count):
    try:
        count = int(count)
    except Exception:
        count = 0

    return f"{count:,}"


def sort_title(title):
    """
    Ignore 'The' when sorting.
    """

    if not title:
        return ""

    lower = title.lower()

    if lower.startswith("the "):
        return lower[4:]

    return lower


if __name__ == "__main__":

    tests = [
        "HALO 3 (1)",
        "FORZA MOTORSPORT 4 (2)",
        "Lost Odyssey Disc 1",
        "Blue Dragon DVD 2"
    ]

    for t in tests:
        print("Original :", t)
        print("Fixed    :", smart_title_case(t))
        print("Disc     :", detect_disc_number(t))
        print("Stripped :", strip_disc_suffix(t))
        print()