"""
tool.py
-------

Master entry point for the HashDB Toolbox.

This module:
- Presents a simple text-based menu
- Launches the GUI
- Launches the CLI parser
- Ensures the database path exists
- Acts as the single entry point for the entire system

It does NOT:
- Perform hashing
- Modify the database
- Run cleanup or dedupe logic directly
"""

import os
import sys
import argparse
import shlex

from .cli import build_parser, register_cli as _register_cli

# ------------------------------------------------------------
# Web UI Configuration (for dynamic GUI generation)
# ------------------------------------------------------------
webui_config = {
    "actions": [
        {
            "id": "scan",
            "name": "Scan Directory",
            "description": "Scan and hash files in a directory.",
            "fields": [
                {"id": "directory", "name": "Directory to Scan", "type": "directory", "required": True},
                {"id": "db", "name": "Database Path", "type": "file", "default": ""},
                {"id": "hash", "name": "Hash Algorithm", "type": "select", "options": ["sha256", "md5"], "default": "sha256"},
            ],
            "command": "hashdb scan {directory}",
        },
        {
            "id": "verify",
            "name": "Verify Files",
            "description": "Verify files against stored hashes.",
            "fields": [
                {"id": "database", "name": "Database Path", "type": "file", "required": True},
                {"id": "hash", "name": "Hash Algorithm", "type": "select", "options": ["sha256", "md5"], "default": "sha256"},
            ],
            "command": "hashdb verify {database}",
        },
        {
            "id": "dedupe",
            "name": "Deduplicate",
            "description": "Find and remove duplicate files.",
            "fields": [
                {"id": "database", "name": "Database Path", "type": "file", "required": True},
                {"id": "hash", "name": "Hash Algorithm", "type": "select", "options": ["sha256", "md5"], "default": "sha256"},
                {"id": "hard_delete", "name": "Permanently delete (dangerous)", "type": "checkbox", "default": False},
            ],
            "command": "hashdb dedupe {database}",
        },
        {
            "id": "report",
            "name": "Duplicate Report",
            "description": "Generate a report of duplicate files.",
            "fields": [
                {"id": "database", "name": "Database Path", "type": "file", "required": True},
                {"id": "output", "name": "Output File", "type": "file", "required": True},
            ],
            "command": "hashdb report {database} {output}",
        },
    ]
}


def register_cli(subparsers):
    _register_cli(subparsers)


def run(mode="menu"):
    """
    Unified entry point for dynamic loading.
    """
    if mode == "gui":
        print("[INFO] Launching GUI (webui)…")
        _launch_webui()
    elif mode == "cli":
        # In a dynamic context, CLI args are usually handled by argparse before calling run,
        # but if called directly:
        run_cli_interactive()
    else:
        # Default to menu/tui
        run_menu()

def _launch_webui() -> int:
    import toolbox.webui
    return toolbox.webui.launch_gui(selected_tool="hashdb")


BANNER = r"""
===========================================
        HASHDB TOOLBOX (MASTER MENU)
===========================================
"""


MENU = """
Choose an option:

  1) Launch GUI
  2) Use CLI mode
  3) Exit

Enter choice: """


def run_cli():
    """
    Run the CLI parser exactly as if invoked from command line.
    """
    parser = build_parser()
    args = parser.parse_args(sys.argv[2:])  # skip "tool.py cli"
    if not hasattr(args, "func"):
        parser.print_help()
        return
    args.func(args)


def run_cli_interactive():
    """
    Interactive CLI mode - prompts for commands until user exits.
    """
    parser = build_parser()
    print("[INFO] Entering interactive CLI mode.")
    print("Type commands like: scan --dir /path --db mydb.sqlite --hash md5")
    print("Type 'help' for available commands, 'exit' to quit.\n")

    while True:
        try:
            cmd_line = input("hashdb> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            return

        if not cmd_line:
            continue
        if cmd_line.lower() in ("exit", "quit", "q"):
            print("Goodbye.")
            return
        if cmd_line.lower() == "help":
            parser.print_help()
            continue

        # Parse and execute the command
        try:
            args = parser.parse_args(shlex.split(cmd_line))
            if hasattr(args, "func"):
                args.func(args)
            else:
                parser.print_help()
        except SystemExit:
            # argparse calls sys.exit on error; catch and continue
            pass
        except Exception as e:
            print(f"[ERROR] {e}")


def run_menu():
    """
    Text-based menu for interactive use.
    """
    print(BANNER)

    while True:
        choice = input(MENU).strip()

        if choice == "1":
            print("[INFO] Launching GUI (webui)…")
            _launch_webui()
            return

        elif choice == "2":
            print("[INFO] Entering CLI mode…")
            run_cli_interactive()
            return

        elif choice == "3":
            print("Goodbye.")
            return

        else:
            print("Invalid choice. Try again.")


def main():
    """
    Main entry point for the toolbox.
    """
    # If user runs: python tool.py cli ...
    if len(sys.argv) > 1 and sys.argv[1] == "cli":
        run_cli()
        return

    # Otherwise show menu
    run_menu()


if __name__ == "__main__":
    main()