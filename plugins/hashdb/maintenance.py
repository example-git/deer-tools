"""
maintenance.py
--------------

Database cleanup utilities for the HashDB system.

This module:
- Removes DB entries for files that no longer exist
- Detects and optionally deletes zero-byte files
- Writes cleanup logs
- Runs VACUUM to compact the database
- Provides progress callbacks for GUI integration

It does NOT:
- Compute hashes
- Perform deduplication
- Modify schema
"""

import os
import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import List, Tuple, Optional


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def db_size_mb(path: str) -> float:
    return os.path.getsize(path) / (1024 * 1024)


def list_all_filepaths(conn, table_name: str) -> List[str]:
    cur = conn.cursor()
    cur.execute(f"SELECT filepath FROM {table_name}")
    return [row[0] for row in cur.fetchall()]


# ------------------------------------------------------------
# Missing file cleanup
# ------------------------------------------------------------
def find_missing_files(filepaths: List[str]) -> List[str]:
    missing = []
    for fp in filepaths:
        if not os.path.exists(fp):
            missing.append(fp)
    return missing


def find_missing_files_parallel(filepaths: List[str], threads: int) -> List[str]:
    """Find missing files using a thread pool (IO-bound)."""
    if not filepaths:
        return []
    t = max(1, int(threads or 1))
    if t <= 1:
        return find_missing_files(filepaths)

    def _check(fp: str) -> Optional[str]:
        return fp if not os.path.exists(fp) else None

    with ThreadPoolExecutor(max_workers=t) as ex:
        return [fp for fp in ex.map(_check, filepaths) if fp]


def remove_missing_from_db(conn, table_name: str, missing: List[str]):
    cur = conn.cursor()
    cur.executemany(
        f"DELETE FROM {table_name} WHERE filepath = ?",
        [(fp,) for fp in missing]
    )
    conn.commit()


# ------------------------------------------------------------
# Zero-byte cleanup
# ------------------------------------------------------------
def find_zero_byte_files(filepaths: List[str]) -> List[str]:
    zeros = []
    for fp in filepaths:
        try:
            if os.path.exists(fp) and os.path.getsize(fp) == 0:
                zeros.append(fp)
        except Exception:
            continue
    return zeros


def find_zero_byte_files_parallel(filepaths: List[str], threads: int) -> List[str]:
    """Find zero-byte files using a thread pool (IO-bound)."""
    if not filepaths:
        return []
    t = max(1, int(threads or 1))
    if t <= 1:
        return find_zero_byte_files(filepaths)

    def _check(fp: str) -> Optional[str]:
        try:
            if os.path.exists(fp) and os.path.getsize(fp) == 0:
                return fp
        except Exception:
            return None
        return None

    with ThreadPoolExecutor(max_workers=t) as ex:
        return [fp for fp in ex.map(_check, filepaths) if fp]


def delete_zero_byte_files(paths: List[str]) -> int:
    deleted = 0
    for fp in paths:
        try:
            os.remove(fp)
            deleted += 1
        except Exception:
            pass
    return deleted


def delete_zero_byte_files_parallel(paths: List[str], threads: int) -> int:
    """Delete files concurrently (IO-bound)."""
    if not paths:
        return 0
    t = max(1, int(threads or 1))
    if t <= 1:
        return delete_zero_byte_files(paths)

    def _delete(fp: str) -> int:
        try:
            os.remove(fp)
            return 1
        except Exception:
            return 0

    with ThreadPoolExecutor(max_workers=t) as ex:
        return sum(ex.map(_delete, paths))


# ------------------------------------------------------------
# Logging
# ------------------------------------------------------------
def write_cleanup_log(
    log_path: str,
    missing: List[str],
    zero_bytes: List[str],
    zero_deleted: int,
    db_before: float,
    db_after: float,
):
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("HashDB Cleanup Log\n")
        f.write(f"Generated: {datetime.datetime.now().isoformat()}\n\n")

        f.write(f"Database size before cleanup: {db_before:.2f} MB\n")
        f.write(f"Database size after cleanup:  {db_after:.2f} MB\n\n")

        f.write("Missing Files Removed from DB:\n")
        for fp in missing:
            f.write(f"  {fp}\n")

        f.write("\nZero-Byte Files:\n")
        for fp in zero_bytes:
            status = "DELETED" if fp in zero_bytes[:zero_deleted] else "FLAGGED"
            f.write(f"  {fp} [{status}]\n")


# ------------------------------------------------------------
# High-level cleanup workflow
# ------------------------------------------------------------
def run_cleanup(
    conn,
    db_path: str,
    table_name: str,
    delete_zero_bytes: bool = False,
    threads: int = 8,
    progress_callback=None,
) -> Tuple[int, int, int, str]:
    """
    Perform full cleanup:
    - Remove missing files from DB
    - Detect zero-byte files
    - Optionally delete zero-byte files
    - VACUUM database
    - Write log file

    Returns:
        (missing_count, zero_count, zero_deleted, log_path)
    """
    db_before = db_size_mb(db_path)

    # Step 1: Load all filepaths
    filepaths = list_all_filepaths(conn, table_name)

    # Step 2: Missing files
    missing = find_missing_files_parallel(filepaths, threads)
    remove_missing_from_db(conn, table_name, missing)

    if progress_callback:
        progress_callback(0.33, f"Removed {len(missing)} missing files")

    # Step 3: Zero-byte files
    zero_bytes = find_zero_byte_files_parallel(filepaths, threads)

    zero_deleted = 0
    if delete_zero_bytes:
        zero_deleted = delete_zero_byte_files_parallel(zero_bytes, threads)

    if progress_callback:
        progress_callback(0.66, f"Processed {len(zero_bytes)} zero-byte files")

    # Step 4: VACUUM
    conn.execute("VACUUM")
    conn.commit()

    db_after = db_size_mb(db_path)

    # Step 5: Log
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = f"cleanup_log_{timestamp}.txt"

    write_cleanup_log(
        log_path,
        missing,
        zero_bytes,
        zero_deleted,
        db_before,
        db_after,
    )

    if progress_callback:
        progress_callback(1.0, "Cleanup complete")

    return len(missing), len(zero_bytes), zero_deleted, log_path