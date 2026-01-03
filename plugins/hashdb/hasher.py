"""
hasher.py
---------

Threaded hashing engine.

This module:
- Computes MD5 and/or SHA-256
- Uses ThreadPoolExecutor for concurrency
- Produces DB-ready record dicts
- Does NOT write to the database (db.py handles that)
"""

import hashlib
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List


def compute_hash(path: str, hash_type: str, chunk_size: int = 65536) -> str:
    """
    Compute MD5 or SHA-256 for a file.
    """
    if hash_type == "md5":
        h = hashlib.md5()
    else:
        h = hashlib.sha256()

    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)

    return h.hexdigest()


def hash_worker(meta: Dict[str, Any], hash_type: str) -> Dict[str, Any]:
    """
    Worker function for threaded hashing.
    Returns a DB-ready record dict.
    """
    filepath = meta["filepath"]

    try:
        hash_value = compute_hash(filepath, hash_type)
    except Exception:
        return None

    now = datetime.datetime.now().isoformat()

    record = {
        "filepath": filepath,
        "filename": meta["filename"],
        "size_bytes": meta["size_bytes"],
        "created_on": meta["created_on"],
        "modified_on": meta["modified_on"],
        "imported_on": now,
        "last_scanned_on": now,
        "hash_md5": hash_value if hash_type == "md5" else None,
        "hash_sha256": hash_value if hash_type == "sha256" else None,
        "flags": None,
    }

    return record


def run_hashing(
    work_list: List[Dict[str, Any]],
    hash_type: str,
    threads: int,
    progress_callback=None,
    batch_callback=None,
    batch_size: int = 50,
):
    """
    Threaded hashing over a list of metadata dicts.

    progress_callback(fraction, message) is optional.
    batch_callback(records_list) is optional and called every batch_size records.
    """
    results = []
    total = len(work_list)

    if total == 0:
        return results

    pending_batch = []

    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = {
            executor.submit(hash_worker, meta, hash_type): meta
            for meta in work_list
        }

        for i, future in enumerate(as_completed(futures)):
            meta = futures[future]
            rec = future.result()
            if rec:
                results.append(rec)
                pending_batch.append(rec)

                # Flush batch if size reached
                if batch_callback and len(pending_batch) >= batch_size:
                    batch_callback(pending_batch)
                    pending_batch = []

            if progress_callback:
                fraction = (i + 1) / total
                progress_callback(fraction, f"Hashed: {meta['filename']}")

    # Flush remaining records
    if batch_callback and pending_batch:
        batch_callback(pending_batch)

    return results