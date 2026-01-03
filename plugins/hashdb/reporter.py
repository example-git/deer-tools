"""
reporter.py
-----------

Reporting utilities for the HashDB system.

This module:
- Generates duplicate hash reports
- Produces summary statistics
- Creates DB health reports
- Writes text-based reports to disk
- Supports GUI progress callbacks

It does NOT:
- Compute hashes
- Modify the database
- Perform cleanup or dedupe
"""

import os
import datetime
from typing import Dict, List, Optional


# ------------------------------------------------------------
# Core DB queries
# ------------------------------------------------------------
def count_rows(conn, table_name: str) -> int:
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM {table_name}")
    return cur.fetchone()[0]


def count_unique_hashes(conn, table_name: str, hash_type: str) -> int:
    col = "hash_md5" if hash_type == "md5" else "hash_sha256"
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(DISTINCT {col}) FROM {table_name} WHERE {col} IS NOT NULL")
    return cur.fetchone()[0]


def count_duplicates(conn, table_name: str, hash_type: str) -> int:
    col = "hash_md5" if hash_type == "md5" else "hash_sha256"
    cur = conn.cursor()
    cur.execute(f"""
        SELECT {col}, COUNT(*)
        FROM {table_name}
        WHERE {col} IS NOT NULL
        GROUP BY {col}
        HAVING COUNT(*) > 1
    """)
    return len(cur.fetchall())


def fetch_duplicate_groups(conn, table_name: str, hash_type: str) -> Dict[str, List[str]]:
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
# Summary report
# ------------------------------------------------------------
def generate_summary(
    conn,
    table_name: str,
    hash_type: str,
) -> Dict[str, int]:
    """
    Return a summary dict with:
        - total_rows
        - unique_hashes
        - duplicate_hashes
    """
    return {
        "total_rows": count_rows(conn, table_name),
        "unique_hashes": count_unique_hashes(conn, table_name, hash_type),
        "duplicate_hashes": count_duplicates(conn, table_name, hash_type),
    }


# ------------------------------------------------------------
# Duplicate report writer
# ------------------------------------------------------------
def write_duplicate_report(
    conn,
    table_name: str,
    hash_type: str,
    output_path: str,
    max_samples: int = 99,
    progress_callback=None,
):
    """
    Write a detailed duplicate report:

        Hash: <hash>
        File Count: N
          path1
          path2
          ...

    """
    groups = fetch_duplicate_groups(conn, table_name, hash_type)
    total = len(groups)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("Duplicate Hash Report\n")
        f.write(f"Generated: {datetime.datetime.now().isoformat()}\n")
        f.write(f"Hash Type: {hash_type.upper()}\n\n")

        for i, (h, paths) in enumerate(sorted(groups.items(), key=lambda x: len(x[1]), reverse=True)):
            f.write(f"Hash: {h}\n")
            f.write(f"File Count: {len(paths)}\n")

            for p in paths[:max_samples]:
                f.write(f"  {p}\n")

            if len(paths) > max_samples:
                f.write(f"  ... ({len(paths) - max_samples} more files)\n")

            f.write("\n")

            if progress_callback:
                progress_callback((i + 1) / total, f"Processed hash {h}")

    return total


# ------------------------------------------------------------
# Health report
# ------------------------------------------------------------
def generate_health_report(
    conn,
    table_name: str,
    db_path: str,
    output_path: str,
):
    """
    Write a DB health report including:
    - DB size
    - Row count
    - Missing file count
    - Zero-byte file count
    """
    size_mb = os.path.getsize(db_path) / (1024 * 1024)

    cur = conn.cursor()
    cur.execute(f"SELECT filepath FROM {table_name}")
    filepaths = [row[0] for row in cur.fetchall()]

    missing = [fp for fp in filepaths if not os.path.exists(fp)]
    zero_bytes = [fp for fp in filepaths if os.path.exists(fp) and os.path.getsize(fp) == 0]

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("HashDB Health Report\n")
        f.write(f"Generated: {datetime.datetime.now().isoformat()}\n\n")

        f.write(f"Database Size: {size_mb:.2f} MB\n")
        f.write(f"Total Rows: {len(filepaths)}\n")
        f.write(f"Missing Files: {len(missing)}\n")
        f.write(f"Zero-Byte Files: {len(zero_bytes)}\n")

    return {
        "db_size_mb": size_mb,
        "total_rows": len(filepaths),
        "missing": len(missing),
        "zero_bytes": len(zero_bytes),
    }