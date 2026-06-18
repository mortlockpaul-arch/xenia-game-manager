from cx_Freeze import setup

# Dependencies are automatically detected, but they might need fine-tuning.
build_exe_options = {
    "excludes": ["tkinter", "unittest"],
    "zip_include_packages": ["encodings", "PySide6", "shiboken6"],
    "include_files": ["db"],
}

setup(
    name="Xenia Game Manager",
    version="0.1",
    options={"build_exe": build_exe_options},
    description="Xenia Game Manager",
    executables=[{"script": "main.py", "base": "gui"}],

)
