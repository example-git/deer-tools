"""
config.py
---------

Configuration system for the upgraded Extension Repair Tool.

Supports:
- Default settings
- Persistent config stored in toolbox/config/extension_repair.json
- Toolbox-provided overrides
- Interactive fallback when settings are missing
- Validation and normalization of paths
"""

import os

from shared.config import (
    build_settings as shared_build_settings,
    load_persistent_config as shared_load_persistent_config,
    save_persistent_config as shared_save_persistent_config,
)


# ------------------------------------------------------------
# Default settings
# ------------------------------------------------------------
DEFAULTS = {
    # Core behavior
    "TARGET_DIRECTORY": "",
    "IN_PLACE": True,
    "OUTPUT_DIRECTORY": "",

    # Modes
    "DRY_RUN": True,
    "REPORT_ONLY": False,
    "QUARANTINE_MODE": False,
    "FORCE_RENAME": False,
    "SKIP_AMBIGUOUS_ISO": True,

    # Diagnostics
    "DIAGNOSTIC_LEVEL": 2,  # 1=Standard, 2=Deep, 3=Forensic
    "SHOW_PREVIEW": True,

    # Logging
    "UNDO_LOG": "",
    "LOG_TO_CONSOLE": False,
    "LOG_FORMAT": "text",  # "text" or "jsonl"

    # Console UI (optional curses TUI)
    "CONSOLE_UI": False,
    "CONSOLE_UI_HEIGHT": 12,

    # Performance
    "THREAD_COUNT": 8,

    # Interactive fallback
    "INTERACTIVE_MODE": True,
}


# ------------------------------------------------------------
# Interactive helpers
# ------------------------------------------------------------
def prompt_path(label, default):
    while True:
        v = input(f"{label} [{default}]: ").strip()
        if not v:
            v = default
        if v and os.path.exists(v):
            return os.path.normpath(v)
        print("Path does not exist. Try again.")


def prompt_yes_no(label, default):
    d = "y" if default else "n"
    v = input(f"{label} [Y/n]:" if default else f"{label} [y/N]:").strip().lower()
    if not v:
        return default
    if v in ("y", "yes"):
        return True
    if v in ("n", "no"):
        return False
    return default


def prompt_int(label, default):
    v = input(f"{label} [{default}]: ").strip()
    if not v:
        return default
    try:
        return int(v)
    except:
        return default


def prompt_choice(label, default):
    v = input(f"{label} [{default}]: ").strip()
    if v in ("1", "2", "3"):
        return int(v)
    return default


# ------------------------------------------------------------
# Merge settings
# ------------------------------------------------------------
def load_persistent_config(config_dir, config_file):
    """Thin wrapper around shared config loader for compatibility."""
    return shared_load_persistent_config(config_name=config_file, config_dir=config_dir)


def save_persistent_config(config_dir, config_file, settings):
    """Thin wrapper around shared config saver for compatibility."""
    return shared_save_persistent_config(settings, config_name=config_file, config_dir=config_dir)


def _interactive_update(settings):
    if not settings.get("INTERACTIVE_MODE", True):
        return settings

    settings["TARGET_DIRECTORY"] = prompt_path(
        "Directory to scan", settings["TARGET_DIRECTORY"]
    )

    settings["IN_PLACE"] = prompt_yes_no(
        "Repair files in place", settings["IN_PLACE"]
    )

    if not settings["IN_PLACE"]:
        settings["OUTPUT_DIRECTORY"] = prompt_path(
            "Output directory", settings["OUTPUT_DIRECTORY"]
        )

    settings["DRY_RUN"] = prompt_yes_no(
        "Dry run only", settings["DRY_RUN"]
    )

    settings["REPORT_ONLY"] = prompt_yes_no(
        "Report only (no renames)", settings["REPORT_ONLY"]
    )

    settings["QUARANTINE_MODE"] = prompt_yes_no(
        "Enable quarantine mode", settings["QUARANTINE_MODE"]
    )

    settings["FORCE_RENAME"] = prompt_yes_no(
        "Force rename even if ambiguous", settings["FORCE_RENAME"]
    )

    settings["SKIP_AMBIGUOUS_ISO"] = prompt_yes_no(
        "Skip ambiguous ISO BMFF files", settings["SKIP_AMBIGUOUS_ISO"]
    )

    settings["THREAD_COUNT"] = prompt_int(
        "Number of threads", settings["THREAD_COUNT"]
    )

    settings["DIAGNOSTIC_LEVEL"] = prompt_choice(
        "Diagnostic level (1=Standard, 2=Deep, 3=Forensic)",
        settings["DIAGNOSTIC_LEVEL"]
    )

    # Normalize paths
    if settings["TARGET_DIRECTORY"]:
        settings["TARGET_DIRECTORY"] = os.path.normpath(settings["TARGET_DIRECTORY"])

    if settings["OUTPUT_DIRECTORY"]:
        settings["OUTPUT_DIRECTORY"] = os.path.normpath(settings["OUTPUT_DIRECTORY"])

    return settings


def build_settings(config_dir, config_file, overrides=None):
    return shared_build_settings(
        defaults=DEFAULTS,
        overrides=overrides or {},
        config_dir=config_dir,
        config_name=config_file,
        interactive_fn=_interactive_update,
    )