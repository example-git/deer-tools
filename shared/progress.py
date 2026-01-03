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
    width = shutil.get_terminal_size((80, 20)).columns
    bar_width = max(10, width - 30)

    filled = int(bar_width * fraction)
    empty = bar_width - filled

    bar = "[" + "#" * filled + "-" * empty + "]"
    percent = f"{int(fraction * 100):3d}%"

    sys.stdout.write(f"\r{bar} {percent}  {message[:width-10]}")
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
    percent = int(fraction * 100)
    print(f"[{percent:3d}%] {message}", flush=True)
