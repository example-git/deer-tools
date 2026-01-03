"""
db.py
-----

Core database utilities for the HashDB system.

Responsibilities:
- Open/close SQLite connections
- Ensure the schema and indexes exist
- Provide basic helpers for common operations

This module does NOT:
- Walk directories
- Compute hashes
- Perform deduplication logic

Other modules (hasher, scanner, deduper, etc.) should build on this.
"""

import os
import sqlite3
from contextlib import contextmanager
from typing import Optional, Dict, Any


DEFAULT_TABLE_NAME = "file_hashes"


# ------------------------------------------------------------
# Connection management
# ------------------------------------------------------------
def connect(db_path: str) -> sqlite3.Connection:
    """
    Open a SQLite connection with sane defaults.
    """
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def open_db(db_path: str):
    """
    Context manager for opening/closing the DB.

    Usage:
        with open_db(db_path) as conn:
            ...
    """
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ------------------------------------------------------------
# Schema and index creation
# ------------------------------------------------------------
def ensure_schema(conn: sqlite3.Connection, table_name: str = DEFAULT_TABLE_NAME):
    """
    Ensure the file_hashes table and core indexes exist.
    Safe to call multiple times.
    """
    cur = conn.cursor()

    # Core table
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filepath TEXT NOT NULL UNIQUE,
            filename TEXT NOT NULL,
            size_bytes INTEGER,
            hash_md5 TEXT,
            hash_sha256 TEXT,
            imported_on TEXT,
            last_scanned_on TEXT,
            created_on TEXT,
            modified_on TEXT,
            flags TEXT
        )
    """)

    # Indexes
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_filepath ON {table_name}(filepath)")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_hash_md5 ON {table_name}(hash_md5)")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_hash_sha256 ON {table_name}(hash_sha256)")

    conn.commit()


# ------------------------------------------------------------
# Basic CRUD helpers
# ------------------------------------------------------------
def upsert_file_record(
    conn: sqlite3.Connection,
    table_name: str,
    record: Dict[str, Any],
):
    """
    Insert or update a file record based on filepath.

    Expected keys in record:
        - filepath (required)
        - filename
        - size_bytes
        - hash_md5
        - hash_sha256
        - imported_on
        - last_scanned_on
        - created_on
        - modified_on
        - flags
    """
    # Ensure required key
    if "filepath" not in record:
        raise ValueError("record['filepath'] is required for upsert_file_record")

    fields = [
        "filepath",
        "filename",
        "size_bytes",
        "hash_md5",
        "hash_sha256",
        "imported_on",
        "last_scanned_on",
        "created_on",
        "modified_on",
        "flags",
    ]

    # Build column/value lists
    cols = []
    placeholders = []
    values = []

    for field in fields:
        cols.append(field)
        placeholders.append("?")
        values.append(record.get(field))

    col_list = ", ".join(cols)
    placeholder_list = ", ".join(placeholders)

    # For update on conflict, we set everything except filepath
    update_assignments = ", ".join(f"{col}=excluded.{col}" for col in cols if col != "filepath")

    sql = f"""
        INSERT INTO {table_name} ({col_list})
        VALUES ({placeholder_list})
        ON CONFLICT(filepath) DO UPDATE SET
            {update_assignments}
    """

    conn.execute(sql, values)


def get_record_by_path(
    conn: sqlite3.Connection,
    table_name: str,
    filepath: str,
) -> Optional[sqlite3.Row]:
    """
    Fetch a single record by filepath.
    Returns a sqlite3.Row or None.
    """
    cur = conn.cursor()
    cur.execute(
        f"SELECT * FROM {table_name} WHERE filepath = ?",
        (filepath,),
    )
    return cur.fetchone()


def iter_all_records(conn: sqlite3.Connection, table_name: str):
    """
    Generator over all records in the table.
    """
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {table_name}")
    for row in cur:
        yield row


def vacuum(conn: sqlite3.Connection):
    """
    Run VACUUM to compact the database.
    """
    conn.execute("VACUUM")
    conn.commit()