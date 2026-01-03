"""
md5_cache.py
------------

MD5 hashing + persistent cache + directory indexing.

This module provides:
- compute_md5(): chunked hashing
- load_cache() / save_cache(): persistent JSON cache
- index_temp_directory(): builds MD5 → file path index
- Multithreaded hashing for new/changed files
- Optional progress reporting via queue (for GUI)

This module is used by restorer.py and tool.py.
"""

import os
import json
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import shared scanner utilities
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared import collect_files_chunked, DEFAULT_CHUNK_SIZE


def compute_md5(path, chunk_size=65536):
    md5 = hashlib.md5()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(chunk_size), b""):
                md5.update(chunk)
        return md5.hexdigest()
    except Exception:
        return None


def compute_sha256(path, chunk_size=65536):
    sha = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(chunk_size), b""):
                sha.update(chunk)
        return sha.hexdigest()
    except Exception:
        return None


def compute_hash(path, hash_type="md5", chunk_size=65536):
    if hash_type == "sha256":
        return compute_sha256(path, chunk_size=chunk_size)
    return compute_md5(path, chunk_size=chunk_size)


def load_cache(cache_path):
    if not os.path.isfile(cache_path):
        return {}
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_cache(cache_path, cache_data):
    cache_dir = os.path.dirname(cache_path)
    if cache_dir and not os.path.exists(cache_dir):
        os.makedirs(cache_dir, exist_ok=True)

    tmp_path = cache_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, indent=2)

    os.replace(tmp_path, cache_path)


def index_temp_directory_with_cache(temp_dir, cache_path, thread_count, progress_queue=None, hash_type="md5"):
    """
    Hash indexer with progress bar support.
    Uses chunked scanning for memory efficiency.
    
    Args:
        hash_type: "md5" or "sha256"

    Returns:
        hash_index: dict mapping hash -> [list of paths] to handle duplicates
        cache: the updated cache dict
    """

    cache = load_cache(cache_path)
    hash_index = {}  # hash -> [paths] to handle duplicates/collisions

    # Collect files with chunked scanning + progress
    def on_scan_chunk(chunk, total_so_far):
        if progress_queue:
            progress_queue.put((
                "index_progress",
                (0.0, f"Scanning... found {total_so_far} files")
            ))

    file_list = collect_files_chunked(
        temp_dir,
        chunk_size=DEFAULT_CHUNK_SIZE,
        callback=on_scan_chunk,
        as_path=False,
    )

    total_files = len(file_list)
    cached_hits = 0
    to_hash = []

    def add_to_index(hash_value, path):
        """Add path to the index, handling duplicates."""
        if hash_value not in hash_index:
            hash_index[hash_value] = []
        if path not in hash_index[hash_value]:
            hash_index[hash_value].append(path)

    # Determine which files need hashing
    for path in file_list:
        try:
            stat = os.stat(path)
        except FileNotFoundError:
            continue

        size = stat.st_size
        mtime = stat.st_mtime

        entry = cache.get(path)
        cached_hash = None
        if entry and entry.get("size") == size and entry.get("mtime") == mtime:
            cached_hash = entry.get(hash_type)

        if cached_hash:
            add_to_index(cached_hash, path)
            cached_hits += 1
        else:
            to_hash.append((path, size, mtime))

    total_to_hash = len(to_hash)
    hashed_count = 0
    processed_overall = 0

    # Initial progress update
    if progress_queue:
        progress_queue.put((
            "index_progress",
            (0.0, f"Indexing: cached {cached_hits} / {total_files}, hashing {total_to_hash}...")
        ))

    # Hash missing files
    def hash_worker(item):
        path, size, mtime = item
        hv = compute_hash(path, hash_type=hash_type)
        return path, size, mtime, hv

    if total_to_hash > 0:
        with ThreadPoolExecutor(max_workers=thread_count) as executor:
            futures = {executor.submit(hash_worker, item): item for item in to_hash}
            for future in as_completed(futures):
                path, size, mtime, hv = future.result()
                if hv:
                    add_to_index(hv, path)
                    cache[path] = {
                        # Keep both hash types if present; update the one we computed.
                        "md5": cache.get(path, {}).get("md5"),
                        "sha256": cache.get(path, {}).get("sha256"),
                        "size": size,
                        "mtime": mtime
                    }
                    cache[path][hash_type] = hv

                hashed_count += 1
                processed_overall = cached_hits + hashed_count

                if progress_queue:
                    fraction = processed_overall / total_files if total_files else 0.0
                    progress_queue.put((
                        "index_progress",
                        (fraction, f"Indexing {processed_overall} / {total_files} (cached: {cached_hits}, hashed: {hashed_count})")
                    ))
    else:
        if progress_queue:
            progress_queue.put((
                "index_progress",
                (1.0, f"Indexing complete (cached: {cached_hits}, hashed: 0)")
            ))

    save_cache(cache_path, cache)
    return hash_index, cache