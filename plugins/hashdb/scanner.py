"""
scanner.py
----------

Directory traversal + rescan decision logic.

This module:
- Uses shared scanner utilities for chunked scanning
- Collects file metadata (size, timestamps)
- Compares against DB records to decide if hashing is needed
- Produces a list of "work items" for the hasher (or yields chunks)

It does NOT compute hashes.
"""

import os
import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional, Iterator, Callable

# Import shared scanner utilities
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared import (
    iter_files,
    iter_files_chunked,
    collect_files,
    collect_files_chunked,
    DEFAULT_CHUNK_SIZE,
)


def get_file_metadata(path: Path) -> Dict[str, Any]:
    """
    Extract filesystem metadata for a file.
    
    Note: On macOS, st_birthtime gives true creation time.
          On Linux, st_ctime is inode change time (not creation).
          We use st_birthtime when available, else None for created_on.
    """
    stat = path.stat()
    
    # Try to get true creation time (macOS has st_birthtime)
    created_on = None
    if hasattr(stat, 'st_birthtime'):
        created_on = datetime.datetime.fromtimestamp(stat.st_birthtime).isoformat()
    # On Windows, st_ctime is creation time
    elif os.name == 'nt':
        created_on = datetime.datetime.fromtimestamp(stat.st_ctime).isoformat()
    # On Linux, st_ctime is metadata change time, not creation - leave as None
    
    return {
        "filepath": str(path),
        "filename": path.name,
        "size_bytes": stat.st_size,
        "created_on": created_on,
        "modified_on": datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(),
    }


def needs_rescan(db_record: Dict[str, Any], meta: Dict[str, Any], rescan_mode: bool) -> bool:
    """
    Decide whether a file needs to be rehashed.

    Rules:
    - If no DB record exists → hash it
    - If rescan_mode=False → always hash (full scan)
    - If rescan_mode=True → hash only if modified timestamp changed
    """
    if db_record is None:
        return True

    if not rescan_mode:
        return True

    return db_record["modified_on"] != meta["modified_on"]


def build_work_list(
    conn,
    table_name: str,
    root: str,
    rescan_mode: bool,
    db_get_record,
    threads: int = 8,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> List[Dict[str, Any]]:
    """
    Build a list of files that need hashing.

    Returns a list of metadata dicts.
    """
    # Bulk-load DB state once to avoid per-file DB queries (SQLite is single-writer
    # and per-file SELECTs become a huge bottleneck).
    modified_index: Dict[str, Any] = {}
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT filepath, modified_on FROM {table_name}")
        for fp, modified_on in cur.fetchall():
            modified_index[str(fp)] = modified_on
    except Exception:
        modified_index = {}

    def _get_db_record(filepath: str) -> Optional[Dict[str, Any]]:
        mo = modified_index.get(filepath)
        if mo is None:
            return None
        return {"modified_on": mo}

    work: List[Dict[str, Any]] = []
    t = max(1, int(threads or 1))

    def _meta_safe(p: Path) -> Optional[Dict[str, Any]]:
        try:
            return get_file_metadata(p)
        except Exception:
            return None

    for file_chunk in iter_files_chunked(root, chunk_size):
        metas: List[Optional[Dict[str, Any]]]
        if t <= 1 or len(file_chunk) <= 1:
            metas = [_meta_safe(p) for p in file_chunk]
        else:
            with ThreadPoolExecutor(max_workers=min(t, len(file_chunk))) as ex:
                metas = list(ex.map(_meta_safe, file_chunk))

        for meta in metas:
            if not meta:
                continue
            db_record = _get_db_record(meta["filepath"])
            if needs_rescan(db_record, meta, rescan_mode):
                work.append(meta)

    return work


def build_work_list_chunked(
    conn,
    table_name: str,
    root: str,
    rescan_mode: bool,
    db_get_record,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    threads: int = 8,
    chunk_callback: Optional[Callable[[List[Dict[str, Any]], int, int], None]] = None,
) -> List[Dict[str, Any]]:
    """
    Build a list of files that need hashing, processing in chunks.
    
    Args:
        conn: Database connection
        table_name: Name of the table
        root: Root directory to scan
        rescan_mode: If True, only rescan files with changed modified_on
        db_get_record: Function to get existing DB record
        chunk_size: Files per chunk
        chunk_callback: Optional function(work_chunk, files_scanned, work_total)
                       called after processing each chunk
        
    Returns:
        Complete list of work items (built incrementally)
    """
    # Bulk-load DB state once (same rationale as build_work_list).
    modified_index: Dict[str, Any] = {}
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT filepath, modified_on FROM {table_name}")
        for fp, modified_on in cur.fetchall():
            modified_index[str(fp)] = modified_on
    except Exception:
        modified_index = {}

    def _get_db_record(filepath: str) -> Optional[Dict[str, Any]]:
        mo = modified_index.get(filepath)
        if mo is None:
            return None
        return {"modified_on": mo}

    work: List[Dict[str, Any]] = []
    files_scanned = 0
    t = max(1, int(threads or 1))

    def _meta_safe(p: Path) -> Optional[Dict[str, Any]]:
        try:
            return get_file_metadata(p)
        except Exception:
            return None

    for file_chunk in iter_files_chunked(root, chunk_size):
        if t <= 1 or len(file_chunk) <= 1:
            metas = [_meta_safe(p) for p in file_chunk]
        else:
            with ThreadPoolExecutor(max_workers=min(t, len(file_chunk))) as ex:
                metas = list(ex.map(_meta_safe, file_chunk))

        work_chunk: List[Dict[str, Any]] = []
        for meta in metas:
            if not meta:
                continue
            db_record = _get_db_record(meta["filepath"])
            if needs_rescan(db_record, meta, rescan_mode):
                work_chunk.append(meta)

        work.extend(work_chunk)
        files_scanned += len(file_chunk)

        if chunk_callback:
            chunk_callback(work_chunk, files_scanned, len(work))

    return work


def iter_work_list_chunked(
    conn,
    table_name: str,
    root: str,
    rescan_mode: bool,
    db_get_record,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    threads: int = 8,
) -> Iterator[List[Dict[str, Any]]]:
    """
    Generator that yields work list chunks.
    
    Use this for streaming/pipeline processing where you don't need
    the complete list in memory.
    
    Yields:
        Lists of work item dicts, each up to chunk_size items
    """
    modified_index: Dict[str, Any] = {}
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT filepath, modified_on FROM {table_name}")
        for fp, modified_on in cur.fetchall():
            modified_index[str(fp)] = modified_on
    except Exception:
        modified_index = {}

    def _get_db_record(filepath: str) -> Optional[Dict[str, Any]]:
        mo = modified_index.get(filepath)
        if mo is None:
            return None
        return {"modified_on": mo}

    t = max(1, int(threads or 1))

    def _meta_safe(p: Path) -> Optional[Dict[str, Any]]:
        try:
            return get_file_metadata(p)
        except Exception:
            return None

    for file_chunk in iter_files_chunked(root, chunk_size):
        if t <= 1 or len(file_chunk) <= 1:
            metas = [_meta_safe(p) for p in file_chunk]
        else:
            with ThreadPoolExecutor(max_workers=min(t, len(file_chunk))) as ex:
                metas = list(ex.map(_meta_safe, file_chunk))

        work_chunk: List[Dict[str, Any]] = []
        for meta in metas:
            if not meta:
                continue
            db_record = _get_db_record(meta["filepath"])
            if needs_rescan(db_record, meta, rescan_mode):
                work_chunk.append(meta)

        if work_chunk:
            yield work_chunk