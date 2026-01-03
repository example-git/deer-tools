#!/usr/bin/env python3
"""webui.py

A lightweight, dependency-free GUI for the toolbox using the system browser.

Why a browser UI?
- Works on macOS/Windows/Linux without tkinter/Qt dependencies.
- Renders nicely and is fast (browser engine).
- Runs locally on 127.0.0.1 only.

This module intentionally does not attempt to embed terminal TUIs.
It can (optionally) open a new terminal window and run TUI commands.
"""

# This module is UI glue code that intentionally catches broad exceptions in a
# few places to keep the local web server responsive.
# pylint: disable=broad-exception-caught

from __future__ import annotations

import html
import json
import os
import shlex
import subprocess
import sys
import threading
import time
import urllib.parse
import weakref
import webbrowser
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from shared import start_subprocess_to_log

# Import shared tool parsing utilities
from toolbox import tool_parser


@dataclass
class Task:
    id: str
    argv: List[str]
    started_at: float = field(default_factory=time.time)
    lines: List[str] = field(default_factory=list)
    done: bool = False
    exit_code: Optional[int] = None
    # Progress tracking
    progress_percent: int = 0
    progress_message: str = ""
    progress_current: Optional[int] = None
    progress_total: Optional[int] = None
    # Log file path for file-based streaming
    log_file: Optional[str] = None


class _State:
    def __init__(self):
        self.lock = threading.Lock()
        self.tasks: Dict[str, Task] = {}
        self.next_id = 1
        self.server: Optional[ThreadingHTTPServer] = None

        # Run commands from repo root so `toolbox.py` and `plugins/` resolve.
        self.base_dir = str(Path(__file__).resolve().parent.parent)
        self.plugins_dir = str(Path(self.base_dir) / "plugins")
        self.tools: Dict[str, dict] = {}  # tool_id -> metadata

        # Ensure repo root is on sys.path for plugins.* imports
        if self.base_dir not in sys.path:
            sys.path.insert(0, self.base_dir)

    def new_task_id(self) -> str:
        with self.lock:
            tid = str(self.next_id)
            self.next_id += 1
            return tid

    def discover_tools(self):
        """Scan subdirectories for metadata.json and populate self.tools."""
        self.tools = tool_parser.discover_tools(self.plugins_dir)


_STATE = _State()

# Track background server threads without mutating stdlib server objects.
_SERVER_THREADS: "weakref.WeakKeyDictionary[ThreadingHTTPServer, threading.Thread]" = (
    weakref.WeakKeyDictionary()
)


def _split_command(cmd: str) -> List[str]:
    """Split a shell command string into a list of arguments."""
    return tool_parser.split_command(cmd)


def _start_task(argv: List[str]) -> Task:
    tid = _STATE.new_task_id()

    # Create log directory in the project's working directory
    log_dir = os.path.join(_STATE.base_dir, ".logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"task_{tid}_{int(time.time())}.log")

    task = Task(id=tid, argv=argv, log_file=log_file)

    with _STATE.lock:
        _STATE.tasks[tid] = task

    def _runner():
        def _on_line(line: str):
            # LogWatcher yields lines without a trailing newline
            with _STATE.lock:
                task.lines.append(line + "\n")
                progress = tool_parser.parse_progress(line)
                if progress:
                    task.progress_percent = progress["percent"]
                    task.progress_message = progress["message"]
                    task.progress_current = progress.get("current")
                    task.progress_total = progress.get("total")

        try:
            runner = start_subprocess_to_log(
                argv,
                cwd=_STATE.base_dir,
                log_dir=os.path.join(_STATE.base_dir, ".logs"),
                log_prefix=f"task_{tid}",
                env={"PYTHONUNBUFFERED": "1"},
                threads=tool_parser.get_global_threads(),
                on_line=_on_line,
                poll_interval=0.05,
            )
        except Exception as e:
            with _STATE.lock:
                task.lines.append(f"[ERROR] Failed to start process: {e}\n")
                task.done = True
                task.exit_code = 1
            return

        rc = runner.wait()
        with _STATE.lock:
            task.done = True
            task.exit_code = rc if rc is not None else runner.exit_code
            if task.exit_code == 0:
                task.progress_percent = 100

    threading.Thread(target=_runner, daemon=True).start()
    return task


def _html_page(title: str, body: str) -> bytes:
    py = shlex.quote(sys.executable)
    page = f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\"/>
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"/>
  <title>{html.escape(title)}</title>
  <script>
    // Persistent theme: default to dark.
    (function() {{
      try {{
        const saved = localStorage.getItem('toolbox_theme');
        document.documentElement.dataset.theme = saved || 'dark';
      }} catch (e) {{
        document.documentElement.dataset.theme = 'dark';
      }}
    }})();

    function toolboxSetTheme(next) {{
      try {{ localStorage.setItem('toolbox_theme', next); }} catch (e) {{}}
      document.documentElement.dataset.theme = next;
    }}
    function toolboxToggleTheme() {{
      const cur = document.documentElement.dataset.theme || 'dark';
      toolboxSetTheme(cur === 'dark' ? 'light' : 'dark');
    }}
    function toolboxBack() {{ try {{ history.back(); }} catch (e) {{}} }}
    function toolboxForward() {{ try {{ history.forward(); }} catch (e) {{}} }}
    function toolboxHome() {{ location.href = '/'; }}
  </script>
  <style>
    :root[data-theme="dark"] {{
      --bg: #0f1115;
      --panel: #151820;
      --panel2: #0c0e12;
      --text: #e8e8ea;
      --muted: #a7adb8;
      --accent: #9aa4b2;
      --border: #2a2f39;
      --good: #4ade80;
      --warn: #fbbf24;
      --bad: #fb7185;
      --primary: #60a5fa;
      --danger: #fb7185;
      --code-bg: #1a1d26;
      --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
      --sans: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial;
    }}

    :root[data-theme="light"] {{
      --bg: #f5f5f7;
      --panel: #ffffff;
      --panel2: #e8e8ec;
      --text: #1d1d1f;
      --muted: #6e6e73;
      --accent: #0071e3;
      --border: #d2d2d7;
      --good: #34c759;
      --warn: #ff9f0a;
      --bad: #ff3b30;
      --primary: #0071e3;
      --danger: #ff3b30;
      --code-bg: #f5f5f7;
      --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
      --sans: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial;
    }}

    body {{
      margin: 0;
      padding: 0;
      background: radial-gradient(1200px 700px at 15% 10%, color-mix(in srgb, var(--panel) 65%, var(--bg)) 0%, var(--bg) 60%);
      color: var(--text);
      font-family: var(--sans);
    }}

    .wrap {{
      max-width: 980px;
      margin: 28px auto;
      padding: 0 16px;
    }}

    .header-bar {{
      display: grid;
      grid-template-columns: 1fr auto 1fr;
      align-items: center;
      gap: 8px;
      padding: 6px 12px;
      background: var(--panel);
      border-bottom: 1px solid var(--border);
      -webkit-app-region: drag;
      user-select: none;
      position: sticky;
      top: 0;
      z-index: 100;
    }}

    .header-bar h1 {{
      font-size: 14px;
      margin: 0;
      font-weight: 500;
      text-align: center;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}

    .header-bar .nav {{
      -webkit-app-region: no-drag;
      justify-self: start;
    }}

    .header-bar button, .header-bar .btn {{
      padding: 5px 10px;
      font-size: 14px;
      min-width: 28px;
    }}

    .winctrl {{
      display: flex;
      gap: 6px;
      -webkit-app-region: no-drag;
      justify-self: end;
    }}

    .winctrl button {{
      padding: 4px 10px;
      font-size: 13px;
      border-radius: 6px;
    }}

    .winctrl .close:hover {{
      background: var(--bad);
      border-color: var(--bad);
    }}

    .top {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 14px;
    }}

    .nav {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      align-items: center;
      justify-content: flex-end;
    }}

    h1 {{
      margin: 0;
      font-size: 20px;
      letter-spacing: 0.2px;
    }}

    .card {{
      background: color-mix(in srgb, var(--panel) 92%, transparent);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 14px;
      box-shadow: 0 10px 30px rgba(0,0,0,0.25);
    }}

    .row {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: center;
      margin: 10px 0;
    }}

    label {{
      font-size: 13px;
      color: var(--muted);
    }}

    input[type=text] {{
      width: min(860px, 100%);
      padding: 10px 12px;
      border-radius: 10px;
      border: 1px solid var(--border);
      background: color-mix(in srgb, var(--panel) 55%, var(--bg));
      color: var(--text);
      font-family: var(--mono);
      font-size: 13px;
      outline: none;
    }}

    button, a.btn {{
      display: inline-block;
      padding: 9px 12px;
      border-radius: 10px;
      border: 1px solid var(--border);
      background: color-mix(in srgb, var(--panel) 55%, var(--bg));
      color: var(--text);
      text-decoration: none;
      cursor: pointer;
      font-size: 13px;
    }}

    button.primary {{
      border-color: color-mix(in srgb, var(--accent) 70%, var(--border));
      background: color-mix(in srgb, var(--accent) 18%, color-mix(in srgb, var(--panel) 55%, var(--bg)));
    }}

    .hint {{
      font-size: 13px;
      color: var(--muted);
      margin-top: 8px;
      line-height: 1.4;
    }}

    pre.console {{
      background: var(--panel2);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 12px;
      margin: 10px 0 0;
      height: 52vh;
      overflow: auto;
      font-family: var(--mono);
      font-size: 12px;
      line-height: 1.35;
      white-space: pre-wrap;
      word-break: break-word;
    }}

    .status {{
      font-family: var(--mono);
      font-size: 12px;
      color: var(--muted);
    }}

    .badge {{
      display: inline-block;
      padding: 2px 8px;
      border-radius: 999px;
      border: 1px solid var(--border);
      font-size: 12px;
      margin-left: 8px;
    }}

    .good {{ color: var(--good); border-color: color-mix(in srgb, var(--good) 35%, var(--border)); }}
    .warn {{ color: var(--warn); border-color: color-mix(in srgb, var(--warn) 35%, var(--border)); }}
    .bad {{ color: var(--bad); border-color: color-mix(in srgb, var(--bad) 35%, var(--border)); }}

    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 10px;
      margin-top: 10px;
    }}

    .tile {{
      padding: 12px;
      border-radius: 12px;
      border: 1px solid var(--border);
      background: color-mix(in srgb, var(--panel) 55%, var(--bg));
    }}

    .tile h3 {{
      margin: 0 0 8px;
      font-size: 14px;
    }}

    .tile p {{
      margin: 0 0 10px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
    }}

    .tile .row {{ margin: 0; }}
  </style>
</head>
<body>
  <div class="header-bar">
    <div class="nav">
      <button type="button" onclick="toolboxBack()" title="Back">&#x2190;</button>
      <button type="button" onclick="toolboxForward()" title="Forward">&#x2192;</button>
      <button type="button" class="primary" onclick="toolboxHome()" title="Home">&#x2302;</button>
      <button type="button" onclick="toolboxToggleTheme()" title="Toggle Light/Dark">&#x263E;</button>
    </div>
    <h1>{html.escape(title)}</h1>
    <div class="winctrl">
      <button type="button" onclick="if(pywebview && pywebview.api && pywebview.api.minimize) pywebview.api.minimize()" title="Minimize">&#x2212;</button>
      <button type="button" onclick="if(pywebview && pywebview.api && pywebview.api.toggle_fullscreen) pywebview.api.toggle_fullscreen()" title="Fullscreen">&#x26F6;</button>
      <button type="button" class="close" onclick="if(pywebview && pywebview.api && pywebview.api.close) {{ pywebview.api.close(); }} else {{ location.href='/shutdown_redirect'; }}" title="Close">&#x2716;</button>
    </div>
  </div>
  <div class="wrap">
    <div class="top" style="display:none">
      <div class=\"nav\">
        <button type="button" onclick="toolboxBack()" title="Back">&#x2190;</button>
        <button type="button" onclick="toolboxForward()" title="Forward">&#x2192;</button>
        <button type="button" class="primary" onclick="toolboxHome()" title="Home">&#x2302;</button>
        <form method="post" action="/run" style="margin:0">
          <input type="hidden" name="cmd" value="{html.escape(py)} toolbox.py doctor"/>
          <button type="submit" title="Doctor">&#x2695;</button>
        </form>
        <button type="button" onclick="toolboxToggleTheme()" title="Theme">&#x263E;</button>
        <form method="post" action="/shutdown" style="margin:0">
          <button type="submit" title="Stop">&#x2716;</button>
        </form>
      </div>
    </div>

    {body}

    <div class=\"hint\">Bound to <span class=\"status\">127.0.0.1</span>. Close this tab or click <b>Stop GUI</b> to exit.</div>
  </div>
</body>
</html>"""
    return page.encode("utf-8")


def _launcher_body(selected: Optional[str]) -> str:
    selected_q = html.escape(selected or "")
    py = html.escape(sys.executable)
    base = html.escape(_STATE.base_dir)

    # Discover tools if not already done
    if not _STATE.tools:
        _STATE.discover_tools()

    # Build tool tiles dynamically
    tool_tiles = []
    for tool_id in sorted(_STATE.tools.keys()):
        meta = _STATE.tools[tool_id]
        name = html.escape(meta.get("name", tool_id.replace("_", " ").title()))
        desc = html.escape(meta.get("description", ""))
        icon = meta.get("icon", "&#128295;")  # Default wrench icon
        if meta.get("supports_gui", False):
            tool_tiles.append(
                f"""
      <div class="tile">
        <h3>{icon} {name}</h3>
        <p>{desc}</p>
        <div class="row">
          <a class="btn primary" href="/tool/{html.escape(tool_id)}">Open</a>
        </div>
      </div>"""
            )

    tiles = '<div class="grid">' + "".join(tool_tiles)

    # Add Doctor tile
    tiles += f"""
      <div class="tile">
        <h3>&#9881; Doctor</h3>
        <p>Environment + tool discovery checks.</p>
        <div class="row">
          <form method="post" action="/run" style="margin:0">
            <input type="hidden" name="cmd" value="{py} toolbox.py doctor"/>
            <button class="primary" type="submit">Run</button>
          </form>
        </div>
      </div>
      <div class="tile">
        <h3>&#128214; Documentation</h3>
        <p>View Deer Toolbox documentation.</p>
        <div class="row">
          <a class="btn primary" href="/readme">View Docs</a>
        </div>
      </div>
    </div>"""

    form = f"""
    <div class="card" style="margin-top:16px">
      <div class="row">
        <label for="cmd">Run command (in: <span class="status">{base}</span>)</label>
      </div>
      <form method="post" action="/run">
        <input id="cmd" name="cmd" type="text" value="{py} toolbox.py {selected_q}"/>
        <div class="row" style="margin-top:10px">
          <button class="primary" type="submit">Run</button>
          <a class="btn" href="/">Reset</a>
        </div>
      </form>
    </div>
    """

    return tiles + form


def _readme_page(tool_id: Optional[str] = None) -> str:
    """Generate a README viewing page with markdown rendering.

    Args:
        tool_id: Tool ID to show README for, or None for main README
    """
    # Determine README path
    if tool_id:
        meta = _STATE.tools.get(tool_id, {})
        tool_path = meta.get("_path") or os.path.join(
            _STATE.plugins_dir, meta.get("_dir", tool_id)
        )
        readme_path = os.path.join(tool_path, "README.md")
        title = f"{tool_id.replace('_', ' ').title()} Documentation"
        back_link = f"/tool/{html.escape(tool_id)}"
    else:
        readme_path = os.path.join(_STATE.base_dir, "README.md")
        title = "Deer Toolbox Documentation"
        back_link = "/"

    # Read README content
    try:
        with open(readme_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        return f"""
        <div class="card">
          <h2>&#10071; Not Found</h2>
          <p style="color:var(--danger)">README not found: {html.escape(readme_path)}</p>
          <a class="btn" href="{back_link}">Go Back</a>
        </div>
        """
    except Exception as e:
        return f"""
        <div class="card">
          <h2>&#10071; Error</h2>
          <p style="color:var(--danger)">Error reading README: {html.escape(str(e))}</p>
          <a class="btn" href="{back_link}">Go Back</a>
        </div>
        """

    # Try to render markdown with Python markdown library if available
    try:
        import importlib

        markdown = importlib.import_module("markdown")
        html_content = markdown.markdown(
            content,
            extensions=["extra", "codehilite", "toc", "tables", "fenced_code"],
        )
    except ImportError:
        # Fallback: basic HTML escaping with pre-wrap
        html_content = f'<pre style="white-space: pre-wrap; font-family: inherit;">{html.escape(content)}</pre>'

    return f"""
    <div class="card">
      <div class="row" style="justify-content:space-between; align-items:center">
        <h2>&#128214; {html.escape(title)}</h2>
        <a class="btn" href="{back_link}">Go Back</a>
      </div>
    </div>
    <div class="card" style="margin-top:16px; max-width:900px">
      <div class="readme-content">
        {html_content}
      </div>
    </div>
    <style>
      .readme-content {{ line-height: 1.6; }}
      .readme-content h1 {{ margin-top: 1.5em; border-bottom: 2px solid var(--border); padding-bottom: 0.3em; }}
      .readme-content h2 {{ margin-top: 1.3em; border-bottom: 1px solid var(--border); padding-bottom: 0.2em; }}
      .readme-content h3 {{ margin-top: 1em; }}
      .readme-content code {{ background: var(--code-bg); padding: 2px 6px; border-radius: 3px; font-size: 0.9em; }}
      .readme-content pre {{ background: var(--code-bg); padding: 12px; border-radius: 6px; overflow-x: auto; }}
      .readme-content pre code {{ background: none; padding: 0; }}
      .readme-content table {{ border-collapse: collapse; width: 100%; margin: 1em 0; }}
      .readme-content th, .readme-content td {{ border: 1px solid var(--border); padding: 8px 12px; text-align: left; }}
      .readme-content th {{ background: var(--code-bg); font-weight: bold; }}
      .readme-content blockquote {{ border-left: 4px solid var(--primary); padding-left: 1em; margin-left: 0; color: var(--muted); }}
      .readme-content a {{ color: var(--primary); text-decoration: none; }}
      .readme-content a:hover {{ text-decoration: underline; }}
      .readme-content ul, .readme-content ol {{ padding-left: 2em; }}
      .readme-content li {{ margin: 0.3em 0; }}
    </style>
    """


def _tool_page(tool_id: str) -> str:
    """Generate a dynamic tool page.

    Checks for a webui_config in the tool's module or falls back to generic CLI form.
    """
    meta = _STATE.tools.get(tool_id, {})
    tool_dir = meta.get("_dir", tool_id)
    py = shlex.quote(sys.executable)

    # Try to import webui_config from the tool module
    webui_config = None
    try:
        import importlib

        mod = importlib.import_module(f"plugins.{tool_dir}.tool")
        webui_config = getattr(mod, "webui_config", None)
    except Exception:
        pass

    # If tool provides custom webui_config, use it to build forms
    if webui_config and isinstance(webui_config, dict):
        return _build_tool_form(tool_id, meta, webui_config, py)

    # Default: show generic command runner
    return _build_generic_tool_page(tool_id, meta, py)


def _build_generic_tool_page(tool_id: str, meta: dict, py: str) -> str:
    """Build a generic tool page with command runner."""
    name = html.escape(meta.get("name", tool_id))
    desc = html.escape(meta.get("description", ""))
    icon = meta.get("icon", "&#128295;")
    cli_name = tool_id.replace("_", "-")

    return f"""
    <div class="card">
      <h2>{icon} {name}</h2>
      <p style="color:var(--muted)">{desc}</p>
      <div class="row" style="margin-top:12px">
        <a class="btn" href="/readme?tool={tool_id}">&#128214; View Documentation</a>
        <a class="btn" href="/">Home</a>
      </div>
    </div>

    <div class="card" style="margin-top:16px">
      <h3>Quick Actions</h3>
      <div class="grid" style="margin-top:12px">
        <div class="tile">
          <h3>Run with GUI</h3>
          <form method="post" action="/run">
            <input type="hidden" name="cmd" value="{py} toolbox.py {cli_name} --mode gui"/>
            <button class="primary" type="submit">Launch GUI</button>
          </form>
        </div>
        <div class="tile">
          <h3>Show Help</h3>
          <form method="post" action="/run">
            <input type="hidden" name="cmd" value="{py} toolbox.py {cli_name} --help"/>
            <button type="submit">--help</button>
          </form>
        </div>
      </div>
    </div>

    <div class="card" style="margin-top:16px">
      <h3>Custom Command</h3>
      <form method="post" action="/run">
        <input id="cmd" name="cmd" type="text" value="{py} toolbox.py {cli_name} "/>
        <div class="row" style="margin-top:10px">
          <button class="primary" type="submit">Run</button>
          <a class="btn" href="/">Home</a>
        </div>
      </form>
    </div>
    """


def _get_field_placeholder(field_def: dict) -> str:
    """Get a placeholder/example for a field based on its type and id."""
    return tool_parser.get_field_placeholder(field_def)


def _build_tool_form(tool_id: str, meta: dict, config: dict, py: str) -> str:
    """Build a custom tool page from webui_config."""
    name = html.escape(meta.get("name", tool_id))
    desc = html.escape(meta.get("description", ""))
    icon = meta.get("icon", "&#128295;")
    cli_name = tool_id.replace("_", "-")

    sections = []
    sections.append(
        f"""
    <div class="card">
      <h2>{icon} {name}</h2>
      <p style="color:var(--muted)">{desc}</p>
      <div class="row" style="margin-top:12px">
        <a class="btn" href="/readme?tool={tool_id}">&#128214; View Documentation</a>
        <a class="btn" href="/">Home</a>
      </div>
    </div>
    """
    )

    # Build forms from config
    for action in config.get("actions", []):
        action_id = html.escape(action.get("id", "action"))
        action_name = html.escape(action.get("name", "Action"))
        action_desc = html.escape(action.get("description", ""))
        fields_html = []

        for field_def in action.get("fields", []):
            fid = html.escape(field_def.get("id", "field"))
            fname = html.escape(field_def.get("name", fid))
            ftype = field_def.get("type", "text")
            fdefault = html.escape(str(field_def.get("default", "")))
            placeholder = html.escape(_get_field_placeholder(field_def))
            frequired = "required" if field_def.get("required", False) else ""

            if ftype == "directory":
                fields_html.append(
                    f"""
                <div class="row">
                  <label for="{fid}">{fname}</label>
                  <input id="{fid}" name="{fid}" type="text" placeholder="{placeholder}" value="{fdefault}" {frequired}/>
                </div>"""
                )
            elif ftype == "file":
                fields_html.append(
                    f"""
                <div class="row">
                  <label for="{fid}">{fname}</label>
                  <input id="{fid}" name="{fid}" type="text" placeholder="{placeholder}" value="{fdefault}" {frequired}/>
                </div>"""
                )
            elif ftype == "select":
                opts = "".join(
                    f'<option value="{html.escape(o)}">{html.escape(o)}</option>'
                    for o in field_def.get("options", [])
                )
                fields_html.append(
                    f"""
                <div class="row">
                  <label for="{fid}">{fname}</label>
                  <select id="{fid}" name="{fid}">{opts}</select>
                </div>"""
                )
            elif ftype == "checkbox":
                checked = "checked" if field_def.get("default", False) else ""
                fields_html.append(
                    f"""
                <div class="row">
                  <label><input type="checkbox" id="{fid}" name="{fid}" {checked}/> {fname}</label>
                </div>"""
                )
            else:
                fields_html.append(
                    f"""
                <div class="row">
                  <label for="{fid}">{fname}</label>
                  <input id="{fid}" name="{fid}" type="text" placeholder="{placeholder}" value="{fdefault}" {frequired}/>
                </div>"""
                )
        sections.append(
            f"""
    <div class="card" style="margin-top:16px">
      <h3>{action_name}</h3>
      <p style="color:var(--muted);font-size:13px">{action_desc}</p>
      <form method="post" action="/run_form/{html.escape(tool_id)}/{action_id}">
        {"".join(fields_html)}
        <div class="row" style="margin-top:12px">
          <button class="primary" type="submit">Run</button>
        </div>
      </form>
    </div>
        """
        )

    # Add generic command runner
    sections.append(
        f"""
    <div class="card" style="margin-top:16px">
      <h3>Custom Command</h3>
      <form method="post" action="/run">
        <input id="cmd" name="cmd" type="text" value="{py} toolbox.py {cli_name} "/>
        <div class="row" style="margin-top:10px">
          <button class="primary" type="submit">Run</button>
          <a class="btn" href="/">Home</a>
        </div>
      </form>
    </div>
    """
    )

    return "".join(sections)


def _build_command_from_form(tool_id: str, action_id: str, form: dict) -> Optional[str]:
    """Build a CLI command from form data using tool's webui_config.

    Uses the 'command' template from action if available, otherwise builds
    command from fields. The template can contain {field_id} placeholders.
    """
    if not _STATE.tools:
        _STATE.discover_tools()

    # Get webui_config from the tool module
    webui_config = tool_parser.get_tool_webui_config(tool_id, _STATE.tools)
    if not webui_config:
        return None

    # Find the action
    action = tool_parser.get_action_by_id(webui_config, action_id)
    if not action:
        return None

    # Extract form values from HTTP form data
    field_values = tool_parser.extract_form_values(action, form)

    # Build the command using shared logic
    return tool_parser.build_command_from_action(tool_id, action, field_values)


class _Handler(BaseHTTPRequestHandler):
    def _send(
        self, code: int, body: bytes, content_type: str = "text/html; charset=utf-8"
    ):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location: str):
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def log_message(
        self, format: str, *args: object
    ) -> None:  # pylint: disable=redefined-builtin
        # Keep console clean; tasks output is shown in UI.
        return

    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if path == "/":
            selected = (qs.get("tool") or [""])[0].strip() or None
            body = _launcher_body(selected)
            self._send(200, _html_page("Toolbox", body))
            return

        if path == "/shutdown_redirect":
            _shutdown_server()
            self._send(
                200,
                _html_page(
                    "Stopped",
                    "<div class='card'>GUI stopped. You can close this window.</div>",
                ),
            )
            return

        # README viewing
        if path == "/readme":
            tool_id = (qs.get("tool") or [""])[0].strip() or None
            body = _readme_page(tool_id)
            title = (
                "Documentation"
                if tool_id is None
                else f"{tool_id.replace('_', ' ').title()} Documentation"
            )
            self._send(200, _html_page(title, body))
            return

        # Dynamic tool pages
        if path.startswith("/tool/"):
            tool_id = path[6:].strip("/")
            if not _STATE.tools:
                _STATE.discover_tools()

            if tool_id in _STATE.tools:
                body = _tool_page(tool_id)
                meta = _STATE.tools[tool_id]
                title = meta.get("name", tool_id.replace("_", " ").title())
                self._send(200, _html_page(title, body))
                return
            else:
                self._send(
                    404,
                    _html_page(
                        "Not Found",
                        f"<div class='card'>Tool '{html.escape(tool_id)}' not found.</div>",
                    ),
                )
                return

        if path.startswith("/task/") and path.endswith("/logs"):
            parts = path.strip("/").split("/")
            # /task/{id}/logs
            if len(parts) != 3:
                self._send(404, b"not found", "text/plain")
                return

            tid = parts[1]
            pos_s = (qs.get("pos") or ["0"])[0]
            try:
                pos = int(pos_s)
            except ValueError:
                pos = 0

            with _STATE.lock:
                task = _STATE.tasks.get(tid)
                if not task:
                    payload = {"error": "not found"}
                    self._send(
                        404, json.dumps(payload).encode("utf-8"), "application/json"
                    )
                    return

                lines = task.lines[pos:]
                # Calculate ETA if progress is available
                eta = None
                if task.progress_percent > 0 and not task.done:
                    eta = tool_parser.estimate_eta(
                        task.started_at, task.progress_percent
                    )

                payload = {
                    "id": task.id,
                    "pos": pos + len(lines),
                    "lines": lines,
                    "done": task.done,
                    "exit_code": task.exit_code,
                    "progress": {
                        "percent": task.progress_percent,
                        "message": task.progress_message,
                        "current": task.progress_current,
                        "total": task.progress_total,
                        "eta": eta,
                    },
                    "elapsed": time.time() - task.started_at,
                }

            self._send(200, json.dumps(payload).encode("utf-8"), "application/json")
            return

        if path.startswith("/task/"):
            parts = path.strip("/").split("/")
            # /task/{id}
            if len(parts) != 2:
                self._send(404, b"not found", "text/plain")
                return

            tid = parts[1]
            with _STATE.lock:
                task = _STATE.tasks.get(tid)

            if not task:
                self._send(
                    404,
                    _html_page(
                        "Task not found", '<div class="card">No such task.</div>'
                    ),
                )
                return

            argv_disp = html.escape(" ".join(task.argv))
            body = f"""
            <div class=\"card\">
              <div class=\"row\" style=\"justify-content:space-between; align-items:center\">
                <div style=\"flex:1; min-width:0\">
                  <span class=\"status\">Command:</span>
                  <span class=\"status\" style=\"word-break:break-all\">{argv_disp}</span>
                </div>
                <div id=\"badge\" class=\"badge warn\">running</div>
              </div>
              
              <!-- Progress Section -->
              <div id=\"progress-section\" class=\"progress-section\" style=\"margin:14px 0\">
                <div class=\"progress-header\" style=\"display:flex; justify-content:space-between; align-items:center; margin-bottom:6px\">
                  <span id=\"progress-label\" class=\"status\">Starting...</span>
                  <span id=\"progress-eta\" class=\"status\" style=\"color:var(--muted)\"></span>
                </div>
                <div class=\"progress-bar-container\" style=\"background:var(--panel2); border-radius:8px; height:20px; overflow:hidden; border:1px solid var(--border)\">
                  <div id=\"progress-bar\" class=\"progress-bar\" style=\"height:100%; width:0%; background:linear-gradient(90deg, var(--accent), color-mix(in srgb, var(--accent) 70%, var(--good))); transition:width 0.3s ease\"></div>
                </div>
                <div class=\"progress-footer\" style=\"display:flex; justify-content:space-between; margin-top:4px\">
                  <span id=\"progress-detail\" class=\"status\" style=\"font-size:11px; color:var(--muted)\"></span>
                  <span id=\"progress-elapsed\" class=\"status\" style=\"font-size:11px; color:var(--muted)\"></span>
                </div>
              </div>
              
              <pre id=\"console\" class=\"console\"></pre>
            </div>

            <script>
              const consoleEl = document.getElementById('console');
              const badge = document.getElementById('badge');
              const progressBar = document.getElementById('progress-bar');
              const progressLabel = document.getElementById('progress-label');
              const progressEta = document.getElementById('progress-eta');
              const progressDetail = document.getElementById('progress-detail');
              const progressElapsed = document.getElementById('progress-elapsed');
              const progressSection = document.getElementById('progress-section');
              let pos = 0;

              function formatElapsed(seconds) {{
                if (seconds < 60) return Math.floor(seconds) + 's';
                if (seconds < 3600) return Math.floor(seconds/60) + 'm ' + Math.floor(seconds%60) + 's';
                return Math.floor(seconds/3600) + 'h ' + Math.floor((seconds%3600)/60) + 'm';
              }}

              function setBadge(done, code) {{
                if (!done) {{
                  badge.textContent = 'running';
                  badge.className = 'badge warn';
                  return;
                }}
                badge.textContent = 'done (exit ' + code + ')';
                badge.className = 'badge ' + (code === 0 ? 'good' : 'bad');
              }}

              function updateProgress(data) {{
                const p = data.progress || {{}};
                const pct = p.percent || 0;
                
                progressBar.style.width = pct + '%';
                
                if (data.done) {{
                  progressBar.style.width = '100%';
                  if (data.exit_code === 0) {{
                    progressBar.style.background = 'var(--good)';
                    progressLabel.textContent = '✓ Completed successfully';
                  }} else {{
                    progressBar.style.background = 'var(--bad)';
                    progressLabel.textContent = '✗ Failed (exit ' + data.exit_code + ')';
                  }}
                  progressEta.textContent = '';
                }} else if (pct > 0) {{
                  progressLabel.textContent = (p.message || 'Processing...') + ' (' + pct + '%)';
                  progressEta.textContent = p.eta || '';
                }} else {{
                  progressLabel.textContent = 'Processing...';
                }}
                
                // Show current/total if available
                if (p.current !== null && p.total !== null) {{
                  progressDetail.textContent = p.current + ' / ' + p.total + ' items';
                }} else {{
                  progressDetail.textContent = '';
                }}
                
                // Show elapsed time
                if (data.elapsed) {{
                  progressElapsed.textContent = 'Elapsed: ' + formatElapsed(data.elapsed);
                }}
              }}

              async function poll() {{
                const res = await fetch('/task/{tid}/logs?pos=' + pos);
                const data = await res.json();
                if (data.lines && data.lines.length) {{
                  consoleEl.textContent += data.lines.join('');
                  pos = data.pos;
                  consoleEl.scrollTop = consoleEl.scrollHeight;
                }}
                setBadge(data.done, data.exit_code);
                updateProgress(data);
                if (!data.done) setTimeout(poll, 350);
              }}
              poll();
            </script>
            """

            self._send(200, _html_page(f"Task {tid}", body))
            return

        self._send(404, b"not found", "text/plain")

    def do_POST(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        length = int(self.headers.get("Content-Length", "0") or 0)
        data = self.rfile.read(length) if length else b""
        form = urllib.parse.parse_qs(data.decode("utf-8"), keep_blank_values=True)

        if path == "/run":
            cmd = (form.get("cmd") or [""])[0]
            argv = _split_command(cmd)
            if not argv:
                self._send(
                    400,
                    _html_page("Error", '<div class="card">No command provided.</div>'),
                )
                return

            task = _start_task(argv)
            self._redirect(f"/task/{task.id}")
            return

        # Handle form submissions from tool-specific forms
        if path.startswith("/run_form/"):
            parts = path[10:].strip("/").split("/")
            if len(parts) >= 2:
                tool_id = parts[0]
                action_id = parts[1]
                cmd = _build_command_from_form(tool_id, action_id, form)
                if cmd:
                    argv = _split_command(cmd)
                    if argv:
                        task = _start_task(argv)
                        self._redirect(f"/task/{task.id}")
                        return
            self._send(
                400,
                _html_page("Error", "<div class='card'>Invalid form submission.</div>"),
            )
            return

        if path == "/open_tui":
            ok, msg = open_tui_in_terminal()
            badge = "good" if ok else "bad"
            body = f'<div class="card"><div class="badge {badge}">{html.escape(msg)}</div></div>'
            self._send(200, _html_page("Open TUI", body))
            return

        if path == "/shutdown":
            self._send(
                200, _html_page("Stopping", '<div class="card">Stopping GUI…</div>')
            )
            threading.Thread(target=_shutdown_server, daemon=True).start()
            return

        self._send(404, b"not found", "text/plain")


def _shutdown_server():
    srv = _STATE.server
    if srv is None:
        return
    try:
        srv.shutdown()
    except Exception:
        pass


def open_tui_in_terminal() -> Tuple[bool, str]:
    """Best-effort: open a new terminal window and run `python toolbox.py`.

    Returns:
        (ok, message)
    """
    cmd = (
        f"cd {shlex.quote(_STATE.base_dir)} && {shlex.quote(sys.executable)} toolbox.py"
    )

    if sys.platform == "darwin":
        # macOS Terminal
        script = f'tell application "Terminal" to do script "{cmd}"'
        try:
            subprocess.Popen(["osascript", "-e", script])
            return True, "Opened Terminal with TUI command."
        except Exception as e:
            return False, f"Failed to open Terminal: {e}"

    if os.name == "nt":
        try:
            subprocess.Popen(["cmd", "/c", "start", "cmd", "/k", cmd])
            return True, "Opened cmd.exe with TUI command."
        except Exception as e:
            return False, f"Failed to open cmd.exe: {e}"

    # Linux/others: cannot reliably pick terminal emulator
    return False, "Run the TUI from a terminal: python toolbox.py"


def launch_gui(
    selected_tool: Optional[str] = None, host: str = "127.0.0.1", port: int = 0
) -> int:
    """Launch the browser-based GUI launcher.

    Args:
        selected_tool: Optional tool name to prefill in the command input.
        host: Bind address (default 127.0.0.1).
        port: Port to bind. 0 chooses a free port.

    Returns:
        Process exit code.
    """
    server, url = start_server(
        host=host, port=port, selected_tool=selected_tool, open_browser=True
    )

    print(f"[INFO] Toolbox GUI running at: {url}")
    print("[INFO] Press Ctrl+C to stop.")

    try:
        server.serve_forever()
        return 0
    except KeyboardInterrupt:
        return 0
    finally:
        try:
            server.server_close()
        except Exception:
            pass
        _STATE.server = None


def start_server(
    host: str = "127.0.0.1",
    port: int = 0,
    selected_tool: Optional[str] = None,
    open_browser: bool = False,
    background: bool = False,
):
    """Start the HTTP server and return (server, url).

    This is used by the desktop wrapper to embed the UI.
    """
    server = ThreadingHTTPServer((host, port), _Handler)
    _STATE.server = server

    actual_host, actual_port = server.server_address[:2]
    url = f"http://{actual_host}:{actual_port}/"
    if selected_tool:
        url += "?" + urllib.parse.urlencode({"tool": selected_tool})

    if open_browser:
        try:
            webbrowser.open(url, new=1)
        except Exception:
            pass

    if background:
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        _SERVER_THREADS[server] = t

    return server, url


def stop_server(server: ThreadingHTTPServer):
    """Stop a server started by start_server(background=True)."""
    try:
        server.shutdown()
    except Exception:
        pass
    try:
        server.server_close()
    except Exception:
        pass
