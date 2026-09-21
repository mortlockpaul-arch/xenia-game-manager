from package_window import compress_tool, ToolManager, ensure_tool_extracted, get_actual_tool_path


def tools_setup():
    if get_actual_tool_path("conversion").exists():
        compress_tool("conversion")
    if get_actual_tool_path("ilspycmd").exists():
        compress_tool("ilspycmd")
    if get_actual_tool_path("ilspy").exists():
        compress_tool("ilspy")
    if get_actual_tool_path("vgmstream").exists():
        compress_tool("vgmstream")

    with ToolManager("conversion"):
        print("Conversion is complete.")

    with ToolManager("ilspycmd"):
        print("ILSpy command line is complete.")

    with ToolManager("ilspy"):
        print("ILSpy GUI is complete.")

    with ToolManager("vgmstream"):
        print("Vgmstream is complete.")

if __name__ == "__main__":
    # with ToolManager("conversion"):
    #     print("Conversion is complete.")

    tools_setup()
    # ensure_tool_extracted("ilspy", None)
    # ensure_tool_extracted("ilspycmd", None)
    # ensure_tool_extracted("vgmstream", None)
    # ensure_tool_extracted("conversion", None)