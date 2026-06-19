def get_version():
    import subprocess

    desc = subprocess.check_output(
        ["git", "describe", "--tags", "--dirty", "--always"],
        text=True
    ).strip()

    # 0.2-13-gbccbcea -> 0.2.13.post13+gbccbcea
    if "-" in desc:
        tag, commits, git = desc.split("-")
        return f"{tag}.{commits}.post0+{git}"

    return desc