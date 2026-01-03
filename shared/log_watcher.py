"""
shared/log_watcher.py
---------------------

Log file watcher for real-time log streaming.
Used by webui and textui to monitor tool output.

Usage:
    from shared.log_watcher import LogWatcher

    watcher = LogWatcher("/path/to/logfile.log")
    watcher.start()
    
    # Get new lines (non-blocking)
    for line in watcher.get_new_lines():
        print(line)
    
    watcher.stop()
"""

import os
import time
import threading
from typing import List, Optional, Callable
from collections import deque


class LogWatcher:
    """
    Watches a log file for new content and buffers lines.
    Thread-safe for use with UI event loops.
    """
    
    def __init__(
        self,
        filepath: str,
        poll_interval: float = 0.1,
        max_buffer: int = 10000,
        on_line: Optional[Callable[[str], None]] = None,
    ):
        """
        Args:
            filepath: Path to the log file to watch
            poll_interval: Seconds between file checks
            max_buffer: Maximum lines to buffer
            on_line: Optional callback called for each new line
        """
        self.filepath = filepath
        self.poll_interval = poll_interval
        self.max_buffer = max_buffer
        self.on_line = on_line
        
        self._lines: deque = deque(maxlen=max_buffer)
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._position = 0
        self._file_existed = False
    
    def start(self):
        """Start watching the log file."""
        if self._thread is not None:
            return
        
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop watching the log file."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
    
    def get_new_lines(self) -> List[str]:
        """
        Get and clear buffered lines (non-blocking).
        Returns list of new lines since last call.
        """
        with self._lock:
            lines = list(self._lines)
            self._lines.clear()
            return lines
    
    def get_all_lines(self) -> List[str]:
        """
        Read entire log file from the start.
        Useful for initial load or refresh.
        """
        if not os.path.exists(self.filepath):
            return []
        
        try:
            with open(self.filepath, "r", encoding="utf-8", errors="replace") as f:
                return f.read().splitlines()
        except Exception:
            return []
    
    def _watch_loop(self):
        """Background thread that watches for file changes."""
        while not self._stop_event.is_set():
            try:
                self._check_file()
            except Exception:
                pass  # Don't crash on file errors
            
            self._stop_event.wait(self.poll_interval)
    
    def _check_file(self):
        """Check file for new content."""
        if not os.path.exists(self.filepath):
            if self._file_existed:
                # File was deleted, reset position
                self._position = 0
                self._file_existed = False
            return
        
        self._file_existed = True
        
        try:
            size = os.path.getsize(self.filepath)
            
            # File was truncated/rotated
            if size < self._position:
                self._position = 0
            
            # No new content
            if size == self._position:
                return
            
            # Read new content
            with open(self.filepath, "r", encoding="utf-8", errors="replace") as f:
                f.seek(self._position)
                new_content = f.read()
                self._position = f.tell()
            
            if new_content:
                new_lines = new_content.splitlines()
                with self._lock:
                    for line in new_lines:
                        self._lines.append(line)
                        if self.on_line:
                            try:
                                self.on_line(line)
                            except Exception:
                                pass
        except Exception:
            pass


class TempLogFile:
    """
    Creates a temporary log file for subprocess output.
    Useful when you need a dedicated log file per task.
    """
    
    def __init__(self, prefix: str = "task", suffix: str = ".log", directory: Optional[str] = None):
        """
        Args:
            prefix: Filename prefix
            suffix: Filename suffix
            directory: Directory for log file (default: system temp)
        """
        import tempfile
        
        if directory is None:
            directory = tempfile.gettempdir()
        
        os.makedirs(directory, exist_ok=True)
        
        # Create unique filename with timestamp
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        self.filepath = os.path.join(directory, f"{prefix}_{timestamp}_{os.getpid()}{suffix}")
        
        # Create empty file
        open(self.filepath, "w").close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
    
    def cleanup(self):
        """Remove the temporary log file."""
        try:
            if os.path.exists(self.filepath):
                os.remove(self.filepath)
        except Exception:
            pass


def watch_subprocess_log(
    filepath: str,
    process,
    on_line: Optional[Callable[[str], None]] = None,
    poll_interval: float = 0.1,
) -> List[str]:
    """
    Watch a log file while a subprocess runs.
    Returns all lines when process completes.
    
    Args:
        filepath: Log file path
        process: subprocess.Popen instance
        on_line: Callback for each new line
        poll_interval: Seconds between checks
        
    Returns:
        All lines from the log file
    """
    watcher = LogWatcher(filepath, poll_interval=poll_interval, on_line=on_line)
    watcher.start()
    
    all_lines = []
    
    try:
        while process.poll() is None:
            new_lines = watcher.get_new_lines()
            all_lines.extend(new_lines)
            time.sleep(poll_interval)
        
        # Final read after process exits
        time.sleep(0.1)  # Brief delay for final flush
        new_lines = watcher.get_new_lines()
        all_lines.extend(new_lines)
    finally:
        watcher.stop()
    
    return all_lines
