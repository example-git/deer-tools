""" 
undo_transfer package
---------------------

This package provides a modular, toolbox-ready implementation of the
Undo Transfer Tool. It supports:

- GUI mode
- CLI mode
- Interactive fallback
- Persistent configuration
- Toolbox-provided configuration overrides

The main entry point is plugins.undo_transfer.tool.run().

GUI is provided via the browser-based toolbox web UI.
"""

__all__ = ["run"]


def run(*args, **kwargs):
    """Lazy import wrapper for the run function."""
    from .tool import run as _run
    return _run(*args, **kwargs)