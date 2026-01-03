"""
cli.py
------

Command-line interface for the HashDB Toolbox.

Subcommands:
    hashdb scan --dir <folder> --db <db> --hash md5|sha256
    hashdb verify --db <db> --hash md5|sha256 [--dir <folder>]
    hashdb dedupe --db <db> --hash md5|sha256 [--hard-delete]
    hashdb cleanup --db <db> [--delete-zero]
    hashdb export --db <db> --hash md5|sha256 --out <file>
    hashdb export-chunked --db <db> --hash md5|sha256 --outdir <folder>
    hashdb report --db <db> --hash md5|sha256 --out <file>

This module is pure orchestration.
"""

import argparse
import os
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from .db import open_db, ensure_schema
from .scanner import build_work_list
from .hasher import run_hashing, compute_hash
from .deduper import dedupe
from .maintenance import run_cleanup
from .exporter import export_hashes, export_hashes_chunked
from .reporter import write_duplicate_report, generate_summary
from shared.progress import cli_progress


TABLE_NAME = "file_hashes"


# ------------------------------------------------------------
# Subcommand: scan
# ------------------------------------------------------------
def cmd_scan(args):
    folder = args.directory
    db_path = args.db or os.path.join(folder, ".hashdb.sqlite")
    hash_type = args.hash

    if not os.path.isdir(folder):
        print(f"[ERROR] Folder not found: {folder}", flush=True)
        return

    with open_db(db_path) as conn:
        ensure_schema(conn)

        print("[INFO] Building work list…", flush=True)
        work = build_work_list(
            conn,
            TABLE_NAME,
            folder,
            rescan_mode=not args.full,
            db_get_record=lambda c, t, p: c.execute(
                f"SELECT * FROM {t} WHERE filepath=?", (p,)
            ).fetchone(),
            threads=args.threads,
        )

        print(f"[INFO] {len(work)} files need hashing", flush=True)

        batch_size = args.batch_size if hasattr(args, 'batch_size') and args.batch_size else 50
        committed_count = [0]  # mutable container for closure

        def commit_batch(records):
            """Write a batch of records to DB and commit."""
            for rec in records:
                conn.execute(
                    f"""
                    INSERT INTO {TABLE_NAME} (
                        filepath, filename, size_bytes,
                        hash_md5, hash_sha256,
                        imported_on, last_scanned_on,
                        created_on, modified_on, flags
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(filepath) DO UPDATE SET
                        filename=excluded.filename,
                        size_bytes=excluded.size_bytes,
                        hash_md5=excluded.hash_md5,
                        hash_sha256=excluded.hash_sha256,
                        last_scanned_on=excluded.last_scanned_on,
                        created_on=excluded.created_on,
                        modified_on=excluded.modified_on
                    """,
                    (
                        rec["filepath"], rec["filename"], rec["size_bytes"],
                        rec["hash_md5"], rec["hash_sha256"],
                        rec["imported_on"], rec["last_scanned_on"],
                        rec["created_on"], rec["modified_on"], rec["flags"],
                    )
                )
            conn.commit()
            committed_count[0] += len(records)
            print(f"[INFO] Committed {committed_count[0]} records to DB", flush=True)

        results = run_hashing(
            work,
            hash_type,
            threads=args.threads,
            progress_callback=cli_progress,
            batch_callback=commit_batch,
            batch_size=batch_size,
        )

    print("[DONE] Scan complete.", flush=True)


# ------------------------------------------------------------
# Subcommand: verify
# ------------------------------------------------------------
def _verify_one(filepath: str, expected_hash: str, hash_type: str):
    if not filepath or not os.path.exists(filepath):
        return "missing", filepath, expected_hash, None, None

    if not expected_hash:
        return "nohash", filepath, expected_hash, None, None

    try:
        actual = compute_hash(filepath, hash_type)
    except Exception as e:
        return "error", filepath, expected_hash, None, str(e)

    if actual != expected_hash:
        return "mismatch", filepath, expected_hash, actual, None

    return "ok", filepath, expected_hash, actual, None


def cmd_verify(args):
    db_path = args.database
    hash_type = args.hash
    threads = args.threads
    root_filter = args.dir

    hash_col = "hash_md5" if hash_type == "md5" else "hash_sha256"

    root_prefix = None
    if root_filter:
        if not os.path.isdir(root_filter):
            print(f"[ERROR] Folder not found: {root_filter}", flush=True)
            return
        root_prefix = os.path.normpath(os.path.abspath(root_filter))

    with open_db(db_path) as conn:
        ensure_schema(conn)

        cur = conn.cursor()
        cur.execute(f"SELECT filepath, {hash_col} FROM {TABLE_NAME}")
        rows = cur.fetchall()

    if root_prefix:
        rows = [r for r in rows if os.path.normpath(r["filepath"]).startswith(root_prefix)]

    total = len(rows)
    if total == 0:
        print("[INFO] No records to verify.", flush=True)
        return

    print(f"[INFO] Verifying {total} DB record(s) using {hash_type.upper()}…", flush=True)

    counts = {
        "ok": 0,
        "missing": 0,
        "nohash": 0,
        "mismatch": 0,
        "error": 0,
    }

    problems_shown = 0

    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = []
        for r in rows:
            futures.append(
                executor.submit(_verify_one, r["filepath"], r[hash_col], hash_type)
            )

        for i, fut in enumerate(as_completed(futures)):
            status, filepath, expected, actual, err = fut.result()
            counts[status] += 1

            if status in ("missing", "nohash", "mismatch", "error"):
                problems_shown += 1
                if status == "missing":
                    print(f"[MISSING] {filepath}", flush=True)
                elif status == "nohash":
                    print(f"[NOHASH]  {filepath}", flush=True)
                elif status == "mismatch":
                    print(f"[MISMATCH] {filepath}", flush=True)
                    print(f"  expected: {expected}", flush=True)
                    print(f"  actual:   {actual}", flush=True)
                else:
                    print(f"[ERROR] {filepath}: {err}", flush=True)
                    
            if args.progress and (i + 1) % 200 == 0:
                cli_progress((i + 1) / total, "verify")

    print("\n[DONE] Verify complete.", flush=True)
    print(
        " ".join(
            [
                f"OK={counts['ok']}",
                f"MISSING={counts['missing']}",
                f"NOHASH={counts['nohash']}",
                f"MISMATCH={counts['mismatch']}",
                f"ERROR={counts['error']}",
            ]
        ),
        flush=True,
    )


# ------------------------------------------------------------
# Subcommand: dedupe
# ------------------------------------------------------------
def cmd_dedupe(args):
    db_path = args.database
    hash_type = args.hash
    safe_delete = not args.hard_delete

    quarantine = None
    if safe_delete:
        quarantine = args.quarantine or "quarantine"
        os.makedirs(quarantine, exist_ok=True)

    with open_db(db_path) as conn:
        sets, actions = dedupe(
            conn,
            TABLE_NAME,
            hash_type=hash_type,
            safe_delete=safe_delete,
            quarantine_dir=quarantine,
            progress_callback=cli_progress,
        )

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = f"dedupe_log_{ts}.txt"
    with open(log_path, "w") as f:
        for path, action in actions:
            f.write(f"{path} -> {action}\n")

    print(f"[DONE] Dedupe complete. {sets} sets processed.", flush=True)
    print(f"[LOG] {log_path}", flush=True)


# ------------------------------------------------------------
# Subcommand: cleanup
# ------------------------------------------------------------
def cmd_cleanup(args):
    db_path = args.database

    with open_db(db_path) as conn:
        missing, zero, zero_deleted, log_path = run_cleanup(
            conn,
            db_path,
            TABLE_NAME,
            delete_zero_bytes=args.delete_zero,
            threads=args.threads,
            progress_callback=cli_progress,
        )

    print(f"[DONE] Cleanup complete.", flush=True)
    print(f"Missing removed: {missing}", flush=True)
    print(f"Zero-byte found: {zero}", flush=True)
    print(f"Zero-byte deleted: {zero_deleted}", flush=True)
    print(f"[LOG] {log_path}", flush=True)


# ------------------------------------------------------------
# Subcommand: export
# ------------------------------------------------------------
def cmd_export(args):
    db_path = args.database
    hash_type = args.hash
    out = args.output

    with open_db(db_path) as conn:
        export_hashes(conn, TABLE_NAME, hash_type, out)

    print(f"[DONE] Exported hashes to {out}", flush=True)


# ------------------------------------------------------------
# Subcommand: export-chunked
# ------------------------------------------------------------
def cmd_export_chunked(args):
    db_path = args.database
    hash_type = args.hash
    outdir = args.output_dir

    with open_db(db_path) as conn:
        export_hashes_chunked(conn, TABLE_NAME, hash_type, outdir, threads=args.threads, progress_callback=cli_progress)

    print(f"[DONE] Chunked export complete: {outdir}", flush=True)


# ------------------------------------------------------------
# Subcommand: report
# ------------------------------------------------------------
def cmd_report(args):
    db_path = args.database
    hash_type = args.hash
    out = args.output

    with open_db(db_path) as conn:
        write_duplicate_report(conn, TABLE_NAME, hash_type, out)

    print(f"[DONE] Duplicate report written to {out}", flush=True)


# ------------------------------------------------------------
# Main entry point
# ------------------------------------------------------------
def _add_subcommands(sub):
    # scan
    p = sub.add_parser("scan", help="Scan and hash files")
    p.add_argument("directory", help="Directory to scan")
    p.add_argument("--db", help="Database path (default: .hashdb.sqlite in scan directory)")
    p.add_argument("--hash", choices=["md5", "sha256"], default="sha256", help="Hash algorithm (default: sha256)")
    p.add_argument("--threads", type=int, default=8, help="Worker threads (default: 8)")
    p.add_argument("--full", action="store_true", help="Full scan, ignore optimization")
    p.add_argument("--batch-size", type=int, default=50, help="Commit batch size (default: 50)")
    p.set_defaults(func=cmd_scan)

    # verify
    p = sub.add_parser("verify", help="Verify files against DB hashes (non-destructive)")
    p.add_argument("database", help="Database path")
    p.add_argument("--hash", choices=["md5", "sha256"], default="sha256", help="Hash algorithm (default: sha256)")
    p.add_argument("--threads", type=int, default=8, help="Worker threads (default: 8)")
    p.add_argument("--dir", help="Only verify records under this directory")
    p.add_argument("--progress", action="store_true", help="Show periodic progress")
    p.set_defaults(func=cmd_verify)

    # dedupe
    p = sub.add_parser("dedupe", help="Remove duplicate files")
    p.add_argument("database", help="Database path")
    p.add_argument("--hash", choices=["md5", "sha256"], default="sha256")
    p.add_argument("--threads", type=int, default=8, help="Worker threads (default: 8)")
    p.add_argument("--hard-delete", action="store_true", help="Permanently delete (dangerous)")
    p.add_argument("--quarantine", help="Quarantine directory")
    p.set_defaults(func=cmd_dedupe)

    # cleanup
    p = sub.add_parser("cleanup", help="Remove missing/zero-byte records")
    p.add_argument("database", help="Database path")
    p.add_argument("--threads", type=int, default=8, help="Worker threads (default: 8)")
    p.add_argument("--delete-zero", action="store_true", help="Delete zero-byte files")
    p.set_defaults(func=cmd_cleanup)

    # export
    p = sub.add_parser("export", help="Export hashes to file")
    p.add_argument("database", help="Database path")
    p.add_argument("output", help="Output file path")
    p.add_argument("--threads", type=int, default=8, help="Worker threads (default: 8)")
    p.add_argument("--hash", choices=["md5", "sha256"], default="sha256")
    p.set_defaults(func=cmd_export)

    # export-chunked
    p = sub.add_parser("export-chunked", help="Export hashes in chunks")
    p.add_argument("database", help="Database path")
    p.add_argument("output_dir", help="Output directory")
    p.add_argument("--threads", type=int, default=8, help="Worker threads (default: 8)")
    p.add_argument("--hash", choices=["md5", "sha256"], default="sha256")
    p.set_defaults(func=cmd_export_chunked)

    # report
    p = sub.add_parser("report", help="Generate duplicate report")
    p.add_argument("database", help="Database path")
    p.add_argument("output", help="Output report path")
    p.add_argument("--threads", type=int, default=8, help="Worker threads (default: 8)")
    p.add_argument("--hash", choices=["md5", "sha256"], default="sha256")
    p.set_defaults(func=cmd_report)


def register_cli(subparsers):
    """
    Register this tool with the toolbox CLI.
    """
    parser = subparsers.add_parser("hashdb", help="HashDB Tool")
    sub = parser.add_subparsers(dest="cmd")
    _add_subcommands(sub)


def build_parser():
    parser = argparse.ArgumentParser(description="HashDB Toolbox CLI")
    sub = parser.add_subparsers(dest="cmd")
    _add_subcommands(sub)
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        return

    args.func(args)
