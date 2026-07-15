import subprocess
import sys
from pathlib import Path

from build_tools.package import create_defaults, copy_optimized_settings, zip_portable

ROOT = Path(__file__).parent.parent
src_dir = ROOT / "src"

for file in src_dir.rglob("*.previous"):
    print(f"Removing {file}")
    file.unlink()

create_defaults()
copy_optimized_settings()

# Build the executable
subprocess.run([sys.executable, "setup.py", "build_exe"], check=True)

# Build the MSI
subprocess.run([sys.executable, "setup.py", "bdist_msi"], check=True)

zip_portable()