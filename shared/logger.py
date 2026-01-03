"""
shared/logger.py
----------------

Universal buffered logger for high-performance logging.
Can be used by any tool that needs thread-safe, buffered file logging.

Features:
- Thread-safe buffered writes
- Automatic flushing at threshold
- Optional console mirroring
- Text and JSONL formats
- UTF-8 safe output
- Callback support for log streaming
"""

import threading
import json
from datetime import datetime


class BufferedLogger:
    """
    A high-performance, thread-safe logger that buffers log lines
    and writes them to disk in batches.

    This dramatically reduces I/O overhead when thousands of files
    are being processed in parallel.
    """

    def __init__(
        self,
        log_path,
        buffer_limit=200,
        mirror_to_console=False,
        log_format="text",
        on_line=None,
    ):
        """
        Args:
            log_path: Path to the log file
            buffer_limit: Number of lines before auto-flush
            mirror_to_console: If True, also print log lines to console
            log_format: "text" or "jsonl"
            on_line: Optional callback invoked with the final rendered line
        """
        self.log_path = log_path
        self.buffer_limit = buffer_limit
        self.buffer = []
        self.lock = threading.Lock()
        self.mirror = mirror_to_console
        self.log_format = (log_format or "text").lower()
        self.on_line = on_line

        # When True, diagnostics and other helpers can avoid printing to stdout
        self.suppress_console = False

        # Ensure file starts cleanly separated for text logs
        # For JSONL, avoid blank lines that can confuse strict parsers
        if self.log_format != "jsonl":
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write("\n")

    def _flush_locked(self):
        """Internal flush (requires lock already held)"""
        if not self.buffer:
            return

        text = "\n".join(self.buffer) + "\n"
        self.buffer.clear()

        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(text)

    def log(self, msg):
        """
        Append a timestamped message to the buffer.
        Auto-flush when buffer_limit is reached.
        """
        now = datetime.now()

        if self.log_format == "jsonl":
            payload = {
                "ts": now.isoformat(timespec="seconds"),
                "msg": str(msg),
            }
            line = json.dumps(payload, ensure_ascii=False)
        else:
            ts = now.strftime("%Y-%m-%d %H:%M:%S")
            line = f"[{ts}] {msg}"

        if self.mirror:
            print(line, flush=True)

        if self.on_line is not None:
            try:
                self.on_line(line)
            except Exception:
                # Logging must never crash the tool
                pass

        with self.lock:
            self.buffer.append(line)
            if len(self.buffer) >= self.buffer_limit:
                self._flush_locked()

    def flush(self):
        """
        Flush all buffered log lines to disk.
        Safe to call multiple times.
        """
        with self.lock:
            self._flush_locked()
