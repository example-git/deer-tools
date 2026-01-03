"""
exporter.py
-----------

Hash export utilities for the HashDB system.

This module:
- Exports MD5 or SHA-256 hashes
- Supports chunked export (Hydrus-style)
- Can export duplicates only
- Can export full file records
- Provides progress callbacks for GUI integration

It does NOT:
- Compute hashes
- Modify the database
- Perform deduplication
"""

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional


# ------------------------------------------------------------
# Core DB queries
# ------------------------------------------------------------
def fetch_hashes(conn, table_name: str, hash_type: str) -> List[str]:
    """
    Fetch all MD5 or SHA-256 hashes from the DB.
    """
    col = "hash_md5" if hash_type == "md5" else "hash_sha256"
    cur = conn.cursor()
    cur.execute(f"SELECT {col} FROM {table_name} WHERE {col} IS NOT NULL")
    return [row[0] for row in cur.fetchall()]


def fetch_duplicate_hashes(conn, table_name: str, hash_type: str) -> Dict[str, List[str]]:
    """
    Return a dict: hash_value -> list of filepaths (duplicates only).
    """
    col = "hash_md5" if hash_type == "md5" else "hash_sha256"
    cur = conn.cursor()
    cur.execute(f"""
        SELECT {col}, filepath
        FROM {table_name}
        WHERE {col} IS NOT NULL
    """)

    groups = {}
    for h, fp in cur.fetchall():
        if h not in groups:
            groups[h] = []
        groups[h].append(fp)

    return {h: fps for h, fps in groups.items() if len(fps) > 1}


# ------------------------------------------------------------
# Export helpers
# ------------------------------------------------------------
def write_lines(path: str, lines: List[str]):
    """
    Write a list of lines to a file.
    """
    with open(path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")


def chunk_list(items: List[str], chunk_size: int) -> List[List[str]]:
    """
    Split a list into chunks of size chunk_size.
    """
    return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]


# ------------------------------------------------------------
# High-level export functions
# ------------------------------------------------------------
def export_hashes(
    conn,
    table_name: str,
    hash_type: str,
    output_path: str,
    progress_callback=None,
):
    """
    Export all MD5 or SHA-256 hashes into a single file.
    """
    hashes = fetch_hashes(conn, table_name, hash_type)
    write_lines(output_path, hashes)

    if progress_callback:
        progress_callback(1.0, f"Exported {len(hashes)} hashes")


def export_hashes_chunked(
    conn,
    table_name: str,
    hash_type: str,
    output_dir: str,
    chunk_size: int = 100_000,
    threads: int = 8,
    progress_callback=None,
):
    """
    Export hashes into multiple chunked files (Hydrus-style).
    """
    os.makedirs(output_dir, exist_ok=True)

    hashes = fetch_hashes(conn, table_name, hash_type)
    chunks = chunk_list(hashes, chunk_size)

    total = len(chunks)
    if total == 0:
        if progress_callback:
            progress_callback(1.0, "No hashes to export")
        return

    t = max(1, int(threads or 1))
    if t <= 1:
        for i, chunk in enumerate(chunks):
            filename = os.path.join(output_dir, f"{hash_type}_chunk_{i+1}.txt")
            write_lines(filename, chunk)
            if progress_callback:
                progress_callback((i + 1) / total, f"Wrote {filename}")
        return

    def _write_one(i_and_chunk):
        i, chunk = i_and_chunk
        filename = os.path.join(output_dir, f"{hash_type}_chunk_{i+1}.txt")
        write_lines(filename, chunk)
        return filename

    written = 0
    with ThreadPoolExecutor(max_workers=min(t, total)) as ex:
        futures = {ex.submit(_write_one, pair): pair[0] for pair in enumerate(chunks)}
        for fut in as_completed(futures):
            filename = fut.result()
            written += 1
            if progress_callback:
                progress_callback(written / total, f"Wrote {filename}")


def export_duplicates(
    conn,
    table_name: str,
    hash_type: str,
    output_path: str,
    progress_callback=None,
):
    """
    Export duplicate sets in the format:

        <hash>
        path1
        path2
        ...

    """
    dupes = fetch_duplicate_hashes(conn, table_name, hash_type)

    lines = []
    for h, paths in dupes.items():
        lines.append(h)
        lines.extend(paths)
        lines.append("")  # blank line between groups

    write_lines(output_path, lines)

    if progress_callback:
        progress_callback(1.0, f"Exported {len(dupes)} duplicate sets")


def export_full_records(
    conn,
    table_name: str,
    output_path: str,
    progress_callback=None,
):
    """
    Export full DB rows as a TSV file.
    Useful for debugging or external tools.
    """
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {table_name}")
    rows = cur.fetchall()

    if not rows:
        write_lines(output_path, [])
        return

    # Header
    header = rows[0].keys()
    lines = ["\t".join(header)]

    # Rows
    for row in rows:
        lines.append("\t".join(str(row[h]) if row[h] is not None else "" for h in header))

    write_lines(output_path, lines)

    if progress_callback:
        progress_callback(1.0, f"Exported {len(rows)} records")