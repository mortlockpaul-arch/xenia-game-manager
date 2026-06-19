from cx_Freeze import setup

# Dependencies are automatically detected, but they might need fine-tuning.
build_exe_options = {
    "excludes": ["tkinter", "unittest"],
    "zip_include_packages": [],
    "include_files": [("src/db", "db")],
}


directory_table = [
    ("ProgramMenuFolder", "TARGETDIR", "."),
    ("MyProgramMenu", "ProgramMenuFolder", "MYPROG~1|My Program"),
]

msi_data = {
    "Directory": directory_table,
    "ProgId": [
        ("Prog.Id", None, None, "This is a description", "IconId", None),
    ],
    "Icon": [
        ("IconId", "Xenia_Game_Manager.ico"),
    ],
}

bdist_msi_options = {
    "add_to_path": True,
    "data": msi_data,
    "upgrade_code": "{6B29FC40-CA47-1067-B31D-00DD010662DA}",
}

setup(
    name="Xenia Game Manager",
    version="0.2",
    description="Xenia Game Manager",
    executables=[{"script": "src/main.py", "base": "gui"}],
    options={"build_exe": build_exe_options, "bdist_msi": bdist_msi_options},
)
