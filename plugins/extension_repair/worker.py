"""
worker.py
---------

Threaded worker for the upgraded Extension Repair Tool.

Responsibilities:
- Recursively scan directories using shared scanner utilities
- Detect file types (strict mode)
- Apply rename logic with conflict-proof behavior
- Support in-place or output-directory repairs
- Support report-only, quarantine, and force-rename modes
- Emit progress updates for GUI
- Return detailed stats for diagnostics
"""

import os
import threading
from concurrent.futures import as_completed
from concurrent.futures.thread import ThreadPoolExecutor

from .detector import detect_file_type
from shared.path_utils import (
    get_extension,
    build_new_name,
    safe_rename,
    is_zero_byte,
)
from .diagnostics import init_stats

# Import shared scanner utilities
from shared import (
    iter_files as _iter_files,
    iter_files_chunked as _iter_files_chunked,
    collect_files as _collect_files,
    collect_files_chunked as _collect_files_chunked,
    DEFAULT_CHUNK_SIZE,
)


# ------------------------------------------------------------
# File collection wrappers (use shared utilities with strings)
# ------------------------------------------------------------
def iter_files(root):
    """Yield file paths as strings."""
    return _iter_files(root, as_path=False)


def iter_files_chunked(root, chunk_size=DEFAULT_CHUNK_SIZE):
    """Yield chunks of file path strings."""
    return _iter_files_chunked(root, chunk_size, as_path=False)


def collect_files(root):
    """Collect all files as strings."""
    return _collect_files(root, as_path=False)


def collect_files_chunked(root, chunk_size=DEFAULT_CHUNK_SIZE, callback=None):
    """Collect files in chunks as strings."""
    return _collect_files_chunked(root, chunk_size, callback, as_path=False)


# ------------------------------------------------------------
# Worker Thread
# ------------------------------------------------------------
class ExtensionRepairWorker(threading.Thread):
    """
    Threaded worker that processes files and emits progress updates.

    Emits queue messages:
        ("progress", fraction, message)
        ("done", stats)
        ("error", message)
    """

    def __init__(self, settings, logger, queue=None):
        super().__init__()
        self.settings = settings
        self.logger = logger
        self.queue = queue  # GUI queue or None for CLI
        self.stats = init_stats()

    # --------------------------------------------------------
    # Helper: emit progress to GUI
    # --------------------------------------------------------
    def emit(self, kind, *payload):
        if self.queue:
            self.queue.put((kind, *payload))

    # --------------------------------------------------------
    # Main thread entry
    # --------------------------------------------------------
    def run(self):
        try:
            self._run_internal()
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.emit("error", str(e))
            self.logger.log(f"FATAL ERROR: {e}")

    # --------------------------------------------------------
    # Internal logic
    # --------------------------------------------------------
    def _run_internal(self):
        settings = self.settings
        target_dir = settings["TARGET_DIRECTORY"]
        in_place = settings["IN_PLACE"]
        out_dir = settings["OUTPUT_DIRECTORY"]
        dry_run = settings["DRY_RUN"]
        report_only = settings["REPORT_ONLY"]
        quarantine = settings["QUARANTINE_MODE"]
        force_rename = settings["FORCE_RENAME"]
        skip_ambiguous_iso = settings["SKIP_AMBIGUOUS_ISO"]
        thread_count = settings.get("THREAD_COUNT", 8)

        # ----------------------------------------------------
        # Collect files with chunked scanning + progress
        # ----------------------------------------------------
        self.logger.log(f"Scanning directory: {target_dir}")
        def on_scan_chunk(_chunk, total_so_far):
            self.emit("progress", 0.0, f"Scanning... found {total_so_far} files")
            self.logger.log(f"Scan progress: {total_so_far} files found")

        files = collect_files_chunked(target_dir, DEFAULT_CHUNK_SIZE, on_scan_chunk)
        total = len(files)
        self.logger.log(f"Found {total} files.")

        if total == 0:
            self.emit("done", self.stats)
            return

        # ----------------------------------------------------
        # Ensure output directory exists if needed
        # ----------------------------------------------------
        if not in_place:
            os.makedirs(out_dir, exist_ok=True)

        # ----------------------------------------------------
        # Ensure quarantine directory exists if needed
        # ----------------------------------------------------
        quarantine_dir = None
        if quarantine:
            quarantine_dir = os.path.join(target_dir, "_quarantine")
            os.makedirs(quarantine_dir, exist_ok=True)

        # Thread-safe counter for progress
        progress_lock = threading.Lock()
        processed = [0]  # mutable container for closure

        def process_file(path):
            """Process a single file - designed for ThreadPoolExecutor."""
            rel = os.path.relpath(path, target_dir)
            result = {"path": path, "action": None, "detail": None}

            # ------------------------------------------------
            # Detect file type
            # ------------------------------------------------
            ext, reason = detect_file_type(path)

            # Handle detection failures
            if ext is None:
                result["action"] = "skip"
                result["detail"] = reason
                return result

            # ------------------------------------------------
            # Compare extension
            # ------------------------------------------------
            current_ext = get_extension(path)

            # Already correct?
            if current_ext == ext:
                result["action"] = "correct"
                return result

            # ------------------------------------------------
            # Ambiguous ISO BMFF handling
            # ------------------------------------------------
            if reason == "ambiguous_iso":
                if skip_ambiguous_iso and not force_rename:
                    result["action"] = "skip"
                    result["detail"] = "ambiguous_iso"
                    return result

            # ------------------------------------------------
            # Determine target directory
            # ------------------------------------------------
            if in_place:
                base_dir = os.path.dirname(path)
            else:
                base_dir = os.path.join(out_dir, os.path.dirname(rel))
                os.makedirs(base_dir, exist_ok=True)

            # ------------------------------------------------
            # Build new name
            # ------------------------------------------------
            original_name = os.path.basename(path)
            new_path = build_new_name(base_dir, original_name, ext)

            # ------------------------------------------------
            # Report-only mode
            # ------------------------------------------------
            if report_only:
                result["action"] = "report"
                result["detail"] = (path, new_path, ext)
                return result

            # ------------------------------------------------
            # Quarantine mode
            # ------------------------------------------------
            if quarantine:
                assert quarantine_dir is not None
                q_target = os.path.join(quarantine_dir, os.path.basename(path))
                status, detail = safe_rename(path, q_target)
                result["action"] = "quarantine"
                result["detail"] = (status, detail)
                return result

            # ------------------------------------------------
            # Dry-run mode
            # ------------------------------------------------
            if dry_run:
                result["action"] = "dry_run"
                result["detail"] = (path, new_path, ext)
                return result

            # ------------------------------------------------
            # Actual rename
            # ------------------------------------------------
            status, detail = safe_rename(path, new_path)
            result["action"] = "rename"
            result["detail"] = (status, detail, ext)
            return result

        # ----------------------------------------------------
        # Process files with ThreadPoolExecutor
        # ----------------------------------------------------
        with ThreadPoolExecutor(max_workers=thread_count) as executor:
            futures = {executor.submit(process_file, path): path for path in files}
            
            for future in as_completed(futures):
                path = futures[future]
                rel = os.path.relpath(path, target_dir)
                
                with progress_lock:
                    processed[0] += 1
                    fraction = processed[0] / total
                    self.emit("progress", fraction, f"Processing {rel}")

                try:
                    result = future.result()
                except Exception as e:  # pylint: disable=broad-exception-caught
                    self.stats["other"].append(path)
                    self.logger.log(f"ERROR processing {path}: {e}")
                    continue

                # Handle result based on action
                action = result["action"]
                detail = result["detail"]

                if action == "skip":
                    self._handle_detection_failure(path, detail)
                elif action == "correct":
                    self.stats["correct_ext"].append(path)
                    self.logger.log(f"OK correct ext: {path}")
                elif action == "report":
                    src, dst, ext = detail
                    self.logger.log(f"REPORT: {src} -> {dst} (type: {ext})")
                elif action == "quarantine":
                    status, rename_detail = detail
                    if status == "ok":
                        self.logger.log(f"QUARANTINE: {path} -> {rename_detail}")
                    else:
                        self._handle_rename_failure(path, status, rename_detail)
                elif action == "dry_run":
                    src, dst, ext = detail
                    self.logger.log(f"DRY-RUN: {src} -> {dst} (type: {ext})")
                elif action == "rename":
                    status, rename_detail, ext = detail
                    if status == "ok":
                        self.logger.log(f"RENAME: {path} -> {rename_detail} (type: {ext})")
                    else:
                        self._handle_rename_failure(path, status, rename_detail)

        # ----------------------------------------------------
        # Done
        # ----------------------------------------------------
        self.emit("done", self.stats)

    # --------------------------------------------------------
    # Detection failure handler
    # --------------------------------------------------------
    def _handle_detection_failure(self, path, reason):
        stats = self.stats
        logger = self.logger

        if reason == "unreadable":
            stats["unreadable"].append(path)
            logger.log(f"SKIP unreadable: {path}")
        elif reason == "too_small":
            stats["too_small"].append(path)
            logger.log(f"SKIP too small: {path}")
        elif reason == "ambiguous_riff":
            stats["ambiguous_riff"].append(path)
            logger.log(f"SKIP ambiguous RIFF: {path}")
        elif reason == "ambiguous_iso":
            stats["ambiguous_iso"].append(path)
            logger.log(f"SKIP ambiguous ISO BMFF: {path}")
        elif is_zero_byte(path):
            stats["zero_byte"].append(path)
            logger.log(f"SKIP zero-byte: {path}")
        else:
            stats["unknown"].append(path)
            logger.log(f"SKIP unknown type: {path}")

    # --------------------------------------------------------
    # Rename failure handler
    # --------------------------------------------------------
    def _handle_rename_failure(self, path, status, detail):
        stats = self.stats
        logger = self.logger

        if status == "permission":
            stats["permission_denied"].append(path)
            logger.log(f"ERROR permission denied: {path}")
        elif status == "unicode":
            stats["unicode_issue"].append(path)
            logger.log(f"ERROR unicode issue: {path}")
        else:
            stats["other"].append(path)
            logger.log(f"ERROR renaming {path}: {detail}")