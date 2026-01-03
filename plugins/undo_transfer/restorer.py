"""
restorer.py
-----------

Threaded restoration engine for the Undo Transfer Tool.

Responsibilities:
- Iterate through parsed log entries
- Match MD5 hashes to files in the temp directory
- Reconstruct original folder structure under RESTORE_ROOT
- Move files (or dry-run)
- Update MD5 cache
- Report progress via queue (for GUI)
- Write detailed undo log entries

This module is GUI-agnostic and can be used in CLI or GUI mode.
"""

import os
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from pathlib import Path
from .md5_cache import index_temp_directory_with_cache
from shared.path_utils import ensure_directory
from .utils import load_log_entries


class UndoWorker(threading.Thread):
    """
    Worker thread that performs the undo operation and sends progress updates
    to the GUI or CLI via a queue.
    """

    def __init__(self, settings, progress_queue=None):
        super().__init__()
        self.settings = settings
        self.progress_queue = progress_queue

        self.total_entries = 0
        self.processed_entries = 0

    def _emit(self, msg_type, payload):
        if self.progress_queue:
            self.progress_queue.put((msg_type, payload))

    def _update_restore_progress(self):
        if self.total_entries == 0:
            fraction = 0.0
        else:
            fraction = self.processed_entries / self.total_entries

        status = f"Restoring {self.processed_entries} / {self.total_entries}"
        self._emit("restore_progress", (fraction, status))

    def run(self):
        s = self.settings

        log_file = s["LOG_FILE"]
        temp_dir = s["TEMP_DIRECTORY"]
        targets = s["TARGET_SUBFOLDERS"]
        undo_log = s["UNDO_LOG"]
        original_root = s["ORIGINAL_ROOT"]
        restore_root = s["RESTORE_ROOT"]
        cache_file = s["CACHE_FILE"]
        thread_count = s["THREAD_COUNT"]
        hash_type_setting = s.get("HASH_TYPE", "md5")
        dry_run = s["DRY_RUN"]

        # Ensure undo log exists
        undo_dir = os.path.dirname(undo_log)
        if undo_dir and not os.path.exists(undo_dir):
            os.makedirs(undo_dir, exist_ok=True)
        if not os.path.exists(undo_log):
            open(undo_log, "w", encoding="utf-8").close()

        with open(undo_log, "a", encoding="utf-8") as log:

            log_lock = threading.Lock()
            pick_lock = threading.Lock()
            cache_lock = threading.Lock()

            def write(msg):
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                line = f"[{timestamp}] {msg}"
                with log_lock:
                    print(line, flush=True)
                    log.write(line + "\n")
                    log.flush()

            write("=" * 80)
            write("UNDO TRANSFER STARTED")
            write(f"Target subfolders: {targets}")
            write(f"Temp directory: {temp_dir}")
            write(f"Original root: {original_root}")
            write(f"Restore root: {restore_root}")
            write(f"Dry run: {dry_run}")
            write(f"Cache file: {cache_file}")
            write(f"Thread count: {thread_count}")

            # Load log entries (returns tuples with relative path and hash algorithm)
            entries = load_log_entries(log_file, targets, original_root)
            self.total_entries = len(entries)
            write(f"Loaded {self.total_entries} matching log entries")

            # Index temp directory by hash
            # If logs contain mixed hash types, build both indexes (cache will be reused).
            hash_types_in_log = set(e[3] for e in entries) if entries else {hash_type_setting}
            indexes = {}
            cache = None

            for algo in sorted(hash_types_in_log):
                write(f"Indexing temp directory by {algo.upper()} (cache + hashing)...")
                idx, cache = index_temp_directory_with_cache(
                    temp_dir,
                    cache_file,
                    thread_count,
                    self.progress_queue,
                    hash_type=algo,
                )
                indexes[algo] = idx
                write(
                    f"Indexing complete. Indexed {len(idx)} {algo.upper()} entries. "
                    f"Cache size: {len(cache)}"
                )

            restored = 0
            missing = 0
            removed_from_cache = 0
            ambiguous = 0

            restore_root_path = Path(restore_root)

            def _pick_candidate(idx_map, hv: str, rel) -> (str, int):
                """Pick and REMOVE a candidate path for this hash, returns (path, ambiguous_count)."""
                candidates = idx_map.get(hv)
                if not candidates:
                    return "", 0

                if len(candidates) == 1:
                    chosen = candidates.pop(0)
                    if not idx_map.get(hv):
                        idx_map.pop(hv, None)
                    return chosen, 0

                # Prefer matching basename, else newest mtime.
                target_basename = rel.name if rel else None
                chosen = None
                if target_basename:
                    for i, c in enumerate(candidates):
                        if Path(c).name == target_basename:
                            chosen = candidates.pop(i)
                            break
                if chosen is None:
                    best_i = 0
                    best_m = -1
                    for i, c in enumerate(candidates):
                        try:
                            m = os.path.getmtime(c) if os.path.exists(c) else -1
                        except Exception:
                            m = -1
                        if m > best_m:
                            best_m = m
                            best_i = i
                    chosen = candidates.pop(best_i)

                if not candidates:
                    idx_map.pop(hv, None)
                return chosen, len(candidates) + 1

            def _restore_one(entry):
                original_path_str, hash_value, rel_path, algo = entry
                idx = indexes.get(algo)
                if idx is None:
                    write(f"ERROR: No index available for hash type {algo} (entry {original_path_str})")
                    return {"status": "missing"}

                with pick_lock:
                    current_path, candidate_count = _pick_candidate(idx, hash_value, rel_path)

                if not current_path:
                    write(f"Missing: No file with {algo.upper()} {hash_value} found for {original_path_str}")
                    return {"status": "missing"}

                if candidate_count > 1:
                    write(
                        f"Ambiguous: {candidate_count} files share {algo.upper()} {hash_value}, picked {current_path}"
                    )
                    amb = 1
                else:
                    amb = 0

                # Compute restore path using cross-platform Path
                if rel_path:
                    target_path = str(restore_root_path / Path(*rel_path.parts))
                else:
                    target_path = original_path_str  # fallback

                write(f"Restoring: {current_path} -> {target_path}")

                if dry_run:
                    return {"status": "restored", "ambiguous": amb, "cache_removed": 0}

                try:
                    ensure_directory(target_path)
                    shutil.move(current_path, target_path)
                except Exception as e:
                    write(f"ERROR moving file: {e}")
                    return {"status": "error", "ambiguous": amb, "cache_removed": 0}

                cache_removed = 0
                with cache_lock:
                    if cache is not None and current_path in cache:
                        del cache[current_path]
                        cache_removed = 1
                if cache_removed:
                    write(f"Cache: removed entry for {current_path}")

                return {"status": "restored", "ambiguous": amb, "cache_removed": cache_removed}

            # Restore loop (concurrent)
            if not entries:
                write("No matching log entries to restore.")
            elif int(thread_count or 1) <= 1:
                for entry in entries:
                    res = _restore_one(entry)
                    self.processed_entries += 1
                    if res.get("status") == "restored":
                        restored += 1
                    elif res.get("status") == "missing":
                        missing += 1
                    else:
                        missing += 1
                    ambiguous += int(res.get("ambiguous") or 0)
                    removed_from_cache += int(res.get("cache_removed") or 0)
                    self._update_restore_progress()
            else:
                with ThreadPoolExecutor(max_workers=max(1, int(thread_count))) as ex:
                    futures = [ex.submit(_restore_one, e) for e in entries]
                    for fut in as_completed(futures):
                        res = fut.result()
                        self.processed_entries += 1

                        if res.get("status") == "restored":
                            restored += 1
                        elif res.get("status") == "missing":
                            missing += 1
                        else:
                            missing += 1

                        ambiguous += int(res.get("ambiguous") or 0)
                        removed_from_cache += int(res.get("cache_removed") or 0)
                        self._update_restore_progress()

            # Save updated cache
            from .md5_cache import save_cache
            save_cache(cache_file, cache)

            write(f"Cache updated. Entries removed: {removed_from_cache}")
            write(f"Final cache size: {len(cache)}")
            write(f"Restored files: {restored}")
            write(f"Missing files: {missing}")
            write("UNDO TRANSFER COMPLETED")
            write("=" * 80)

            self._emit("done", None)