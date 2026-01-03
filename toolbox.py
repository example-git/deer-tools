#!/usr/bin/env python3
"""
toolbox.py
-------------------
Master entry point for the Tools Suite.
Automatically discovers and loads tools from subdirectories.
Provides a unified TUI menu and CLI interface.
"""

import sys
import os
import argparse
import importlib
from pathlib import Path

# Shared tool parsing utilities
import toolbox.tool_parser

PLUGINS_DIR = Path(__file__).resolve().parent / "plugins"

# Try to import shared TUI (curses-based fallback)
try:
    import toolbox.tui
    TUI_CURSES_AVAILABLE = True
except ImportError:
    TUI_CURSES_AVAILABLE = False

# Rich+Questionary TUI (preferred, high compatibility)
try:
    import toolbox.textui
    TEXTUI_AVAILABLE = True
except ImportError:
    TEXTUI_AVAILABLE = False

# Combined TUI availability: prefer textui, fallback to curses
TUI_AVAILABLE = TEXTUI_AVAILABLE or TUI_CURSES_AVAILABLE

# Browser-based GUI launcher (no tkinter dependency)
try:
    import toolbox.webui
    WEBUI_AVAILABLE = True
except ImportError:
    WEBUI_AVAILABLE = False

# Desktop wrapper (Electron-like) around webui
try:
    import toolbox.desktopui
    DESKTOPUI_AVAILABLE = True
except ImportError:
    DESKTOPUI_AVAILABLE = False

TOOLS = {}


def _is_interactive_tty() -> bool:
    return bool(sys.stdin.isatty() and sys.stdout.isatty())

def discover_tools():
    """
    Scans subdirectories for 'tool.py' and loads them as modules.
    """
    base_path = PLUGINS_DIR

    # Ensure repo root is on sys.path for plugins.* imports
    repo_root = Path(__file__).resolve().parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    if not base_path.exists():
        return

    for item in os.listdir(base_path):
        item_path = base_path / item

        # Skip non-directories and special folders
        if not item_path.is_dir() or item.startswith('.') or item.startswith('__'):
            continue

        tool_file = item_path / "tool.py"
        if tool_file.exists():
            try:
                module_name = f"plugins.{item}.tool"
                module = importlib.import_module(module_name)
                TOOLS[item] = module
            except Exception as e:  # pylint: disable=broad-exception-caught
                print(f"[WARN] Failed to load tool '{item}': {e}")

def run_tui_menu():
    """
    Launches the master TUI menu.
    Prefers the modern textui (rich+questionary) if available,
    falls back to curses-based tui.
    """
    if not TUI_AVAILABLE:
        print("[ERROR] TUI library not found. Please install rich/questionary or ensure curses support.")
        return

    # Prefer textui (cross-platform, high compatibility)
    if TEXTUI_AVAILABLE:
        toolbox.textui.launch_tui()
        return

    # Fallback to curses-based menu
    if not TUI_CURSES_AVAILABLE:
        print("[ERROR] No TUI backend available.")
        return

    menu_items = []

    # Convenience: offer web GUI launcher from the TUI.
    if WEBUI_AVAILABLE:
        menu_items.append(("Open GUI Launcher (Browser)", toolbox.webui.launch_gui))
    
    # Sort tools by name for consistent order
    for name in sorted(TOOLS.keys()):
        module = TOOLS[name]
        
        # Helper to capture closure variables
        def make_runner(mod, mode):
            return lambda: mod.run(mode=mode)
        
        if hasattr(module, 'run'):
            # Prefer universal web GUI launcher rather than tkinter-based GUIs.
            if WEBUI_AVAILABLE:
                menu_items.append(
                    (
                        f"{name.replace('_', ' ').title()} (GUI Launcher)",
                        (lambda n=name: toolbox.webui.launch_gui(selected_tool=n)),
                    )
                )
            else:
                menu_items.append((f"{name.replace('_', ' ').title()} (GUI)", make_runner(module, 'gui')))

            # Add TUI option
            menu_items.append((f"{name.replace('_', ' ').title()} (TUI)", make_runner(module, 'tui')))
    
    menu_items.append(("Exit", lambda: sys.exit(0)))
    
    menu = toolbox.tui.CursesMenu("Master Toolbox", menu_items)
    menu.run()


def run_doctor() -> int:
    """Basic environment + discovery checks.

    Returns:
        int: process exit code (0 success, 1 issues)
    """
    print("=" * 60)
    print("TOOLS SUITE DOCTOR")
    print("=" * 60)

    issues = []
    warnings = []

    py_ver = sys.version_info
    print(f"[CHECK] Python: {py_ver.major}.{py_ver.minor}.{py_ver.micro}")
    if py_ver < (3, 8):
        issues.append("Python 3.8+ is recommended")

    print(f"[CHECK] Interactive TTY: {_is_interactive_tty()}")

    print("[CHECK] Discovered tools:")
    if not TOOLS:
        warnings.append("No tools discovered")
        print("  [WARN] none")
    else:
        for name in sorted(TOOLS.keys()):
            module = TOOLS[name]
            ok_register = hasattr(module, "register_cli")
            ok_run = hasattr(module, "run")
            print(f"  [OK] {name} (register_cli={ok_register}, run={ok_run})")
            if not ok_register:
                warnings.append(f"{name}: missing register_cli")
            if not ok_run:
                warnings.append(f"{name}: missing run")

    print("[CHECK] Optional UI support:")
    if TEXTUI_AVAILABLE:
        print("  [OK] textui TUI available (rich+questionary - preferred)")
    else:
        warnings.append("textui.py not importable; modern TUI unavailable")
        print("  [WARN] textui TUI not available (install: pip install rich questionary)")

    if TUI_CURSES_AVAILABLE:
        print("  [OK] curses TUI available (tui.py importable - fallback)")
    else:
        warnings.append("tui.py not importable; curses TUI fallback unavailable")
        print("  [WARN] curses TUI not available")

    if WEBUI_AVAILABLE:
        print("  [OK] browser GUI available (webui.py importable)")
    else:
        warnings.append("webui.py not importable; browser GUI unavailable")
        print("  [WARN] browser GUI not available")

    if DESKTOPUI_AVAILABLE:
        print("  [OK] desktop GUI wrapper available (desktopui.py importable)")
    else:
        warnings.append("desktopui.py not importable; desktop GUI wrapper unavailable")
        print("  [WARN] desktop GUI wrapper not available")

    # tkinter is intentionally not used; the browser web UI is the supported GUI path.

    print("=" * 60)
    if issues:
        print(f"RESULT: {len(issues)} issue(s) found")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("RESULT: All checks passed")

    if warnings:
        print(f"Warnings ({len(warnings)}):")
        for warning in warnings:
            print(f"  - {warning}")
    print("=" * 60)

    return 0 if not issues else 1


def main(argv: list[str] | None = None) -> None:
    discover_tools()

    parser = argparse.ArgumentParser(
        prog="toolbox",
        description="Tools Suite - unified CLI/TUI/Web UI launcher",
    )

    # Global options (before subcommands)
    parser.add_argument(
        "--threads", "-t",
        type=int,
        default=8,
        help="Number of worker threads for parallel operations (default: 8)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available Tools")

    # Register tool CLIs
    for name, module in TOOLS.items():
        if hasattr(module, "register_cli"):
            try:
                module.register_cli(subparsers)
            except Exception as e:  # pylint: disable=broad-exception-caught
                print(f"[WARN] Failed to register CLI for '{name}': {e}")

    # Built-in commands
    subparsers.add_parser("menu", help="Show interactive TUI menu")
    subparsers.add_parser("gui", help="Open browser-based GUI launcher")
    subparsers.add_parser("desktop", help="Open desktop GUI (pywebview) if available")
    subparsers.add_parser("doctor", help="Run environment validation checks")

    if argv is None:
        argv = sys.argv[1:]

    # If no arguments provided, launch TUI when possible
    if not argv:
        # If launched from a real terminal, default to TUI.
        if TUI_AVAILABLE and _is_interactive_tty():
            try:
                run_tui_menu()
            except KeyboardInterrupt:
                sys.exit(0)
            return

        # If not an interactive terminal (e.g. double-click / IDE run), open GUI.
        if DESKTOPUI_AVAILABLE:
            sys.exit(toolbox.desktopui.launch_desktop())
        if WEBUI_AVAILABLE:
            sys.exit(toolbox.webui.launch_gui())

        parser.print_help()
        return

    args = parser.parse_args(argv)

    # Set global thread count from CLI arg
    if hasattr(args, "threads") and args.threads:
        toolbox.tool_parser.set_global_threads(args.threads)

    if args.command == "menu":
        if not TUI_AVAILABLE:
            print("[ERROR] TUI not available (missing tui.py or curses support)")
            sys.exit(1)
        if not _is_interactive_tty():
            print("[ERROR] TUI requires an interactive terminal")
            sys.exit(1)
        run_tui_menu()
        return

    if args.command == "gui":
        if DESKTOPUI_AVAILABLE:
            sys.exit(toolbox.desktopui.launch_desktop())
        if WEBUI_AVAILABLE:
            sys.exit(toolbox.webui.launch_gui())
        print("[ERROR] GUI not available (missing desktopui.py/webui.py)")
        sys.exit(1)

    if args.command == "desktop":
        if not DESKTOPUI_AVAILABLE:
            print("[ERROR] Desktop wrapper not available.")
            print("[INFO] Install dependency: python -m pip install pywebview")
            if WEBUI_AVAILABLE:
                print("[INFO] Falling back to browser GUI.")
                sys.exit(toolbox.webui.launch_gui())
            sys.exit(1)
        sys.exit(toolbox.desktopui.launch_desktop())

    if args.command == "doctor":
        sys.exit(run_doctor())

    # Execute the selected tool's function
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
