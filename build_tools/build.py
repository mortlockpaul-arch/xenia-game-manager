import subprocess
import sys


def run():
    # Build
    subprocess.check_call([
        sys.executable,
        "build_tools/setup.py",
        "build"
    ])

    # Package
    subprocess.check_call([
        sys.executable,
        "build_tools/package.py"
    ])


if __name__ == "__main__":
    run()