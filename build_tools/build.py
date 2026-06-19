import subprocess
import sys

def run():
    subprocess.check_call([
        sys.executable,
        "build_tools/setup.py",
        "build"
    ])

if __name__ == "__main__":
    run()