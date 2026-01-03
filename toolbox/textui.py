#!/usr/bin/env python3
"""textui.py

Full-featured Text User Interface with parity to the web GUI.

Uses:
- `rich` for beautiful terminal rendering (tables, panels, progress)
- `questionary` for interactive prompts (menus, inputs, checkboxes)

Both libraries are highly compatible across Windows/macOS/Linux.

Install:
    pip install rich questionary
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

# Import shared tool parsing utilities
import toolbox.tool_parser
# ---------------------------------------------------------------------------
# Lazy imports for optional dependencies
# ---------------------------------------------------------------------------

def _import_rich():
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table
        from rich.text import Text
        from rich.live import Live
        from rich.progress import (
            Progress, SpinnerColumn, TextColumn, BarColumn, 
            TaskProgressColumn, TimeElapsedColumn, TimeRemainingColumn
        )
        from rich.markdown import Markdown
        from rich.syntax import Syntax
        from rich.style import Style
        from rich.theme import Theme
        return {
            "Console": Console,
            "Panel": Panel,
            "Table": Table,
            "Text": Text,
            "Live": Live,
            "Progress": Progress,
            "SpinnerColumn": SpinnerColumn,
            "TextColumn": TextColumn,
            "BarColumn": BarColumn,
            "TaskProgressColumn": TaskProgressColumn,
            "TimeElapsedColumn": TimeElapsedColumn,
            "TimeRemainingColumn": TimeRemainingColumn,
            "Markdown": Markdown,
            "Syntax": Syntax,
            "Style": Style,
            "Theme": Theme,
        }
    except ImportError:
        return None


def _import_questionary():
    try:
        import questionary
        from questionary import Style as QStyle
        return {"questionary": questionary, "QStyle": QStyle}
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

@dataclass
class TUIState:
    base_dir: str = field(default_factory=lambda: os.path.dirname(os.path.abspath(__file__)))
    tools: Dict[str, dict] = field(default_factory=dict)
    console: Any = None
    questionary: Any = None
    rich: Dict[str, Any] = field(default_factory=dict)
    # Console output buffer for split-screen display
    console_output: deque = field(default_factory=lambda: deque(maxlen=100))
    console_title: str = "Console Output"
    current_log_file: Optional[str] = None

    def discover_tools(self):
        """Scan subdirectories for metadata.json."""
        self.tools = tool_parser.discover_tools(self.base_dir)

    def clear_console(self):
        """Clear the console output buffer."""
        self.console_output.clear()

    def add_output(self, line: str):
        """Add a line to the console output buffer."""
        self.console_output.append(line)

    def get_output_text(self) -> str:
        """Get all console output as string."""
        return "\n".join(self.console_output)


_STATE = TUIState()


# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------

GREY_THEME = {
    "info": "dim cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
    "title": "bold white",
    "muted": "dim white",
    "accent": "cyan",
    "panel_border": "dim white",
}

Q_STYLE = None  # Will be set if questionary available


def _init_theme():
    global Q_STYLE
    q = _import_questionary()
    if q:
        Q_STYLE = q["QStyle"]([
            ("qmark", "fg:cyan bold"),
            ("question", "bold"),
            ("answer", "fg:cyan"),
            ("pointer", "fg:cyan bold"),
            ("highlighted", "fg:cyan bold"),
            ("selected", "fg:cyan"),
            ("separator", "fg:gray"),
            ("instruction", "fg:gray"),
            ("text", ""),
            ("disabled", "fg:gray italic"),
        ])


# ---------------------------------------------------------------------------
# Screen management
# ---------------------------------------------------------------------------

def clear_screen():
    """Clear the terminal screen."""
    if os.name == "nt":
        os.system("cls")
    else:
        os.system("clear")


def get_terminal_size() -> Tuple[int, int]:
    """Get terminal width and height."""
    try:
        size = os.get_terminal_size()
        return size.columns, size.lines
    except Exception:
        return 80, 24


def draw_screen(menu_content: str = "", title: str = "Toolbox TUI"):
    """Draw the split screen layout: header + menu area + console panel."""
    r = _import_rich()
    clear_screen()
    
    width, height = get_terminal_size()
    # Reserve lines: header(3) + menu_area(variable) + console(remaining)
    console_height = max(8, (height - 10) // 2)
    
    if r and _STATE.console:
        # Header
        _STATE.console.print(r["Panel"](
            r["Text"](title, style="bold white", justify="center"),
            border_style="cyan",
            padding=(0, 2),
        ))
        
        # Menu content (printed by questionary or fallback)
        if menu_content:
            _STATE.console.print(menu_content)
        
    else:
        # Fallback header
        print("=" * width)
        print(f"  {title}".center(width))
        print("=" * width)
        if menu_content:
            print(menu_content)


def draw_console_panel(menu_item_count: int = 8):
    """Draw the console output panel at current cursor position.
    
    Args:
        menu_item_count: Number of menu items to reserve space for.
                        This ensures the console is maximized while menu fits.
    """
    r = _import_rich()
    width, height = get_terminal_size()
    
    # Calculate space needed for other UI elements:
    # - Header panel: 3 lines (border + text + border)
    # - Tools line: 1 line
    # - Description: 2 lines (info + blank)
    # - Menu prompt: 1 line
    # - Menu items: menu_item_count lines
    # - Back option: 1 line (if applicable)
    # - Blank lines between sections: ~3
    # - Input prompt at bottom: 1 line
    # - Safety margin: 2 lines
    reserved_lines = 3 + 1 + 2 + 1 + menu_item_count + 1 + 3 + 1 + 2
    
    # Console gets remaining space, with min of 4 lines
    console_height = max(4, height - reserved_lines)
    
    output_text = _STATE.get_output_text()
    # Trim to fit console height (account for panel borders)
    output_lines = output_text.split("\n") if output_text else []
    content_height = console_height - 2  # subtract top/bottom border
    visible_lines = output_lines[-content_height:] if output_lines else ["(no output)"]
    visible_text = "\n".join(visible_lines)
    
    if r and _STATE.console:
        panel = r["Panel"](
            visible_text or "(no output)",
            title=f"[cyan]{_STATE.console_title}[/cyan]",
            border_style="dim white",
            height=console_height,
            padding=(0, 1),
        )
        _STATE.console.print(panel)
    else:
        print("-" * width)
        print(f" {_STATE.console_title}")
        print("-" * width)
        for line in visible_lines[-content_height:]:
            print(f" {line}")
        print("-" * width)


def _enable_mouse():
    """Enable mouse tracking in terminal."""
    if os.name != "nt":
        # Enable SGR mouse mode (better compatibility with modern terminals)
        sys.stdout.write('\x1b[?1000h')  # Enable basic mouse tracking
        sys.stdout.write('\x1b[?1006h')  # Enable SGR extended mode
        sys.stdout.flush()


def _disable_mouse():
    """Disable mouse tracking in terminal."""
    if os.name != "nt":
        sys.stdout.write('\x1b[?1006l')  # Disable SGR extended mode
        sys.stdout.write('\x1b[?1000l')  # Disable basic mouse tracking
        sys.stdout.flush()


def _getch_with_mouse():
    """Read a single character or mouse event from stdin (cross-platform)."""
    try:
        if os.name == "nt":
            import msvcrt
            ch = msvcrt.getch()
            if ch in (b'\x00', b'\xe0'):  # Special key prefix on Windows
                ch = msvcrt.getch()
                # Arrow keys on Windows
                if ch == b'H': return 'UP'
                if ch == b'P': return 'DOWN'
                if ch == b'I': return 'PGUP'
                if ch == b'Q': return 'PGDN'
            return ch.decode('utf-8', errors='ignore')
        else:
            import tty
            import termios
            import select
            
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                ch = sys.stdin.read(1)
                if ch == '\x1b':  # Escape sequence
                    # Check if more data is available
                    if select.select([sys.stdin], [], [], 0.01)[0]:
                        ch2 = sys.stdin.read(1)
                        if ch2 == '[':
                            ch3 = sys.stdin.read(1)
                            if ch3 == 'A': return 'UP'
                            if ch3 == 'B': return 'DOWN'
                            if ch3 == '5':
                                sys.stdin.read(1)  # consume ~
                                return 'PGUP'
                            if ch3 == '6':
                                sys.stdin.read(1)  # consume ~
                                return 'PGDN'
                            if ch3 == '<':
                                # SGR mouse event: \x1b[<Btn;X;Y[Mm]
                                seq = ''
                                while True:
                                    c = sys.stdin.read(1)
                                    if c in ('M', 'm'):
                                        break
                                    seq += c
                                parts = seq.split(';')
                                if len(parts) >= 1:
                                    btn = int(parts[0])
                                    # Button 64 = scroll up, 65 = scroll down
                                    if btn == 64:
                                        return 'SCROLL_UP'
                                    elif btn == 65:
                                        return 'SCROLL_DOWN'
                                return None  # Ignore other mouse events
                            if ch3 == 'M':
                                # Legacy mouse event: \x1b[M followed by 3 bytes
                                b1 = ord(sys.stdin.read(1))
                                sys.stdin.read(2)  # x, y coordinates
                                btn = b1 & 0x03
                                if b1 & 0x40:  # Scroll event
                                    if btn == 0:
                                        return 'SCROLL_UP'
                                    elif btn == 1:
                                        return 'SCROLL_DOWN'
                                return None  # Ignore other mouse events
                        return 'ESC'
                    return 'ESC'
                return ch
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    except Exception:
        return input()


def _getch():
    """Read a single character from stdin (cross-platform) - no mouse support."""
    try:
        if os.name == "nt":
            import msvcrt
            ch = msvcrt.getch()
            if ch in (b'\x00', b'\xe0'):  # Special key prefix on Windows
                ch = msvcrt.getch()
                # Arrow keys on Windows
                if ch == b'H': return 'UP'
                if ch == b'P': return 'DOWN'
                if ch == b'I': return 'PGUP'
                if ch == b'Q': return 'PGDN'
            return ch.decode('utf-8', errors='ignore')
        else:
            import tty
            import termios
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                ch = sys.stdin.read(1)
                if ch == '\x1b':  # Escape sequence
                    ch2 = sys.stdin.read(1)
                    if ch2 == '[':
                        ch3 = sys.stdin.read(1)
                        if ch3 == 'A': return 'UP'
                        if ch3 == 'B': return 'DOWN'
                        if ch3 == '5':
                            sys.stdin.read(1)  # consume ~
                            return 'PGUP'
                        if ch3 == '6':
                            sys.stdin.read(1)  # consume ~
                            return 'PGDN'
                    return 'ESC'
                return ch
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    except Exception:
        return input()


def show_console_viewer():
    """Interactive scrollable console viewer.
    
    Controls:
    - Up/Down or j/k: Scroll one line
    - Mouse scroll: Scroll up/down
    - Page Up/Down: Scroll one page
    - Home/g: Go to top
    - End/G: Go to bottom
    - q/Esc/Enter/Tab: Exit viewer
    """
    r = _import_rich()

    # If we have an active log file, tail it live so the viewer updates
    # immediately whenever the file is appended.
    watcher = None
    output_lines: List[str]
    log_path = getattr(_STATE, "current_log_file", None)
    if log_path and os.path.exists(log_path):
        from shared import LogWatcher

        watcher = LogWatcher(log_path, poll_interval=0.05)
        # Load existing content first
        output_lines = watcher.get_all_lines() or ["(no output)"]
        watcher.start()
    else:
        output_lines = list(_STATE.console_output) or ["(no output)"]

    total_lines = len(output_lines)
    scroll_pos = max(0, total_lines - 1)  # Start at bottom
    follow = True  # auto-follow tail when at bottom
    
    # Enable mouse tracking
    _enable_mouse()
    
    try:
        while True:
            # Pull any newly appended lines before rendering.
            if watcher is not None:
                new_lines = watcher.get_new_lines()
                if new_lines:
                    was_at_bottom = follow and (scroll_pos >= total_lines - 1)
                    output_lines.extend(new_lines)
                    total_lines = len(output_lines)
                    if was_at_bottom:
                        scroll_pos = max(0, total_lines - 1)
            else:
                # Best-effort live refresh from buffer (no log file)
                latest = list(_STATE.console_output)
                if latest and latest != output_lines:
                    was_at_bottom = follow and (scroll_pos >= total_lines - 1)
                    output_lines = latest
                    total_lines = len(output_lines)
                    if was_at_bottom:
                        scroll_pos = max(0, total_lines - 1)

            clear_screen()
            width, height = get_terminal_size()
            
            # Reserve space for header and footer
            content_height = height - 6
            
            # Calculate visible window
            start = max(0, scroll_pos - content_height + 1)
            end = min(total_lines, start + content_height)
            visible = output_lines[start:end]
            
            # Scroll indicator
            if total_lines <= content_height:
                scroll_pct = "ALL"
            elif scroll_pos <= content_height - 1:
                scroll_pct = "TOP"
            elif scroll_pos >= total_lines - 1:
                scroll_pct = "BOT"
            else:
                scroll_pct = f"{int(100 * scroll_pos / (total_lines - 1))}%"
            
            title = f"{_STATE.console_title} [{scroll_pct}] ({scroll_pos + 1}/{total_lines})"
            
            if r and _STATE.console:
                # Draw with rich panel
                visible_text = "\n".join(visible)
                panel = r["Panel"](
                    visible_text,
                    title=f"[cyan]{title}[/cyan]",
                    subtitle="[dim]↑/↓/scroll:move  PgUp/PgDn:page  q:exit[/dim]",
                    border_style="cyan",
                    height=content_height + 2,
                    padding=(0, 1),
                )
                _STATE.console.print(panel)
            else:
                print("=" * width)
                print(f" {title}")
                print("=" * width)
                for line in visible:
                    print(f" {line}"[:width-1])
                # Pad remaining lines
                for _ in range(content_height - len(visible)):
                    print()
                print("=" * width)
                print(" ↑/↓/scroll:move  PgUp/PgDn:page  q:exit")
            
            # Get input (with mouse support)
            key = _getch_with_mouse()
            
            if key is None:
                continue  # Ignore unhandled mouse events
            if key in ('q', 'Q', '\x1b', 'ESC', '\r', '\n', '\t'):
                break
            elif key in ('UP', 'k', 'K', 'SCROLL_UP'):
                scroll_pos = max(0, scroll_pos - 1)
                follow = False
            elif key in ('DOWN', 'j', 'J', ' ', 'SCROLL_DOWN'):
                scroll_pos = min(total_lines - 1, scroll_pos + 1)
                if scroll_pos >= total_lines - 1:
                    follow = True
            elif key == 'PGUP':
                scroll_pos = max(0, scroll_pos - content_height)
                follow = False
            elif key == 'PGDN':
                scroll_pos = min(total_lines - 1, scroll_pos + content_height)
                if scroll_pos >= total_lines - 1:
                    follow = True
            elif key in ('g', 'HOME'):
                scroll_pos = 0
                follow = False
            elif key in ('G', 'END'):
                scroll_pos = total_lines - 1
                follow = True
    finally:
        # Always disable mouse tracking when exiting
        _disable_mouse()
        if watcher is not None:
            try:
                watcher.stop()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Fallback prompts (no questionary)
# ---------------------------------------------------------------------------

def _fallback_select(message: str, choices: List[str]) -> Optional[str]:
    print(f"\n{message}")
    for i, c in enumerate(choices, 1):
        print(f"  {i}) {c}")
    try:
        idx = int(input("Enter number: ").strip()) - 1
        if 0 <= idx < len(choices):
            return choices[idx]
    except (ValueError, EOFError, KeyboardInterrupt):
        pass
    return None


def _fallback_text(message: str, default: str = "") -> str:
    try:
        prompt = f"{message}"
        if default:
            prompt += f" [{default}]"
        prompt += ": "
        val = input(prompt).strip()
        return val if val else default
    except (EOFError, KeyboardInterrupt):
        return default


def _fallback_confirm(message: str, default: bool = False) -> bool:
    try:
        prompt = f"{message} [{'Y/n' if default else 'y/N'}]: "
        val = input(prompt).strip().lower()
        if not val:
            return default
        return val in ("y", "yes", "1", "true")
    except (EOFError, KeyboardInterrupt):
        return default


# ---------------------------------------------------------------------------
# Form-based input (all fields visible with Tab navigation)
# ---------------------------------------------------------------------------

def _get_field_placeholder(field: dict) -> str:
    """Get a placeholder/example for a field based on its type and id."""
    return tool_parser.get_field_placeholder(field)


def render_form_field(field: dict, value: str, selected: bool, width: int = 60) -> str:
    """Render a single form field with current value or placeholder."""
    r = _import_rich()
    
    fid = field.get("id", "field")
    fname = field.get("name", fid)
    ftype = field.get("type", "text")
    placeholder = _get_field_placeholder(field)
    
    # Determine display value
    if value:
        display_val = value
        val_style = "white"
    elif placeholder:
        display_val = placeholder
        val_style = "dim italic"
    else:
        display_val = "(empty)"
        val_style = "dim"
    
    # Checkbox special handling
    if ftype == "checkbox":
        checked = "☑" if value else "☐"
        display_val = checked
        val_style = "cyan" if value else "dim"
    
    # Selection indicator
    indicator = "▶ " if selected else "  "
    
    # Truncate if too long
    max_val_len = width - len(fname) - 10
    if len(display_val) > max_val_len:
        display_val = display_val[:max_val_len-3] + "..."
    
    if r and _STATE.console:
        if selected:
            return f"[cyan bold]{indicator}[/][white]{fname}:[/] [{val_style}]{display_val}[/]"
        else:
            return f"[dim]{indicator}[/][white]{fname}:[/] [{val_style}]{display_val}[/]"
    else:
        return f"{indicator}{fname}: {display_val}"


def run_form_editor(fields: List[dict], initial_values: Optional[dict] = None) -> Optional[dict]:
    """
    Interactive form editor showing all fields at once.
    
    Controls:
    - Tab/Down: Next field
    - Shift+Tab/Up: Previous field  
    - Enter on field: Edit field value
    - Enter on [Submit]: Submit form
    - Esc/q: Cancel
    
    Returns field values dict or None if cancelled.
    """
    r = _import_rich()
    q = _import_questionary()
    
    if not fields:
        return {}
    
    # Initialize values
    values = {}
    for field in fields:
        fid = field.get("id", "")
        if initial_values and fid in initial_values:
            values[fid] = initial_values[fid]
        elif field.get("type") == "checkbox":
            values[fid] = field.get("default", False)
        else:
            values[fid] = ""
    
    selected_idx = 0
    total_items = len(fields) + 1  # fields + submit button
    
    while True:
        # Clear and redraw form
        clear_screen()
        width, height = get_terminal_size()
        
        if r and _STATE.console:
            _STATE.console.print()
            _STATE.console.print("[bold cyan]Form Editor[/] [dim](Tab:next  Enter:edit  Esc:cancel)[/dim]")
            _STATE.console.print()
            
            for i, field in enumerate(fields):
                fid = field.get("id", "")
                line = render_form_field(field, values.get(fid, ""), i == selected_idx, width)
                _STATE.console.print(line)
            
            # Submit button
            _STATE.console.print()
            if selected_idx == len(fields):
                _STATE.console.print("[cyan bold]▶ [/][green bold][ Submit ][/]")
            else:
                _STATE.console.print("[dim]  [/][dim][ Submit ][/]")
            
            _STATE.console.print()
            _STATE.console.print("[dim]Tab/↓: next field | Shift+Tab/↑: prev | Enter: edit/submit | Esc: cancel[/dim]")
        else:
            print("\nForm Editor (Tab:next  Enter:edit  Esc:cancel)\n")
            for i, field in enumerate(fields):
                fid = field.get("id", "")
                line = render_form_field(field, values.get(fid, ""), i == selected_idx, width)
                print(line)
            print()
            if selected_idx == len(fields):
                print("▶ [ Submit ]")
            else:
                print("  [ Submit ]")
        
        # Get input
        key = _getch()
        
        if key in ('\x1b', 'ESC', 'q', 'Q'):
            return None
        elif key in ('\t', 'DOWN', 'j'):
            selected_idx = (selected_idx + 1) % total_items
        elif key in ('UP', 'k', 'K'):
            selected_idx = (selected_idx - 1) % total_items
        elif key in ('\r', '\n'):
            if selected_idx == len(fields):
                # Submit
                return values
            else:
                # Edit selected field
                field = fields[selected_idx]
                fid = field.get("id", "")
                fname = field.get("name", fid)
                ftype = field.get("type", "text")
                placeholder = _get_field_placeholder(field)
                current = values.get(fid, "")
                
                if ftype == "checkbox":
                    # Toggle checkbox
                    values[fid] = not values.get(fid, False)
                elif ftype == "select":
                    # Show select menu
                    options = field.get("options", [])
                    if options:
                        print()
                        new_val = prompt_select_option(fname, options, current or placeholder)
                        values[fid] = new_val
                else:
                    # Text/path input
                    print()
                    default = current if current else placeholder
                    if ftype == "directory":
                        new_val = prompt_path(fname, default, is_dir=True)
                    elif ftype == "file":
                        new_val = prompt_path(fname, default, is_dir=False)
                    else:
                        new_val = prompt_text(fname, default, required=False)
                    
                    # Only update if user entered something (not just accepting placeholder)
                    if new_val and new_val != placeholder:
                        values[fid] = new_val
                    elif new_val == "":
                        values[fid] = ""


# ---------------------------------------------------------------------------
# Interactive prompts (with fallback)
# ---------------------------------------------------------------------------

def prompt_select(message: str, choices: List[Tuple[str, Any]], back_option: bool = True) -> Optional[Any]:
    """Show a selection menu. Returns the value associated with the choice."""
    q = _import_questionary()

    display_choices = [c[0] for c in choices]
    if back_option:
        display_choices.append("← Back")

    if q:
        try:
            result = q["questionary"].select(
                message,
                choices=display_choices,
                style=Q_STYLE,
                use_shortcuts=True,
            ).ask()

            if result is None or result == "← Back":
                return None

            for c in choices:
                if c[0] == result:
                    return c[1]
            return None
        except Exception:
            pass

    # Fallback
    result = _fallback_select(message, display_choices)
    if result is None or result == "← Back":
        return None
    for c in choices:
        if c[0] == result:
            return c[1]
    return None


def prompt_text(message: str, default: str = "", required: bool = False) -> str:
    """Prompt for text input."""
    q = _import_questionary()

    if q:
        try:
            while True:
                result = q["questionary"].text(
                    message,
                    default=default,
                    style=Q_STYLE,
                ).ask()
                if result is None:
                    return default
                if required and not result.strip():
                    print("  This field is required.")
                    continue
                return result
        except Exception:
            pass

    # Fallback
    while True:
        result = _fallback_text(message, default)
        if required and not result.strip():
            print("  This field is required.")
            continue
        return result


def prompt_path(message: str, default: str = "", is_dir: bool = False) -> str:
    """Prompt for a file/directory path with completion if available."""
    q = _import_questionary()

    if q:
        try:
            from questionary import path as q_path
            result = q["questionary"].path(
                message,
                default=default,
                only_directories=is_dir,
                style=Q_STYLE,
            ).ask()
            return result if result else default
        except Exception:
            # path() might not be available in older questionary
            pass

    # Fallback to text
    return prompt_text(message, default)


def prompt_confirm(message: str, default: bool = False) -> bool:
    """Yes/no confirmation."""
    q = _import_questionary()

    if q:
        try:
            result = q["questionary"].confirm(
                message,
                default=default,
                style=Q_STYLE,
            ).ask()
            return result if result is not None else default
        except Exception:
            pass

    return _fallback_confirm(message, default)


def prompt_checkbox(message: str, choices: List[Tuple[str, str, bool]]) -> List[str]:
    """Multi-select checkbox. choices = [(display, value, default_checked), ...]"""
    q = _import_questionary()

    if q:
        try:
            from questionary import Choice
            q_choices = [
                Choice(title=c[0], value=c[1], checked=c[2])
                for c in choices
            ]
            result = q["questionary"].checkbox(
                message,
                choices=q_choices,
                style=Q_STYLE,
            ).ask()
            return result if result else []
        except Exception:
            pass

    # Fallback: show each as y/n
    selected = []
    print(f"\n{message}")
    for display, value, default in choices:
        if prompt_confirm(f"  {display}?", default):
            selected.append(value)
    return selected


def prompt_select_option(message: str, options: List[str], default: str = "") -> str:
    """Select from a list of string options."""
    q = _import_questionary()

    if q:
        try:
            result = q["questionary"].select(
                message,
                choices=options,
                default=default if default in options else None,
                style=Q_STYLE,
            ).ask()
            return result if result else (default or options[0])
        except Exception:
            pass

    result = _fallback_select(message, options)
    return result if result else (default or options[0])


# ---------------------------------------------------------------------------
# Output rendering (to console buffer)
# ---------------------------------------------------------------------------

def print_header(title: str):
    """Print a styled header."""
    r = _import_rich()
    if r and _STATE.console:
        _STATE.console.print()
        _STATE.console.print(r["Panel"](
            r["Text"](title, style="bold white"),
            border_style="cyan",
            padding=(0, 2),
        ))
    else:
        print(f"\n{'=' * 60}")
        print(f"  {title}")
        print('=' * 60)


def console_print(message: str, style: str = ""):
    """Print to both screen and console buffer."""
    _STATE.add_output(message)
    r = _import_rich()
    if r and _STATE.console:
        if style:
            _STATE.console.print(f"[{style}]{message}[/{style}]")
        else:
            _STATE.console.print(message)
    else:
        print(message)


def print_info(message: str, to_buffer: bool = False):
    r = _import_rich()
    formatted = f"ℹ {message}"
    if to_buffer:
        _STATE.add_output(formatted)
    if r and _STATE.console:
        _STATE.console.print(f"[cyan]ℹ[/cyan] {message}")
    else:
        print(f"[INFO] {message}")


def print_success(message: str, to_buffer: bool = False):
    r = _import_rich()
    formatted = f"✓ {message}"
    if to_buffer:
        _STATE.add_output(formatted)
    if r and _STATE.console:
        _STATE.console.print(f"[green]✓[/green] {message}")
    else:
        print(f"[OK] {message}")


def print_warning(message: str, to_buffer: bool = False):
    r = _import_rich()
    formatted = f"⚠ {message}"
    if to_buffer:
        _STATE.add_output(formatted)
    if r and _STATE.console:
        _STATE.console.print(f"[yellow]⚠[/yellow] {message}")
    else:
        print(f"[WARN] {message}")


def print_error(message: str, to_buffer: bool = False):
    r = _import_rich()
    formatted = f"✗ {message}"
    if to_buffer:
        _STATE.add_output(formatted)
    if r and _STATE.console:
        _STATE.console.print(f"[red]✗[/red] {message}")
    else:
        print(f"[ERROR] {message}")


# ---------------------------------------------------------------------------
# Command execution (outputs to console buffer with progress tracking)
# ---------------------------------------------------------------------------

def _format_progress_bar(percent: int, width: int = 28) -> str:
    try:
        pct = max(0, min(100, int(percent)))
    except Exception:
        pct = 0
    filled = int(width * (pct / 100.0))
    return "[" + ("█" * filled) + ("░" * (width - filled)) + "]"

def run_command(argv: List[str], show_output: bool = True) -> Tuple[int, str]:
    """Run a command and stream output via a log file.

    Key behavior:
    - Subprocess writes ONLY to a log file.
    - A LogWatcher pumps new lines into the console buffer.
    - The UI redraws the pinned console panel on a refresh loop.
    """
    from shared import start_subprocess_to_log

    r = _import_rich()

    cmd_str = " ".join(argv)
    _STATE.console_title = f"Running: {cmd_str[:40]}..."
    _STATE.add_output(f"$ {cmd_str}")
    _STATE.add_output("")

    start_time = time.time()
    progress_lock = threading.Lock()
    last_progress = {"percent": 0, "message": "", "current": None, "total": None}

    log_dir = os.path.join(_STATE.base_dir, ".logs")

    def _on_line(line: str):
        # LogWatcher yields lines without newlines.
        line_stripped = line.rstrip("\n")
        if line_stripped:
            _STATE.add_output(line_stripped)

        progress = tool_parser.parse_progress(line_stripped)
        if progress:
            with progress_lock:
                last_progress.update(progress)

    try:
        task = start_subprocess_to_log(
            argv,
            cwd=_STATE.base_dir,
            log_dir=log_dir,
            log_prefix="textui",
            env={"PYTHONUNBUFFERED": "1"},
            threads=tool_parser.get_global_threads(),
            on_line=_on_line,
            poll_interval=0.05,
        )

        # Expose the active log file so the console viewer can tail it live.
        _STATE.current_log_file = task.log_file

        # Live refresh loop: keep the console panel updated while running.
        while not task.done():
            try:
                if r and _STATE.console:
                    _STATE.console.clear()
                else:
                    clear_screen()

                draw_console_panel(menu_item_count=3)
                print()

                if show_output:
                    print_header("Running")
                    print_info(f"Command: {cmd_str}")

                    with progress_lock:
                        pct = int(last_progress.get("percent") or 0)
                        msg = (last_progress.get("message") or "").strip()
                        cur = last_progress.get("current")
                        tot = last_progress.get("total")

                    eta = tool_parser.estimate_eta(start_time, pct) if pct > 0 else None
                    detail = ""
                    if cur is not None and tot is not None:
                        detail = f" ({cur}/{tot})"

                    if pct > 0 or msg:
                        bar = _format_progress_bar(pct)
                        line = f"{bar} {pct}% {msg}{detail}" + (f" | ETA: {eta}" if eta else "")
                        print_info(line)
                    else:
                        print_info("Progress: (waiting for output…)")

                    print_warning("Press Ctrl+C to stop", to_buffer=False)

                time.sleep(0.15)
            except KeyboardInterrupt:
                _STATE.add_output("")
                _STATE.add_output("✗ Cancel requested; stopping process…")
                task.stop(grace=1.0)
                break

        # Ensure completion state is known
        rc = task.wait(timeout=2.0)
        rc = rc if rc is not None else (task.exit_code if task.exit_code is not None else 1)

        elapsed = time.time() - start_time
        elapsed_str = f"{elapsed:.1f}s" if elapsed < 60 else f"{int(elapsed//60)}m {int(elapsed%60)}s"

        if rc == 0:
            _STATE.add_output("")
            _STATE.add_output(f"✓ Command completed successfully in {elapsed_str}.")
            _STATE.console_title = "Console Output (Success)"
        else:
            _STATE.add_output("")
            _STATE.add_output(f"✗ Command exited with code {rc} after {elapsed_str}.")
            _STATE.console_title = f"Console Output (Exit: {rc})"

        # Return the log contents (best-effort)
        output = ""
        try:
            with open(task.log_file, "r", encoding="utf-8", errors="replace") as f:
                output = f.read()
        except Exception:
            output = ""

        return int(rc), output

    except Exception as e:
        err_msg = f"Failed to run command: {e}"
        _STATE.add_output(f"✗ {err_msg}")
        _STATE.console_title = "Console Output (Error)"
        print_error(err_msg)
        return 1, str(e)


def run_command_string(cmd: str, show_output: bool = True) -> Tuple[int, str]:
    """Run a command string."""
    posix = os.name != "nt"
    argv = shlex.split(cmd, posix=posix)
    return run_command(argv, show_output)


# ---------------------------------------------------------------------------
# Tool-specific UI
# ---------------------------------------------------------------------------

def get_tool_webui_config(tool_id: str) -> Optional[dict]:
    """Load webui_config from a tool's module."""
    return tool_parser.get_tool_webui_config(tool_id, _STATE.tools)


def build_command_from_action(tool_id: str, action: dict, field_values: dict) -> str:
    """Build a CLI command from action config and field values."""
    return tool_parser.build_command_from_action(tool_id, action, field_values)


def run_tool_action_form(tool_id: str, action: dict):
    """Interactive form for a tool action using form editor."""
    action_name = action.get("name", "Action")
    action_desc = action.get("description", "")
    fields = action.get("fields", [])

    # Show header first
    clear_screen()
    print_header(action_name)
    if action_desc:
        print_info(action_desc)
    print()
    
    # Use form editor for all fields at once
    field_values = run_form_editor(fields)
    
    if field_values is None:
        # User cancelled
        return
    
    # Build and confirm command
    cmd = build_command_from_action(tool_id, action, field_values)
    
    clear_screen()
    draw_console_panel(menu_item_count=4)
    print()
    print_header(action_name)
    print()
    print_info(f"Command: {cmd}")

    if prompt_confirm("Run this command?", default=True):
        _STATE.clear_console()
        run_command_string(cmd)
        # Redraw with output
        clear_screen()
        draw_console_panel(menu_item_count=2)  # Just "Press Enter"
        print()
        print_header(f"{action_name} - Complete")

    input("\nPress Enter to continue...")


def show_readme(tool_id: str = None):
    """Display README.md with markdown rendering.
    
    Args:
        tool_id: Tool ID to show README for, or None for main README
    """
    r = _import_rich()
    
    # Determine README path
    if tool_id:
        readme_path = os.path.join(_STATE.base_dir, tool_id, "README.md")
        title = f"{tool_id.replace('_', ' ').title()} Documentation"
    else:
        readme_path = os.path.join(_STATE.base_dir, "README.md")
        title = "Deer Toolbox Documentation"
    
    # Read README content
    try:
        with open(readme_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        print_error(f"README not found: {readme_path}")
        input("\nPress Enter to continue...")
        return
    except Exception as e:
        print_error(f"Error reading README: {e}")
        input("\nPress Enter to continue...")
        return
    
    # Render with rich Markdown if available, otherwise plain text
    if r and _STATE.console:
        clear_screen()
        _STATE.console.print(r["Panel"](
            r["Text"](title, style="bold cyan", justify="center"),
            border_style="cyan",
            padding=(0, 2),
        ))
        _STATE.console.print()
        
        try:
            md = r["Markdown"](content)
            _STATE.console.print(md)
        except Exception:
            # Fallback to plain text
            _STATE.console.print(content)
    else:
        clear_screen()
        print("=" * 80)
        print(f"  {title}")
        print("=" * 80)
        print()
        print(content)
    
    print()
    input("Press Enter to continue...")


def show_tool_menu(tool_id: str):
    """Show the menu for a specific tool."""
    meta = _STATE.tools.get(tool_id, {})
    name = meta.get("name", tool_id.replace("_", " ").title())
    desc = meta.get("description", "")

    config = get_tool_webui_config(tool_id)

    while True:
        # Calculate menu size: actions + standard options (Docs, Help, Custom, Scroll, Clear) + Back
        action_count = len(config.get("actions", [])) if config else 0
        menu_item_count = action_count + 6  # 5 standard options + back
        
        clear_screen()
        
        # Console panel at top (pinned)
        draw_console_panel(menu_item_count=menu_item_count)
        print()
        
        # Header below console
        print_header(name)
        
        # Description below header
        if desc:
            print_info(desc)
        print()

        choices = []

        # Add actions from webui_config
        if config:
            for action in config.get("actions", []):
                action_name = action.get("name", "Action")
                choices.append((f"▶ {action_name}", ("action", action)))

        # Add standard options
        cli_name = tool_id.replace("_", "-")
        py = shlex.quote(sys.executable)

        choices.append(("📄 Show Help", ("cmd", f"{py} toolbox.py {cli_name} --help")))
        choices.append(("🖥 Run Custom Command", ("custom", None)))
        choices.append(("� Scroll Console [Tab]", ("scroll", None)))
        choices.append(("�🗑 Clear Console", ("clear", None)))

        result = prompt_select(f"Select action for {name}:", choices)

        if result is None:
            break

        action_type, action_data = result

        if action_type == "action":
            run_tool_action_form(tool_id, action_data)
        elif action_type == "readme":
            show_readme(tool_id)
        elif action_type == "cmd":
            _STATE.clear_console()
            run_command_string(action_data)
            # Redraw with output
            clear_screen()
            draw_console_panel(menu_item_count=2)  # Just "Press Enter"
            print()
            print_header(name)
            input("\nPress Enter to continue...")
        elif action_type == "custom":
            default_cmd = f"{py} toolbox.py {cli_name} "
            cmd = prompt_text("Enter command:", default_cmd)
            if cmd.strip():
                _STATE.clear_console()
                run_command_string(cmd)
                clear_screen()
                draw_console_panel(menu_item_count=2)  # Just "Press Enter"
                print()
                print_header(name)
                input("\nPress Enter to continue...")
        elif action_type == "scroll":
            show_console_viewer()
        elif action_type == "clear":
            _STATE.clear_console()
            _STATE.console_title = "Console Output"


# ---------------------------------------------------------------------------
# Doctor
# ---------------------------------------------------------------------------

def run_doctor():
    """Run environment checks (same as toolbox doctor)."""
    clear_screen()
    draw_console_panel(menu_item_count=2)  # Just "Press Enter"
    print()
    print_header("Doctor - Environment Check")

    _STATE.clear_console()
    py = shlex.quote(sys.executable)
    run_command_string(f"{py} toolbox.py doctor")
    
    # Redraw with output
    clear_screen()
    draw_console_panel(menu_item_count=2)  # Just "Press Enter"
    print()
    print_header("Doctor - Complete")
    input("\nPress Enter to continue...")


# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------

def print_tools_table(tools: Dict[str, dict]):
    """Print a compact inline list of discovered tools."""
    r = _import_rich()

    if r and _STATE.console:
        tool_list = []
        for tool_id in sorted(tools.keys()):
            meta = tools[tool_id]
            name = meta.get("name", tool_id)
            tool_list.append(f"[cyan]{name}[/cyan]")
        _STATE.console.print(f"Tools: {' | '.join(tool_list)}")
    else:
        print("Tools: " + ", ".join(sorted(tools.keys())))


def show_main_menu():
    """Show the main TUI menu with pinned console."""
    _init_theme()

    # Initialize rich console if available
    r = _import_rich()
    if r:
        custom_theme = r["Theme"](GREY_THEME)
        _STATE.console = r["Console"](theme=custom_theme)

    # Discover tools
    _STATE.discover_tools()

    while True:
        # Calculate menu size: tools + utility options (Docs, Doctor, Custom, Scroll, Clear, Exit)
        menu_item_count = len(_STATE.tools) + 6
        
        clear_screen()
        
        # Console output panel at top (pinned)
        draw_console_panel(menu_item_count=menu_item_count)
        
        print()
        print_header("Toolbox TUI")

        if _STATE.tools:
            print_tools_table(_STATE.tools)
        
        print()

        # Build menu choices
        choices = []

        # Add tools
        for tool_id in sorted(_STATE.tools.keys()):
            meta = _STATE.tools[tool_id]
            name = meta.get("name", tool_id)
            icon = "🔧"
            if "extension" in tool_id.lower():
                icon = "📁"
            elif "hash" in tool_id.lower():
                icon = "🔒"
            elif "undo" in tool_id.lower():
                icon = "↩"
            choices.append((f"{icon} {name}", ("tool", tool_id)))

        # Add utility options
        choices.append(("📖 View Main Documentation", ("readme", None)))
        choices.append(("⚕ Doctor", ("doctor", None)))
        choices.append(("💻 Run Custom Command", ("custom", None)))
        choices.append(("� Scroll Console [Tab]", ("scroll", None)))
        choices.append(("�🗑 Clear Console", ("clear", None)))
        choices.append(("🚪 Exit", ("exit", None)))

        result = prompt_select("Select an option:", choices, back_option=False)

        if result is None or result[0] == "exit":
            clear_screen()
            print_info("Goodbye!")
            break

        action_type, action_data = result

        if action_type == "tool":
            show_tool_menu(action_data)
        elif action_type == "readme":
            show_readme(None)
        elif action_type == "doctor":
            run_doctor()
        elif action_type == "custom":
            py = shlex.quote(sys.executable)
            cmd = prompt_text("Enter command:", f"{py} toolbox.py ")
            if cmd.strip():
                _STATE.clear_console()
                run_command_string(cmd)
                # Screen will redraw on next loop
        elif action_type == "scroll":
            show_console_viewer()
        elif action_type == "clear":
            _STATE.clear_console()
            _STATE.console_title = "Console Output"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def check_dependencies() -> Tuple[bool, bool]:
    """Check if rich and questionary are available."""
    has_rich = _import_rich() is not None
    has_questionary = _import_questionary() is not None
    return has_rich, has_questionary


def launch_tui():
    """Launch the TUI."""
    has_rich, has_questionary = check_dependencies()

    if not has_rich and not has_questionary:
        print("[WARN] For the best experience, install: pip install rich questionary")
        print("[INFO] Running in fallback mode...")
    elif not has_rich:
        print("[INFO] Install 'rich' for better output: pip install rich")
    elif not has_questionary:
        print("[INFO] Install 'questionary' for better menus: pip install questionary")

    try:
        show_main_menu()
    except KeyboardInterrupt:
        print("\n")
        print_info("Interrupted. Goodbye!")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(launch_tui())
