from package_window import compress_tool, ToolManager, ensure_tool_extracted

def tools_setup():
    compress_tool("conversion")
    compress_tool("ilspycmd")
    compress_tool("ilspy")
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
    tools_setup()

    # ensure_tool_extracted("conversion")
    # ensure_tool_extracted("decompiler")
    # ensure_tool_extracted("vgmstream")

    # with ToolManager("conversion"):
    #     print("Conversion is complete.")
    # with ToolManager("decompiler"):
    #     print("Decompiler is complete.")
    # with ToolManager("vgmstream"):
    #     print("Vgmstream is complete.")
