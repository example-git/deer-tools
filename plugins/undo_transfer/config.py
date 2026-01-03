"""
config.py
---------

Configuration system for the Undo Transfer Tool.

Produces a clean, unified settings dictionary that the rest of the tool
can rely on.
"""

import os

from shared.config import (
    build_settings as shared_build_settings,
    load_persistent_config as shared_load_persistent_config,
    save_persistent_config as shared_save_persistent_config,
)

# -------------------------------------------------------------------
# Default settings
# -------------------------------------------------------------------

DEFAULTS = {
    "LOG_FILE": "",
    "TEMP_DIRECTORY": "",
    "ORIGINAL_ROOT": "",
    "RESTORE_ROOT": "",
    "TARGET_SUBFOLDERS": [],
    "AUTO_SCAN_SUBFOLDERS": True,
    "DRY_RUN": True,
    "THREAD_COUNT": 8,
    "UNDO_LOG": "",
    "CACHE_FILE": "",
    "HASH_TYPE": "md5",  # "md5" or "sha256"
    "INTERACTIVE_MODE": True,
}

def load_persistent_config(config_dir, config_file):
    """Thin wrapper around shared config loader for compatibility."""
    return shared_load_persistent_config(config_name=config_file, config_dir=config_dir)


def save_persistent_config(config_dir, config_file, settings):
    """Thin wrapper around shared config saver for compatibility."""
    return shared_save_persistent_config(settings, config_name=config_file, config_dir=config_dir)

# -------------------------------------------------------------------
# Interactive fallback
# -------------------------------------------------------------------

def interactive_prompt(default, label):
    prompt = f"{label} [{default}]: "
    value = input(prompt).strip()
    return value if value else default

def interactive_yes_no(default, label):
    prompt = f"{label} [Y/n]:" if default else f"{label} [y/N]:"
    value = input(prompt).strip().lower()

    if not value:
        return default
    if value in ("y", "yes"):
        return True
    if value in ("n", "no"):
        return False
    return default

def _customize_settings(settings, overrides=None):
    overrides = overrides or {}

    if settings.get("INTERACTIVE_MODE", True):
        settings["LOG_FILE"] = interactive_prompt(settings["LOG_FILE"], "Path to transfer log")
        settings["TEMP_DIRECTORY"] = interactive_prompt(settings["TEMP_DIRECTORY"], "Temp directory")
        settings["ORIGINAL_ROOT"] = interactive_prompt(settings["ORIGINAL_ROOT"], "Original root")
        settings["RESTORE_ROOT"] = interactive_prompt(settings["RESTORE_ROOT"], "Restore root")
        settings["DRY_RUN"] = interactive_yes_no(settings["DRY_RUN"], "Dry run mode")
        settings["AUTO_SCAN_SUBFOLDERS"] = interactive_yes_no(
            settings["AUTO_SCAN_SUBFOLDERS"],
            "Auto-scan first-level subfolders"
        )

        extra = input("Additional subfolders (comma-separated, optional): ").strip()
        if extra:
            parts = [p.strip() for p in extra.split(",") if p.strip()]
            settings["TARGET_SUBFOLDERS"].extend(parts)

        default_ht = settings.get("HASH_TYPE", "md5")
        ht = input(f"Hash type [{default_ht}]: ").strip().lower()
        if not ht:
            ht = default_ht
        if ht in ("md5", "sha256"):
            settings["HASH_TYPE"] = ht

    # If TEMP_DIRECTORY was explicitly overridden, clear dependent defaults unless explicitly overridden too.
    if overrides.get("TEMP_DIRECTORY"):
        if "UNDO_LOG" not in overrides:
            settings["UNDO_LOG"] = ""
        if "CACHE_FILE" not in overrides:
            settings["CACHE_FILE"] = ""
        if "LOG_FILE" not in overrides:
            settings["LOG_FILE"] = ""

    if settings["TEMP_DIRECTORY"]:
        os.makedirs(settings["TEMP_DIRECTORY"], exist_ok=True)

    if not settings["LOG_FILE"] and settings["TEMP_DIRECTORY"]:
        settings["LOG_FILE"] = os.path.join(settings["TEMP_DIRECTORY"], "transfer_log.txt")

    if not settings["UNDO_LOG"] and settings["TEMP_DIRECTORY"]:
        settings["UNDO_LOG"] = os.path.join(settings["TEMP_DIRECTORY"], "undo_transfer.log")
    
    if not settings["CACHE_FILE"] and settings["TEMP_DIRECTORY"]:
        settings["CACHE_FILE"] = os.path.join(settings["TEMP_DIRECTORY"], "md5_cache.json")

    for key in ("LOG_FILE", "TEMP_DIRECTORY", "ORIGINAL_ROOT", "RESTORE_ROOT", "UNDO_LOG", "CACHE_FILE"):
        if settings.get(key):
            settings[key] = os.path.normpath(settings[key])

    seen = set()
    deduped = []
    for t in settings["TARGET_SUBFOLDERS"]:
        key = t.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(t)
    settings["TARGET_SUBFOLDERS"] = deduped

    return settings


def build_settings(config_dir, config_file, overrides=None):
    return shared_build_settings(
        defaults=DEFAULTS,
        overrides=overrides or {},
        config_dir=config_dir,
        config_name=config_file,
        interactive_fn=lambda s: _customize_settings(s, overrides),
    )