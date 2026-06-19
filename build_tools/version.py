import subprocess

def get_version():
    try:
        desc = subprocess.check_output(
            ["git", "describe", "--tags", "--always", "--dirty"],
            text=True
        ).strip()
    except Exception:
        return "0.2.0"

    parts = desc.split("-")

    if len(parts) >= 3:
        tag = parts[0]
        commits = parts[1]
        git_hash = parts[2]
        return f"{tag}.{commits}.post0+{git_hash}"

    return parts[0]