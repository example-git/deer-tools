#!/usr/bin/env python3
"""desktopui.py

Electron-like desktop wrapper for the local Web UI.

Implementation:
- Uses `pywebview` (import name: `webview`) when installed to show a native window.
- Falls back to opening the system browser if `pywebview` is not available.

Install (recommended):
- `python -m pip install pywebview`

Notes:
- No bundling is performed here. For true app packaging, use PyInstaller
  with `pywebview` installed.
"""

# This module intentionally falls back across several UI backends.
# pylint: disable=broad-exception-caught

from __future__ import annotations

import os
import sys
from typing import Optional


def launch_desktop(selected_tool: Optional[str] = None) -> int:
    """Launch the toolbox GUI in a native window if possible.

    Args:
        selected_tool: Optional tool name to prefill in the web UI.

    Returns:
        Process exit code.
    """
    try:
        import webview  # pyright: ignore[reportMissingImports]  # pywebview
    except ImportError:
        # Fall back to browser-based UI.
        try:
            import toolbox.webui
            return toolbox.webui.launch_gui(selected_tool=selected_tool)
        except Exception as e:
            print(f"[ERROR] Cannot launch GUI: {e}")
            return 1

    try:
        import toolbox.webui
    except Exception as e:
        print(f"[ERROR] webui.py not available: {e}")
        return 1

    server, url = toolbox.webui.start_server(selected_tool=selected_tool, open_browser=False, background=True)
    debug = os.environ.get("TOOLBOX_DESKTOP_DEBUG", "").strip().lower() in ("1", "true", "yes")

    class Api:
        """Exposed to JS for window control."""
        def __init__(self, win):
            self._win = win

        def minimize(self):
            try:
                self._win.minimize()
            except Exception:
                pass

        def toggle_fullscreen(self):
            try:
                self._win.toggle_fullscreen()
            except Exception:
                pass

        def close(self):
            """Close window - use evaluate_js to avoid blocking on macOS."""
            import threading
            def _do_close():
                try:
                    self._win.destroy()
                except Exception:
                    pass
            # Run destroy in a separate thread to avoid blocking
            threading.Thread(target=_do_close, daemon=True).start()

    window = webview.create_window(
        "Toolbox",
        url,
        width=1100,
        height=760,
        frameless=True,
        draggable=True,
        )
    api = Api(window)
    window.expose(api.minimize, api.toggle_fullscreen, api.close)

    try:
        webview.start(debug=debug)
        return 0
    finally:
        try:
            toolbox.webui.stop_server(server)
        except Exception:
            pass


if __name__ == "__main__":
    # Optional: `python -m toolbox.desktopui hashdb`
    tool = sys.argv[1] if len(sys.argv) > 1 else None
    raise SystemExit(launch_desktop(selected_tool=tool))
