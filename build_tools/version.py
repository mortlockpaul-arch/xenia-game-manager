from subprocess import check_output

def get_version():
    try:
        # latest tag like v0.3.1
        version = check_output(["git", "describe", "--tags"]).decode().strip()
        return version.lstrip("v")
    except Exception:
        return "0.0.0"