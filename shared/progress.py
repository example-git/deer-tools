"""
shared/progress.py
------------------

Universal progress bar and progress tracking utilities.
Can be used by any tool for CLI progress visualization.

Features:
- Terminal-width aware progress bar rendering
- Simple draw/finish interface
- Thread-safe operation
"""

import sys
import shutil
import time


_LAST_NONTTY_PROGRESS = {
    "pct": None,
    "msg": None,
    "ts": 0.0,
}


def _truncate_left(text: str, max_len: int) -> str:
    if max_len <= 0:
        return ""
    if len(text) <= max_len:
        return text
    if max_len <= 3:
        return text[-max_len:]
    return "..." + text[-(max_len - 3) :]


def _format_full_width_progress_line(width: int, fraction: float, message: str) -> str:
    width = max(20, int(width or 0))
    try:
        frac = float(fraction)
    except (TypeError, ValueError):
        frac = 0.0
    frac = max(0.0, min(1.0, frac))

    pct_int = int(round(frac * 100))
    percent = f"{pct_int:3d}%"

    # Reserve space: "<message> <bar> <percent>"
    desired_msg = max(10, width // 2)
    inner_bar = width - len(percent) - 4 - desired_msg  # 4 = spaces + brackets
    inner_bar = max(10, inner_bar)

    bar = "[" + "#" * int(inner_bar * frac) + "-" * (inner_bar - int(inner_bar * frac)) + "]"
    msg_width = max(0, width - len(bar) - len(percent) - 2)
    msg = _truncate_left(message or "", msg_width)
    msg = msg.ljust(msg_width)
    line = f"{msg} {bar} {percent}"
    return line[:width]


def draw_progress_bar(fraction, message):
    """
    Draw a dynamic progress bar in the terminal.
    
    Args:
        fraction: Progress from 0.0 to 1.0
        message: Status text to display
    
    Example:
        draw_progress_bar(0.5, "Processing files...")
        # Output: [##########----------] 50%  Processing files...
    """
    # When running under the Text UI, tools often have stdout redirected to a
    # log file. Carriage-return updates won't be seen as new "lines", so the
    # Text UI can't parse progress. In non-TTY mode, emit newline-delimited
    # updates in a parseable format.
    if not sys.stdout.isatty():
        try:
            frac = float(fraction)
        except (TypeError, ValueError):
            frac = 0.0
        frac = max(0.0, min(1.0, frac))
        pct = int(round(frac * 100))

        now = time.time()
        last_pct = _LAST_NONTTY_PROGRESS.get("pct")
        last_msg = _LAST_NONTTY_PROGRESS.get("msg")
        last_ts = float(_LAST_NONTTY_PROGRESS.get("ts") or 0.0)

        # Throttle so we don't spam logs; always emit on percent change.
        should_emit = (pct != last_pct) or ((message or "") != (last_msg or ""))
        if should_emit and ((now - last_ts) >= 0.15 or pct in (0, 100)):
            _LAST_NONTTY_PROGRESS["pct"] = pct
            _LAST_NONTTY_PROGRESS["msg"] = message or ""
            _LAST_NONTTY_PROGRESS["ts"] = now
            # Parseable by toolbox.tool_parser.parse_progress
            print(f"[{pct:3d}%] {message}", flush=True)
        return

    width = shutil.get_terminal_size((80, 20)).columns
    line = _format_full_width_progress_line(width, fraction, message)
    sys.stdout.write("\r" + line)
    sys.stdout.flush()


def finish_progress(message="Done"):
    """
    Finish progress tracking and print a completion message.
    
    Args:
        message: Completion message to display
    """
    sys.stdout.write("\n" + message + "\n")
    sys.stdout.flush()


def cli_progress(fraction, message):
    """
    Simple CLI progress callback compatible with hashdb-style progress.
    
    Args:
        fraction: Progress from 0.0 to 1.0
        message: Status message
    """
    try:
        frac = float(fraction)
    except (TypeError, ValueError):
        frac = 0.0
    frac = max(0.0, min(1.0, frac))
    percent = int(round(frac * 100))
    print(f"[{percent:3d}%] {message}", flush=True)
