"""
tool.py
-------

Entry point for the upgraded Extension Repair Tool.

Provides:
- CLI mode
- GUI mode
- Toolbox integration
- Persistent config loading
- Logging setup
- Worker launch
- Diagnostics summary generation
"""

import os
import sys
import argparse
from queue import Queue

# Support running as a script (python plugins/extension_repair/tool.py ...) as well as
# a module (python -m plugins.extension_repair.tool ...).
if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from plugins.extension_repair.config import build_settings, save_persistent_config
    from shared.logger import BufferedLogger
    from plugins.extension_repair.worker import ExtensionRepairWorker
    from plugins.extension_repair.diagnostics import generate_summary
else:
    from .config import build_settings, save_persistent_config
    from shared.logger import BufferedLogger
    from .worker import ExtensionRepairWorker
    from .diagnostics import generate_summary


# ------------------------------------------------------------
# Constants
# ------------------------------------------------------------
CONFIG_FILE = "extension_repair.json"

# ------------------------------------------------------------
# Web UI Configuration (for dynamic GUI generation)
# ------------------------------------------------------------
webui_config = {
    "actions": [
        {
            "id": "scan",
            "name": "Scan & Repair",
            "description": "Scan a directory and fix file extensions based on magic bytes.",
            "fields": [
                {"id": "directory", "name": "Target Directory", "type": "directory", "required": True},
                {"id": "dry_run", "name": "Dry Run (preview only)", "type": "checkbox", "default": True},
                {"id": "force", "name": "Force ambiguous renames", "type": "checkbox", "default": False},
                {"id": "quarantine", "name": "Quarantine mode", "type": "checkbox", "default": False},
            ],
            "command": "extension-repair {directory} --mode cli",
        },
        {
            "id": "report",
            "name": "Report Only",
            "description": "Generate a report without making changes.",
            "fields": [
                {"id": "directory", "name": "Target Directory", "type": "directory", "required": True},
            ],
            "command": "extension-repair {directory} --mode cli --report",
        },
    ]
}


# ------------------------------------------------------------
# CLI runner
# ------------------------------------------------------------
def run_cli(settings, logger):
    """
    Run the tool in CLI mode.
    """
    logger.log("Starting Extension Repair Tool (CLI mode)")

    use_console_ui = bool(settings.get("CONSOLE_UI")) and sys.stdout.isatty() and sys.stdin.isatty()

    if use_console_ui:
        try:
            from tui import run_fixed_log_ui
        except ImportError:
            # Fallback if tui.py is not found or curses fails
            try:
                from .tui import run_fixed_log_ui
            except ImportError:
                print("[WARN] TUI module not found, falling back to text mode.", flush=True)
                use_console_ui = False

    if use_console_ui:
        # Queues for UI
        log_queue = Queue()
        event_queue = Queue()

        # Route all log lines into the UI and avoid direct printing.
        logger.on_line = log_queue.put
        logger.mirror = False
        logger.suppress_console = True

        worker = ExtensionRepairWorker(settings=settings, logger=logger, queue=event_queue)
        worker.start()

        def _on_done(stats):
            # Generate summary while UI is still visible.
            generate_summary(stats, settings["DIAGNOSTIC_LEVEL"], logger)
            logger.flush()
            logger.log("Done.")

        run_fixed_log_ui(
            log_queue=log_queue,
            event_queue=event_queue,
            log_height=int(settings.get("CONSOLE_UI_HEIGHT", 12) or 12),
            title="Extension Repair (CLI)",
            on_done=_on_done,
        )

        worker.join()
        logger.flush()
        return

    # Plain CLI (no curses)
    worker = ExtensionRepairWorker(settings=settings, logger=logger, queue=None)
    worker.start()
    worker.join()

    # Generate summary
    generate_summary(worker.stats, settings["DIAGNOSTIC_LEVEL"], logger)
    logger.flush()

    print("\nDone.\n", flush=True)


# ------------------------------------------------------------
# GUI runner
# ------------------------------------------------------------
def run_gui(settings, logger):
    """
    Run the tool in GUI mode.

    GUI is provided via the browser-based toolbox web UI.
    """
    logger.log("Starting Extension Repair Tool (GUI mode via webui)")
    try:
        import toolbox.webui
        toolbox.webui.launch_gui(selected_tool="extension_repair")
    except Exception as e:
        logger.log(f"[ERROR] Failed to launch web UI: {e}")
        raise


# ------------------------------------------------------------
# Main entry point
# ------------------------------------------------------------
def run(mode="cli", overrides=None, config_dir=None):
    """
    Main entry point used by the toolbox.

    Parameters:
        mode: "cli" or "gui"
        overrides: dict of settings overrides from toolbox
        config_dir: directory where persistent config is stored
    """
    if mode == "gui":
        # For GUI, prefer the browser web UI and avoid building tool-specific tkinter UI.
        try:
            import toolbox.webui
            toolbox.webui.launch_gui(selected_tool="extension_repair")
            return
        except Exception:
            # Fall back to normal settings path if webui can't be imported.
            pass

    if config_dir is None:
        # Toolbox passes this automatically
        config_dir = os.path.join(os.getcwd(), "config")

    # --------------------------------------------------------
    # Load settings
    # --------------------------------------------------------
    settings = build_settings(
        config_dir=config_dir,
        config_file=CONFIG_FILE,
        overrides=overrides,
    )

    # --------------------------------------------------------
    # Prepare log file
    # --------------------------------------------------------
    if not settings["UNDO_LOG"]:
        log_path = os.path.join(settings["TARGET_DIRECTORY"], "extension_repair.log")
    else:
        log_path = settings["UNDO_LOG"]

    logger = BufferedLogger(
        log_path=log_path,
        mirror_to_console=settings["LOG_TO_CONSOLE"],
        log_format=settings.get("LOG_FORMAT", "text"),
    )

    # --------------------------------------------------------
    # Save updated settings
    # --------------------------------------------------------
    save_persistent_config(config_dir, CONFIG_FILE, settings)

    # --------------------------------------------------------
    # Run mode
    # --------------------------------------------------------
    if mode == "gui":
        run_gui(settings, logger)
    elif mode == "tui":
        # Force console UI for TUI mode
        settings["CONSOLE_UI"] = True
        run_cli(settings, logger)
    else:
        run_cli(settings, logger)


# ------------------------------------------------------------
# Standardized entry point for toolbox + direct execution
# ------------------------------------------------------------
def register_cli(subparsers):
    """
    Register this tool with the toolbox CLI.
    """
    parser = subparsers.add_parser("extension-repair", help="Extension Repair Tool")
    _add_arguments(parser)
    parser.set_defaults(func=_run_from_args)


def _add_arguments(parser):
    parser.add_argument("directory", nargs="?", help="Target directory to scan")
    parser.add_argument(
        "-m",
        "--mode",
        choices=["gui", "cli"],
        default="gui",
        help="Run mode (default: gui). GUI opens the browser-based web UI.",
    )
    parser.add_argument("--config-dir", help="Config directory")
    parser.add_argument("-y", "--yes", dest="non_interactive", action="store_true", help="Non-interactive mode")
    parser.add_argument("--out", dest="OUTPUT_DIRECTORY", help="Output directory (for non-in-place mode)")
    parser.add_argument("-n", "--dry-run", dest="DRY_RUN", action="store_true", help="Preview changes only")
    parser.add_argument("--commit", dest="DRY_RUN", action="store_false", help="Actually make changes")
    parser.add_argument("--report", dest="REPORT_ONLY", action="store_true", help="Report only, no renames")
    parser.add_argument("--quarantine", dest="QUARANTINE_MODE", action="store_true", help="Move to quarantine instead")
    parser.add_argument("-f", "--force", dest="FORCE_RENAME", action="store_true", help="Force ambiguous renames")
    parser.add_argument("-t", "--threads", dest="THREAD_COUNT", type=int, help="Worker threads")
    parser.add_argument("--console-ui", dest="CONSOLE_UI", action="store_true", help="Show split-pane console UI")
    parser.add_argument("--json", dest="LOG_FORMAT", action="store_const", const="jsonl", help="JSON log output")


def _run_from_args(args):
    overrides = {}
    
    # Handle positional directory argument
    if args.directory:
        overrides["TARGET_DIRECTORY"] = args.directory
        overrides["IN_PLACE"] = True  # Default to in-place when dir specified
    
    for key in (
        "OUTPUT_DIRECTORY",
        "DRY_RUN",
        "REPORT_ONLY",
        "QUARANTINE_MODE",
        "FORCE_RENAME",
        "THREAD_COUNT",
        "LOG_FORMAT",
        "CONSOLE_UI",
    ):
        val = getattr(args, key, None)
        if val is not None:
            overrides[key] = val

    if args.non_interactive:
        overrides["INTERACTIVE_MODE"] = False

    run(mode=args.mode, overrides=overrides if overrides else None, config_dir=args.config_dir)


def main():
    """
    Standard entry point so the master toolbox launcher can call this tool.
    """
    parser = argparse.ArgumentParser(description="Extension Repair Tool")
    _add_arguments(parser)
    args = parser.parse_args()
    _run_from_args(args)


if __name__ == "__main__":
    main()
