"""
deduper.py
----------

Duplicate detection + safe deletion logic for the HashDB system.

This module:
- Finds duplicate files using the database (MD5 or SHA-256)
- Groups duplicates into sets
- Scores files to choose the "best" one to keep
- Supports safe delete (quarantine) or hard delete
- Generates logs for all actions
- Integrates cleanly with GUI or CLI frontends

It does NOT:
- Compute hashes
- Walk directories
- Modify the database schema
"""

import os
import shutil
import datetime
from typing import List, Dict, Tuple, Optional
from pathlib import Path


# ------------------------------------------------------------
# Duplicate detection
# ------------------------------------------------------------
def find_duplicates(conn, table_name: str, hash_type: str = "md5") -> Dict[str, List[Dict]]:
    """
    Return a dict: hash_value -> list of DB rows (duplicates).
    hash_type: "md5" or "sha256"
    """
    cur = conn.cursor()

    col = "hash_md5" if hash_type == "md5" else "hash_sha256"

    cur.execute(f"""
        SELECT * FROM {table_name}
        WHERE {col} IS NOT NULL
    """)

    groups = {}
    for row in cur.fetchall():
        h = row[col]
        if h not in groups:
            groups[h] = []
        groups[h].append(dict(row))

    # Keep only groups with more than one file
    return {h: rows for h, rows in groups.items() if len(rows) > 1}


# ------------------------------------------------------------
# Scoring logic (choose best file to keep)
# ------------------------------------------------------------
def score_file(path: str) -> float:
    """
    Heuristic scoring to choose the best file to keep.
    Lower score = better file.
    """
    name = os.path.basename(path).lower()
    score = 0

    # Penalize common duplicate indicators
    if any(suffix in name for suffix in ["_1", "(1)", "-copy", "-edited", " - "]):
        score += 10

    # Penalize deeper paths
    score += path.count(os.sep)

    # Penalize long names
    score += len(name) / 10

    # Prefer older files (lower ctime)
    try:
        score -= os.path.getctime(path) / 1e6
    except Exception:
        pass

    return score


def choose_best_file(rows: List[Dict]) -> Dict:
    """
    Given a list of DB rows for duplicate files, return the best one to keep.
    """
    return min(rows, key=lambda r: score_file(r["filepath"]))


# ------------------------------------------------------------
# Deletion / quarantine
# ------------------------------------------------------------
def safe_move(src: str, quarantine_dir: str) -> str:
    """
    Move a file to the quarantine directory with collision-safe renaming.
    Returns the final destination path.
    """
    os.makedirs(quarantine_dir, exist_ok=True)

    base = os.path.basename(src)
    dest = os.path.join(quarantine_dir, base)

    counter = 1
    while os.path.exists(dest):
        name, ext = os.path.splitext(base)
        dest = os.path.join(quarantine_dir, f"{name}_{counter}{ext}")
        counter += 1

    shutil.move(src, dest)
    return dest


def delete_or_quarantine(
    rows: List[Dict],
    keep: Dict,
    safe_delete: bool,
    quarantine_dir: Optional[str] = None,
) -> List[Tuple[str, str]]:
    """
    Delete or quarantine all files except the one to keep.
    Returns a list of (filepath, action) tuples.
    """
    actions = []

    for row in rows:
        path = row["filepath"]
        if path == keep["filepath"]:
            continue

        try:
            if safe_delete:
                dest = safe_move(path, quarantine_dir)
                actions.append((path, f"moved to {dest}"))
            else:
                os.remove(path)
                actions.append((path, "deleted"))
        except Exception as e:
            actions.append((path, f"failed: {e}"))

    return actions


# ------------------------------------------------------------
# Logging
# ------------------------------------------------------------
def write_log(log_path: str, actions: List[Tuple[str, str]]):
    """
    Write a deletion/quarantine log.
    """
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"Duplicate Cleanup Log - {datetime.datetime.now()}\n\n")
        for path, action in actions:
            f.write(f"{path} -> {action}\n")


# ------------------------------------------------------------
# High-level dedupe workflow
# ------------------------------------------------------------
def dedupe(
    conn,
    table_name: str,
    hash_type: str = "md5",
    safe_delete: bool = True,
    quarantine_dir: Optional[str] = None,
    progress_callback=None,
) -> Tuple[int, List[Tuple[str, str]]]:
    """
    Perform full dedupe:
    - Find duplicates
    - Choose best file to keep
    - Delete/quarantine others
    - Return (duplicate_sets, actions)
    """
    duplicates = find_duplicates(conn, table_name, hash_type)
    actions = []
    total_sets = len(duplicates)

    for i, (h, rows) in enumerate(duplicates.items()):
        keep = choose_best_file(rows)
        set_actions = delete_or_quarantine(
            rows,
            keep,
            safe_delete=safe_delete,
            quarantine_dir=quarantine_dir,
        )
        actions.extend(set_actions)

        if progress_callback:
            progress_callback((i + 1) / total_sets, f"Processed hash {h}")

    return total_sets, actions