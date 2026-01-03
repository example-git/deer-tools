#!/usr/bin/env python3
"""
Shared tool parsing and command building utilities.

This module contains functions shared between textui.py, webui.py, and other
UI components to ensure parity when working with tool modules.

Functions:
- discover_tools() - Scan for tools with metadata.json
- get_tool_webui_config() - Load webui_config from a tool module
- get_field_placeholder() - Get placeholder text for form fields
- build_command_from_action() - Build CLI command from action config

Also re-exports from shared module:
- iter_files, collect_files_chunked - Directory scanning utilities
- BaseWorker - Base class for threaded workers
"""

from __future__ import annotations

import importlib
import json
import os
import re
import shlex
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

# Re-export shared utilities for convenience
from shared import (
    DEFAULT_CHUNK_SIZE,
    BaseWorker,
    FunctionWorker,
    ProgressInfo,
    WorkerState,
    collect_files,
    collect_files_chunked,
    collect_files_filtered,
    count_files,
    iter_files,
    iter_files_chunked,
    iter_files_filtered,
)

__all__ = [
    "iter_files",
    "iter_files_chunked",
    "collect_files",
    "collect_files_chunked",
    "iter_files_filtered",
    "collect_files_filtered",
    "count_files",
    "DEFAULT_CHUNK_SIZE",
    "BaseWorker",
    "FunctionWorker",
    "WorkerState",
    "ProgressInfo",
    "set_global_threads",
    "get_global_threads",
    "discover_tools",
    "get_tool_webui_config",
    "get_tool_module",
    "get_field_placeholder",
    "build_command_from_action",
    "extract_form_values",
    "get_action_by_id",
    "split_command",
    "parse_progress",
    "format_progress_bar",
]


# ---------------------------------------------------------------------------
# Global Configuration
# ---------------------------------------------------------------------------

# Default number of threads for parallel operations
# Can be set via set_global_threads() or --threads CLI arg
_GLOBAL_THREADS: int = 8


def set_global_threads(n: int) -> None:
    """Set the global thread count for all tool operations."""
    # pylint: disable=global-statement
    global _GLOBAL_THREADS
    _GLOBAL_THREADS = max(1, n)


def get_global_threads() -> int:
    """Get the current global thread count."""
    return _GLOBAL_THREADS


# ---------------------------------------------------------------------------
# Tool Discovery
# ---------------------------------------------------------------------------


def discover_tools(base_dir: Optional[str] = None) -> Dict[str, dict]:
    """
    Scan subdirectories for metadata.json and return discovered tools.

    Args:
        base_dir: Directory to scan. Defaults to script directory.

    Returns:
        Dict mapping tool_id -> metadata dict (includes _dir, _path keys)
    """
    if base_dir is None:
        base_dir = str(Path(__file__).resolve().parent.parent / "plugins")

    tools: Dict[str, dict] = {}

    for item in os.listdir(base_dir):
        item_path = os.path.join(base_dir, item)
        if not os.path.isdir(item_path):
            continue
        if item.startswith(".") or item.startswith("__"):
            continue

        meta_path = os.path.join(item_path, "metadata.json")
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                # Store internal references
                meta["_dir"] = item
                meta["_path"] = item_path
                tool_id = meta.get("id", item)
                tools[tool_id] = meta
            except Exception:  # pylint: disable=broad-exception-caught
                pass

    return tools


# ---------------------------------------------------------------------------
# Config Loading
# ---------------------------------------------------------------------------


def get_tool_webui_config(tool_id: str, tools: Dict[str, dict]) -> Optional[dict]:
    """
    Load webui_config from a tool's module.

    Args:
        tool_id: ID of the tool (from metadata)
        tools: Dict of discovered tools (from discover_tools())

    Returns:
        webui_config dict if found, else None
    """
    meta = tools.get(tool_id)
    if not meta:
        return None

    tool_dir = meta.get("_dir", tool_id)
    try:
        mod = importlib.import_module(f"plugins.{tool_dir}.tool")
        return getattr(mod, "webui_config", None)
    except Exception:  # pylint: disable=broad-exception-caught
        return None


def get_tool_module(tool_id: str, tools: Dict[str, dict]) -> Optional[Any]:
    """
    Import and return a tool's module.

    Args:
        tool_id: ID of the tool (from metadata)
        tools: Dict of discovered tools (from discover_tools())

    Returns:
        Imported module if found, else None
    """
    meta = tools.get(tool_id)
    if not meta:
        return None

    tool_dir = meta.get("_dir", tool_id)
    try:
        return importlib.import_module(f"plugins.{tool_dir}.tool")
    except Exception:  # pylint: disable=broad-exception-caught
        return None


# ---------------------------------------------------------------------------
# Field Placeholders
# ---------------------------------------------------------------------------

# ID-based placeholders (more specific)
FIELD_ID_PLACEHOLDERS = {
    "directory": "~/Documents",
    "database": "./database.sqlite",
    "db": "./hash.db",
    "output": "./output.txt",
    "output_dir": "./output/",
    "log": "./transfer.log",
    "temp": os.path.join(tempfile.gettempdir(), "source"),
    "restore": "~/restored",
    "hash": "sha256",
}

# Type-based placeholders (fallback)
FIELD_TYPE_PLACEHOLDERS = {
    "directory": "/path/to/directory",
    "file": "/path/to/file",
    "select": "",
}


def get_field_placeholder(field: dict) -> str:
    """
    Get a placeholder/example for a field based on its type and id.

    Args:
        field: Field definition dict with keys: id, type, default, etc.

    Returns:
        Placeholder string for the field
    """
    fid = field.get("id", "")
    ftype = field.get("type", "text")
    fdefault = field.get("default", "")

    # Return default if set (non-checkbox)
    if fdefault and ftype != "checkbox":
        return str(fdefault)

    # Check ID-based placeholders first (more specific)
    if fid in FIELD_ID_PLACEHOLDERS:
        return FIELD_ID_PLACEHOLDERS[fid]

    # Fall back to type-based placeholders
    if ftype in FIELD_TYPE_PLACEHOLDERS:
        return FIELD_TYPE_PLACEHOLDERS[ftype]

    return ""


# ---------------------------------------------------------------------------
# Command Building
# ---------------------------------------------------------------------------


def build_command_from_action(
    tool_id: str,
    action: dict,
    field_values: Dict[str, Any],
    python_exe: Optional[str] = None,
    toolbox_script: str = "toolbox.py",
    threads: Optional[int] = None,
) -> str:
    """
    Build a CLI command from action config and field values.

    Uses the 'command' template from action if available, otherwise builds
    command from fields. The template can contain {field_id} placeholders.

    Args:
        tool_id: ID of the tool
        action: Action dict from webui_config
        field_values: Dict mapping field_id -> value
        python_exe: Python executable path (defaults to sys.executable)
        toolbox_script: Name of toolbox script (default: "toolbox.py")
        threads: Number of threads to use (defaults to global setting)

    Returns:
        Complete shell command string
    """
    if python_exe is None:
        python_exe = sys.executable
    py = shlex.quote(python_exe)

    if threads is None:
        threads = _GLOBAL_THREADS

    cli_name = tool_id.replace("_", "-")

    # Check if action has a command template
    cmd_template = action.get("command", "")

    if cmd_template:
        return _build_from_template(
            py, toolbox_script, action, field_values, cmd_template, threads
        )
    else:
        return _build_from_fields(
            py, toolbox_script, cli_name, action, field_values, threads
        )


def _expand_path(value: Any) -> str:
    """Expand user home (~) and environment variables in paths."""
    if not isinstance(value, str):
        return str(value) if value else ""
    # Expand ~ to user's home directory
    expanded = os.path.expanduser(value)
    # Also expand environment variables like $HOME
    expanded = os.path.expandvars(expanded)
    return expanded


def _build_from_template(
    py: str,
    toolbox_script: str,
    action: dict,
    field_values: Dict[str, Any],
    cmd_template: str,
    threads: int,
) -> str:
    """Build command using a template with {field_id} placeholders."""
    cmd = cmd_template

    # Replace placeholders with actual values (with path expansion)
    for field in action.get("fields", []):
        fid = field.get("id", "")
        value = _expand_path(field_values.get(fid, ""))
        placeholder = "{" + fid + "}"

        if placeholder in cmd:
            if value:
                cmd = cmd.replace(placeholder, shlex.quote(value))
            else:
                # Remove unfilled placeholders
                cmd = cmd.replace(placeholder, "")

    # Build final command with python and toolbox prefix
    cmd_parts = [py, toolbox_script]
    cmd_parts.extend(cmd.split())

    # Add optional flags that aren't in the template
    for field in action.get("fields", []):
        fid = field.get("id", "")
        ftype = field.get("type", "text")
        value = _expand_path(field_values.get(fid, ""))
        placeholder = "{" + fid + "}"

        # Skip fields already in the template
        if placeholder in action.get("command", ""):
            continue

        if ftype == "checkbox":
            if field_values.get(fid):  # Checkbox was checked (use original bool)
                flag_name = f"--{fid.replace('_', '-')}"
                cmd_parts.append(flag_name)
        elif value:
            flag_name = f"--{fid.replace('_', '-')}"
            cmd_parts.append(flag_name)
            cmd_parts.append(shlex.quote(value))

    # Always add --threads if not already specified in field values
    if "threads" not in field_values:
        cmd_parts.append("--threads")
        cmd_parts.append(str(threads))

    return " ".join(cmd_parts)


def _build_from_fields(
    py: str,
    toolbox_script: str,
    cli_name: str,
    action: dict,
    field_values: Dict[str, Any],
    threads: int,
) -> str:
    """Build command from fields (legacy behavior when no template)."""
    cmd_parts = [py, toolbox_script, cli_name]

    for field in action.get("fields", []):
        fid = field.get("id", "")
        ftype = field.get("type", "text")
        raw_value = field_values.get(fid, "")
        value = _expand_path(raw_value)

        if ftype == "checkbox":
            if raw_value:  # Checkbox was checked (use original bool)
                flag_name = f"--{fid.replace('_', '-')}"
                cmd_parts.append(flag_name)
        elif value:
            # Positional args for common fields
            if fid in ("directory", "database", "output"):
                cmd_parts.append(shlex.quote(value))
            else:
                flag_name = f"--{fid.replace('_', '-')}"
                cmd_parts.append(flag_name)
                cmd_parts.append(shlex.quote(value))

    # Always add --threads if not already specified
    if "threads" not in field_values:
        cmd_parts.append("--threads")
        cmd_parts.append(str(threads))

    return " ".join(cmd_parts)


# ---------------------------------------------------------------------------
# Utility Functions
# ---------------------------------------------------------------------------


def extract_form_values(
    action: dict, form_data: Dict[str, List[str]]
) -> Dict[str, Any]:
    """
    Extract field values from form data (like HTTP POST).

    Args:
        action: Action dict from webui_config
        form_data: Dict mapping field names to list of values (HTTP-style)

    Returns:
        Dict mapping field_id -> value (string or bool for checkboxes)
    """
    field_values: Dict[str, Any] = {}

    for field in action.get("fields", []):
        fid = field.get("id", "")
        ftype = field.get("type", "text")

        if ftype == "checkbox":
            field_values[fid] = fid in form_data  # True if present
        else:
            values = form_data.get(fid, [""])
            field_values[fid] = values[0].strip() if values else ""

    return field_values


def get_action_by_id(webui_config: dict, action_id: str) -> Optional[dict]:
    """
    Find an action by ID in a webui_config.

    Args:
        webui_config: webui_config dict from a tool module
        action_id: ID of the action to find

    Returns:
        Action dict if found, else None
    """
    for action in webui_config.get("actions", []):
        if action.get("id") == action_id:
            return action
    return None


def split_command(cmd: str) -> List[str]:
    """
    Split a shell command string into a list of arguments.

    Handles platform-specific quoting (POSIX vs Windows).

    Args:
        cmd: Command string to split

    Returns:
        List of command arguments
    """
    cmd = (cmd or "").strip()
    if not cmd:
        return []

    # Windows quoting rules differ
    posix = os.name != "nt"
    return shlex.split(cmd, posix=posix)


# ---------------------------------------------------------------------------
# Progress Parsing
# ---------------------------------------------------------------------------

# Patterns to detect progress in output lines
PROGRESS_PATTERNS = [
    # [XXX%] message or [ XX%] message
    re.compile(r"^\[?\s*(\d{1,3})%\]?\s*(.*)$"),
    # XX% complete, XX% done, etc.
    re.compile(r"^.*?(\d{1,3})%\s*(?:complete|done|finished)?.*$", re.IGNORECASE),
    # Progress: XX/YY or XX of YY
    re.compile(r".*?(\d+)\s*(?:/|of)\s*(\d+).*", re.IGNORECASE),
    # Processed X of Y files
    re.compile(
        r".*?(?:processed|completed|finished)\s+(\d+)\s+(?:of|/)\s+(\d+).*",
        re.IGNORECASE,
    ),
]


def parse_progress(line: str) -> Optional[Dict[str, Any]]:
    """
    Parse a line of output to extract progress information.

    Args:
        line: A line of output text

    Returns:
        Dict with keys: percent (0-100), message, current, total
        Or None if no progress found
    """
    line = line.strip()
    if not line:
        return None

    # Try percentage patterns first
    for pattern in PROGRESS_PATTERNS[:2]:
        match = pattern.match(line)
        if match:
            try:
                percent = int(match.group(1))
                if 0 <= percent <= 100:
                    message = match.group(2).strip() if len(match.groups()) > 1 else ""
                    return {
                        "percent": percent,
                        "message": message or line,
                        "current": None,
                        "total": None,
                    }
            except (ValueError, IndexError):
                continue

    # Try X/Y or X of Y patterns
    for pattern in PROGRESS_PATTERNS[2:]:
        match = pattern.search(line)
        if match:
            try:
                current = int(match.group(1))
                total = int(match.group(2))
                if total > 0:
                    percent = min(100, int(current * 100 / total))
                    return {
                        "percent": percent,
                        "message": line,
                        "current": current,
                        "total": total,
                    }
            except (ValueError, IndexError):
                continue

    return None


def format_progress_bar(
    percent: int, width: int = 30, filled_char: str = "█", empty_char: str = "░"
) -> str:
    """
    Create a text-based progress bar.

    Args:
        percent: Progress percentage (0-100)
        width: Width of the bar in characters
        filled_char: Character for filled portion
        empty_char: Character for empty portion

    Returns:
        Progress bar string like "████████░░░░░░░░░░░░ 40%"
    """
    percent = max(0, min(100, percent))
    filled = int(width * percent / 100)
    empty = width - filled
    bar = filled_char * filled + empty_char * empty
    return f"{bar} {percent:3d}%"


def estimate_eta(start_time: float, percent: int) -> Optional[str]:
    """
    Estimate time remaining based on progress.

    Args:
        start_time: Unix timestamp when task started
        percent: Current progress percentage

    Returns:
        ETA string like "2m 30s remaining" or None
    """
    import time

    if percent <= 0:
        return None

    elapsed = time.time() - start_time
    if elapsed <= 0:
        return None

    # Estimate total time and remaining
    estimated_total = elapsed * 100 / percent
    remaining = estimated_total - elapsed

    if remaining <= 0:
        return "almost done"

    if remaining < 60:
        return f"{int(remaining)}s remaining"
    elif remaining < 3600:
        mins = int(remaining // 60)
        secs = int(remaining % 60)
        return f"{mins}m {secs}s remaining"
    else:
        hours = int(remaining // 3600)
        mins = int((remaining % 3600) // 60)
        return f"{hours}h {mins}m remaining"
