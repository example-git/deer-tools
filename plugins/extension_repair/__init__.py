"""
extension_repair package
------------------------

Strict-Mode Extension Repair Tool (upgraded, toolbox-ready).

Features:
- Strict magic-byte based detection (no guessing)
- In-place or output-directory repairs
- Auto-resolving rename conflicts (_1, _2, ...)
- Report-only and quarantine modes
- Detailed diagnostics (Standard / Deep / Forensic)
- GUI and CLI entry points
- Persistent configuration with toolbox overrides

Primary entry point:

    from plugins.extension_repair.tool import run

GUI is provided via the browser-based toolbox web UI.
"""

__all__ = ["run"]


def run(*args, **kwargs):
    """Lazy import wrapper for the run function."""
    from .tool import run as _run
    return _run(*args, **kwargs)