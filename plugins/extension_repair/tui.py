"""
tui.py
------

Curses-based console UI for CLI mode.

Shows a fixed-height log window at the top and a status/progress
area below it.

This is optional and only used when running in a real TTY.
"""

from __future__ import annotations

import curses
import time
from collections import deque
from queue import Empty


def run_fixed_log_ui(
    *,
    log_queue,
    event_queue,
    log_height: int = 12,
    title: str = "Extension Repair",
    on_done=None,
):
    """
    Run a curses UI that displays log lines in a fixed-height top window.

    log_queue: queue of rendered log lines (strings)
    event_queue: queue of worker events (tuples like ("progress", frac, msg) or ("done", stats))
    log_height: desired height of the log window
    on_done: optional callback invoked once with stats when worker sends ("done", stats)

    Returns the stats dict if received, else None.
    """

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

            status_line = "Starting… (press 'q' to hide UI)"
            progress_line = ""

            def redraw():
                log_win.erase()
                status_win.erase()

                # Header
                header = f"{title} — Logs".ljust(width - 1)
                log_win.addnstr(0, 0, header, width - 1)

                # Log body
                for i, line in enumerate(list(log_lines)[-max_log_lines:]):
                    log_win.addnstr(1 + i, 0, line, width - 1)

                # Footer / separator
                log_win.hline(top_h - 1, 0, curses.ACS_HLINE, width - 1)

                # Status area
                status_win.addnstr(0, 0, status_line, width - 1)
                if bottom_h > 1 and progress_line:
                    status_win.addnstr(1, 0, progress_line, width - 1)

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
                        progress_line = f"[{pct:3d}%] {msg}"
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
                                # Keep UI resilient.
                                pass

                if drained:
                    redraw()

                # If done, keep UI up until user quits.
                if stats is not None:
                    time.sleep(0.05)
                    continue

                time.sleep(0.05)

    return curses.wrapper(_curses_main)
