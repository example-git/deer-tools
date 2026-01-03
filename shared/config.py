"""
shared.config
-------------

Common configuration management utilities.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


def get_config_dir() -> Path:
    """Return the default config directory (~/.config/deer-toolbox)."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path.home() / ".config"
    return base / "deer-toolbox"


def load_persistent_config(
    config_name: str = "config.json", config_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """Load a JSON config file from the given or default config directory."""

    base_dir = Path(config_dir) if config_dir else get_config_dir()
    config_path = base_dir / config_name

    if not config_path.exists():
        return {}

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, UnicodeDecodeError, ValueError, TypeError):
        return {}


def save_persistent_config(
    config: Dict[str, Any],
    config_name: str = "config.json",
    *,
    config_dir: Optional[Path] = None,
) -> bool:
    """Persist a config dict to disk in the given or default directory."""

    base_dir = Path(config_dir) if config_dir else get_config_dir()
    base_dir.mkdir(parents=True, exist_ok=True)

    config_path = base_dir / config_name

    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        return True
    except (OSError, UnicodeEncodeError, ValueError, TypeError):
        return False


def merge_settings(
    *,
    defaults: Optional[Dict[str, Any]] = None,
    persistent: Optional[Dict[str, Any]] = None,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Merge defaults + persistent + overrides (overrides win)."""

    merged: Dict[str, Any] = {}

    if defaults:
        merged.update(defaults)

    if persistent:
        merged.update(persistent)

    if overrides:
        for key, value in overrides.items():
            if value is not None:
                merged[key] = value

    return merged


def build_settings(
    cli_args: Optional[Dict[str, Any]] = None,
    config_name: str = "config.json",
    *,
    config_dir: Optional[Path] = None,
    defaults: Optional[Dict[str, Any]] = None,
    overrides: Optional[Dict[str, Any]] = None,
    interactive_fn: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Build settings by loading persistence, applying defaults, and merging overrides.

    Backward-compatible: if only ``cli_args`` is provided, it behaves the same as
    the original implementation.
    """

    base_overrides = overrides if overrides is not None else cli_args or {}
    persistent = load_persistent_config(config_name=config_name, config_dir=config_dir)

    merged = merge_settings(
        defaults=defaults,
        persistent=persistent,
        overrides=base_overrides,
    )

    if callable(interactive_fn):
        return interactive_fn(merged)

    return merged
