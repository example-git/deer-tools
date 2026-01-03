"""
tui.py
------

Shared Curses-based UI components for the Toolbox and its tools.
"""

import curses
import time
from collections import deque
from queue import Empty
import sys

def run_fixed_log_ui(
    *,
    log_queue,
    event_queue,
    log_height: int = 12,
    title: str = "Tool Output",
    on_done=None,
):
    """
    Run a curses UI that displays log lines in a fixed-height top window.
    """
    if not sys.stdout.isatty():
        # Fallback for non-TTY environments
        return

    def _curses_main(stdscr):
        curses.curs_set(0)
        stdscr.nodelay(True)
        stdscr.keypad(True)

        stats = None
        done_handled = False

        while True:
            height, width = stdscr.getmaxyx()
            top_h = max(3, min(int(log_height), max(3, height - 3)))
            bottom_h = max(1, height - top_h)

            log_win = curses.newwin(top_h, width, 0, 0)
            status_win = curses.newwin(bottom_h, width, top_h, 0)

            max_log_lines = max(1, top_h - 2)
            log_lines = deque(maxlen=max_log_lines)

            status_line = "Running... (press 'q' to hide UI)"
            progress_line = ""

            def redraw():
                log_win.erase()
                status_win.erase()

                # Header
                header = f"{title} — Logs".ljust(width - 1)
                try:
                    log_win.addnstr(0, 0, header, width - 1)
                except curses.error:
                    pass

                # Log body
                for i, line in enumerate(list(log_lines)[-max_log_lines:]):
                    try:
                        log_win.addnstr(1 + i, 0, line, width - 1)
                    except curses.error:
                        pass

                # Footer / separator
                try:
                    log_win.hline(top_h - 1, 0, curses.ACS_HLINE, width - 1)
                except curses.error:
                    pass

                # Status area
                try:
                    status_win.addnstr(0, 0, status_line, width - 1)
                    if bottom_h > 1 and progress_line:
                        status_win.addnstr(1, 0, progress_line, width - 1)
                except curses.error:
                    pass

                status_win.refresh()
                log_win.refresh()

            redraw()

            while True:
                # Handle keypress
                try:
                    ch = stdscr.getch()
                except Exception:
                    ch = -1
                if ch in (ord("q"), ord("Q")):
                    return stats

                drained = False

                # Drain log lines
                while True:
                    try:
                        line = log_queue.get_nowait()
                    except Empty:
                        break
                    log_lines.append(line)
                    drained = True

                # Drain worker events
                while True:
                    try:
                        ev = event_queue.get_nowait()
                    except Empty:
                        break

                    drained = True
                    if not ev:
                        continue

                    kind = ev[0]
                    if kind == "progress":
                        frac = ev[1]
                        msg = ev[2] if len(ev) > 2 else ""
                        pct = int((frac or 0) * 100)
                        # Full-width progress with percent pinned right.
                        right = f"{pct:3d}%"
                        left_width = max(0, (width - 1) - len(right) - 1)
                        left = (msg or "")
                        if len(left) > left_width:
                            left = ("..." + left[-(left_width - 3) :]) if left_width > 3 else left[-left_width:]
                        progress_line = f"{left.ljust(left_width)} {right}"[: width - 1]
                    elif kind == "error":
                        status_line = f"Error: {ev[1] if len(ev) > 1 else ''}"[: width - 1]
                    elif kind == "done":
                        stats = ev[1] if len(ev) > 1 else None
                        status_line = "Completed. Press 'q' to exit."[: width - 1]
                        progress_line = ""

                        if (not done_handled) and (on_done is not None):
                            done_handled = True
                            try:
                                on_done(stats)
                            except Exception:
                                pass

                if drained:
                    redraw()

                # If done, keep UI up until user quits.
                if stats is not None:
                    time.sleep(0.05)
                    continue

                time.sleep(0.05)

    return curses.wrapper(_curses_main)


class CursesMenu:
    def __init__(self, title, options):
        self.title = title
        self.options = options  # List of (label, callback)
        self.selected = 0

    def run(self):
        if not sys.stdout.isatty():
            return None
        try:
            return curses.wrapper(self._main)
        except curses.error:
            return None

    def _main(self, stdscr):
        curses.curs_set(0)
        stdscr.keypad(True)
        
        while True:
            stdscr.erase()
            height, width = stdscr.getmaxyx()
            
            # Draw title
            try:
                stdscr.addstr(1, 2, self.title, curses.A_BOLD)
                stdscr.hline(2, 2, curses.ACS_HLINE, width - 4)
            except curses.error:
                pass
            
            # Draw options
            for idx, (label, _) in enumerate(self.options):
                y = 4 + idx
                if y >= height - 1:
                    break
                
                prefix = "> " if idx == self.selected else "  "
                style = curses.A_REVERSE if idx == self.selected else curses.A_NORMAL
                try:
                    stdscr.addstr(y, 2, f"{prefix}{label}", style)
                except curses.error:
                    pass
            
            stdscr.refresh()
            
            key = stdscr.getch()
            
            if key == curses.KEY_UP:
                self.selected = (self.selected - 1) % len(self.options)
            elif key == curses.KEY_DOWN:
                self.selected = (self.selected + 1) % len(self.options)
            elif key in (curses.KEY_ENTER, 10, 13):
                return self.options[self.selected][1]
            elif key in (ord('q'), ord('Q')):
                return None
