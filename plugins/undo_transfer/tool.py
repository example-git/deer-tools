"""
tool.py
-------

Unified entry point for the Undo Transfer Tool.

Supports:
- GUI mode
- CLI mode
- Interactive fallback
- Toolbox-provided settings
- Persistent config loading/saving

The toolbox should call:

    from plugins.undo_transfer.tool import run
    run(mode="gui")   # or run(mode="cli")
"""

import os
import sys
import argparse
from .config import build_settings, save_persistent_config
from .restorer import UndoWorker

# ------------------------------------------------------------
# Web UI Configuration (for dynamic GUI generation)
# ------------------------------------------------------------
webui_config = {
    "actions": [
        {
            "id": "restore",
            "name": "Restore Files",
            "description": "Restore files to their original locations using a transfer log.",
            "fields": [
                {"id": "log", "name": "Transfer Log File", "type": "file", "required": True},
                {"id": "temp", "name": "Temp Directory (source files)", "type": "directory", "required": True},
                {"id": "restore", "name": "Restore Root (destination)", "type": "directory", "required": True},
                {"id": "dry_run", "name": "Dry Run (preview only)", "type": "checkbox", "default": True},
            ],
            "command": "undo-transfer --mode cli --log {log} --temp {temp} --restore {restore}",
        },
    ]
}

# -------------------------------------------------------------------
# Helper: ensure undo log exists
# -------------------------------------------------------------------

def _ensure_undo_log(settings):
    undo_log = settings["UNDO_LOG"]

    # Always ensure a valid log path
    if not undo_log or undo_log.strip() == "":
        undo_log = os.path.join(settings["TEMP_DIRECTORY"], "undo_transfer.log")
        settings["UNDO_LOG"] = undo_log

    undo_dir = os.path.dirname(undo_log)
    if undo_dir and not os.path.exists(undo_dir):
        os.makedirs(undo_dir, exist_ok=True)

    if not os.path.exists(undo_log):
        open(undo_log, "w", encoding="utf-8").close()


from shared.progress import draw_progress_bar, finish_progress
import queue

def _run_cli(settings):
    print("=== Undo Transfer Tool (CLI Mode) ===", flush=True)
    print("Effective settings:", flush=True)
    for k, v in settings.items():
        print(f"  {k}: {v}", flush=True)
    print(flush=True)

    # Create a queue for progress updates
    progress_queue = queue.Queue()

    # Start worker
    worker = UndoWorker(settings, progress_queue)
    worker.start()

    # Process progress events
    while worker.is_alive():
        try:
            msg_type, payload = progress_queue.get(timeout=0.1)

            if msg_type == "index_progress":
                fraction, text = payload
                draw_progress_bar(fraction, text)

            elif msg_type == "restore_progress":
                fraction, text = payload
                draw_progress_bar(fraction, text)

            elif msg_type == "done":
                finish_progress("Undo transfer completed.")
                break

        except queue.Empty:
            pass

    worker.join()
    print("\n=== Undo Transfer Complete ===", flush=True)
    print(f"Undo log written to: {settings['UNDO_LOG']}", flush=True)


# -------------------------------------------------------------------
# GUI mode
# -------------------------------------------------------------------

def _run_gui(settings):
    """
    Launch the GUI.

    GUI is provided via the browser-based toolbox web UI.
    """
    try:
        import toolbox.webui
        toolbox.webui.launch_gui(selected_tool="undo_transfer")
    except Exception as e:
        print(f"[ERROR] Failed to launch web UI: {e}", flush=True)
        raise


# -------------------------------------------------------------------
# Main entry point
# -------------------------------------------------------------------

def run(mode="gui", settings=None, config_dir=None, config_file="undo_transfer.json"):
    """
    Unified entry point for the Undo Transfer Tool.

    Args:
        mode (str): "gui" or "cli"
        settings (dict): Toolbox-provided overrides (optional)
        config_dir (str): Directory where persistent config is stored
        config_file (str): Name of persistent config file

    Behavior:
        - Load persistent config
        - Merge toolbox overrides
        - If interactive mode is enabled and required fields are missing,
          prompt the user
        - Save updated persistent config
        - Run in GUI or CLI mode
    """

    # Default config directory if not provided
    if config_dir is None:
        # Toolbox structure: toolbox/config/<tool>.json
        config_dir = os.path.join(os.path.dirname(__file__), "..", "..", "config")
        config_dir = os.path.normpath(config_dir)

    mode = (mode or "gui").lower()

    if mode == "gui":
        # Prefer browser UI; avoid tkinter-based UIs.
        _run_gui({})
        return

    # Build final settings for non-GUI modes
    final_settings = build_settings(config_dir, config_file, overrides=settings)
    save_persistent_config(config_dir, config_file, final_settings)

    if mode in ("cli", "tui"):
        _run_cli(final_settings)
    else:
        _run_cli(final_settings)

 
# ------------------------------------------------------------
# Standardized entry point for toolbox + direct execution
# ------------------------------------------------------------
def register_cli(subparsers):
    """
    Register this tool with the toolbox CLI.
    """
    parser = subparsers.add_parser("undo-transfer", help="Undo Transfer Tool")
    _add_arguments(parser)
    parser.set_defaults(func=_run_from_args)


def _add_arguments(parser):
    parser.add_argument(
        "-m",
        "--mode",
        choices=["gui", "cli"],
        default="gui",
        help="Run mode (default: gui). GUI opens the browser-based web UI.",
    )
    parser.add_argument("--config-dir", help="Config directory")
    parser.add_argument("-y", "--yes", dest="non_interactive", action="store_true", help="Non-interactive mode")
    parser.add_argument("--log", dest="LOG_FILE", help="Transfer log file path")
    parser.add_argument("--temp", dest="TEMP_DIRECTORY", help="Temp directory with files")
    parser.add_argument("--restore", dest="RESTORE_ROOT", help="Restore output directory")
    parser.add_argument("-n", "--dry-run", dest="DRY_RUN", action="store_true", help="Preview only")
    parser.add_argument("--commit", dest="DRY_RUN", action="store_false", help="Actually restore files")
    parser.add_argument("-t", "--threads", dest="THREAD_COUNT", type=int, help="Worker threads")
    parser.add_argument("--hash", dest="HASH_TYPE", choices=["md5", "sha256"], default="sha256", help="Hash algorithm (default: sha256)")


def _run_from_args(args):
    overrides = {}
    for key in (
        "LOG_FILE",
        "TEMP_DIRECTORY",
        "RESTORE_ROOT",
        "DRY_RUN",
        "THREAD_COUNT",
        "HASH_TYPE",
    ):
        val = getattr(args, key, None)
        if val is not None:
            overrides[key] = val

    if args.non_interactive:
        overrides["INTERACTIVE_MODE"] = False

    run(mode=args.mode, settings=overrides if overrides else None, config_dir=args.config_dir)


def main():
    """
    Standard entry point so the master toolbox launcher can call this tool.
    """
    parser = argparse.ArgumentParser(description="Undo Transfer Tool")
    _add_arguments(parser)
    args = parser.parse_args()
    _run_from_args(args)


if __name__ == "__main__":
    main()
