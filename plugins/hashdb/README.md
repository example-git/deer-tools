# 🔒 HashDB - File Integrity Management System

**HashDB** is a comprehensive file integrity and deduplication tool that maintains an SQLite database of file checksums. It provides scanning, verification, duplicate detection, and export capabilities for managing large file collections.

## Features

- **Fast Hashing**: Multi-threaded MD5 and SHA-256 computation with automatic GIL release
- **Incremental Scanning**: Only rehash files when modified timestamps change
- **Integrity Verification**: Compare current file hashes against database records
- **Deduplication**: Identify and safely remove duplicate files
- **Batch Processing**: Chunked operations with progress tracking
- **Export Formats**: CSV, JSON, and XML reporting
- **Database Maintenance**: Cleanup orphaned records and optimize database

## Quick Start

### Basic Scanning

**Scan a directory (default: SHA-256 hash, auto-named database):**
```bash
python toolbox.py hashdb scan /path/to/files
```

This creates `/path/to/files/.hashdb.sqlite` containing file records.

**Use MD5 instead of SHA-256:**
```bash
python toolbox.py hashdb scan /path/to/files --hash md5
```

**Custom database location:**
```bash
python toolbox.py hashdb scan /path/to/files --db /custom/hashdb.sqlite
```

### Verification

**Verify all files in database:**
```bash
python toolbox.py hashdb verify /path/to/.hashdb.sqlite
```

**Verify only a subdirectory:**
```bash
python toolbox.py hashdb verify /path/to/.hashdb.sqlite --dir /path/to/subfolder
```

Verification output shows:
- `OK` - File matches database hash
- `MISSING` - File no longer exists
- `NOHASH` - File exists but has no hash in database
- `MISMATCH` - Hash differs (file modified or corrupted)
- `ERROR` - Unable to read file

### Deduplication

**Find and list duplicates (dry-run):**
```bash
python toolbox.py hashdb dedupe /path/to/.hashdb.sqlite --hash sha256
```

**Remove duplicates (keep best file, quarantine others):**
```bash
python toolbox.py hashdb dedupe /path/to/.hashdb.sqlite --hash sha256 --quarantine /path/to/quarantine
```

**Hard delete duplicates (dangerous - no quarantine):**
```bash
python toolbox.py hashdb dedupe /path/to/.hashdb.sqlite --hash sha256 --hard-delete
```

The deduplication algorithm selects the "best" file to keep based on:
- Shortest path (fewer subdirectories)
- Shortest filename
- Absence of duplicate indicators (`_1`, `(1)`, `-copy`, etc.)
- Oldest creation time

### Export and Reporting

**Export hashes:**
```bash
python toolbox.py hashdb export /path/to/.hashdb.sqlite report.csv --hash sha256
```

**Export chunked (for large databases):**
```bash
python toolbox.py hashdb export-chunked /path/to/.hashdb.sqlite /output/dir --hash sha256
```

**Generate duplicate report:**
```bash
python toolbox.py hashdb report /path/to/.hashdb.sqlite report.txt --hash sha256
```

### Database Maintenance

**Clean up orphaned records (files no longer exist):**
```bash
python toolbox.py hashdb cleanup /path/to/.hashdb.sqlite
```

**Vacuum and optimize database:**
```bash
python toolbox.py hashdb vacuum --db /path/to/.hashdb.sqlite
```

## Database Schema

HashDB stores file records in SQLite with the following schema:

```sql
CREATE TABLE files (
    filepath TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    created_on TEXT,              -- ISO 8601 timestamp (macOS/Windows only)
    modified_on TEXT NOT NULL,    -- ISO 8601 timestamp
    imported_on TEXT NOT NULL,    -- First scan timestamp
    last_scanned_on TEXT NOT NULL,-- Most recent scan timestamp
    hash_md5 TEXT,                -- MD5 hex digest (if --hash md5)
    hash_sha256 TEXT,             -- SHA-256 hex digest (if --hash sha256)
    flags TEXT                    -- Reserved for future use
);

CREATE INDEX idx_hash_md5 ON files(hash_md5);
CREATE INDEX idx_hash_sha256 ON files(hash_sha256);
CREATE INDEX idx_modified_on ON files(modified_on);
```

## Performance Tuning

### Thread Count

Adjust worker threads based on your CPU count:
```bash
python toolbox.py hashdb scan /path --threads 16
```

Default is 8 threads. More threads improve performance on SSDs but may bottleneck on HDDs.

### Batch Size

Control database commit frequency:
```bash
python toolbox.py hashdb scan /path --batch-size 100
```

Default is 50 records per batch. Larger batches reduce database overhead but increase memory usage.

### Incremental vs Full Scan

**Incremental scan (default):** Only rehash files with changed `modified_on` timestamps
```bash
python toolbox.py hashdb scan /path
```

**Full rescan:** Rehash all files regardless of timestamps
```bash
python toolbox.py hashdb scan /path --force-rescan
```

## Common Use Cases

### Initial Backup Verification

After copying files to backup storage, verify integrity:
```bash
# Scan source directory
python toolbox.py hashdb scan /source --db source.sqlite

# Scan backup directory
python toolbox.py hashdb scan /backup --db backup.sqlite

# Export both to CSV and compare externally
python toolbox.py hashdb export --db source.sqlite --format csv --output source.csv
python toolbox.py hashdb export --db backup.sqlite --format csv --output backup.csv
```

### Periodic Integrity Checks

Set up a cron job to verify file integrity:
```bash
0 2 * * 0 python /path/to/toolbox.py hashdb verify /data/.hashdb.sqlite --report weekly_check.log
```

### Cleaning Up Duplicates

After merging multiple photo libraries:
```bash
# Scan combined directory
python toolbox.py hashdb scan /photos --hash sha256

# Find duplicates (dry-run)
python toolbox.py hashdb dedupe --db /photos/.hashdb.sqlite --hash sha256

# Review quarantine directory, then delete if satisfied
rm -rf /photos/_quarantine
```

### Archival Checksums

Generate checksums for archival purposes:
```bash
# Scan archive
python toolbox.py hashdb scan /archive --hash sha256

# Export checksums
python toolbox.py hashdb export --db /archive/.hashdb.sqlite --format csv --output archive_checksums.csv
```

## GUI Mode

Launch the graphical interface:
```bash
python toolbox.py
# Select "HashDB" from the menu
```

The GUI provides:
- Visual progress bars
- Real-time log output
- Point-and-click directory selection
- Preset configurations

## Configuration

HashDB settings are stored in `config/hashdb.json`:

```json
{
  "default_hash_algorithm": "sha256",
  "default_threads": 8,
  "default_batch_size": 50,
  "auto_create_db": true,
  "quarantine_dir_name": "_quarantine"
}
```

## Troubleshooting

### Slow Performance

**Problem:** Hashing takes too long

**Solutions:**
- Reduce thread count for HDDs: `--threads 4`
- Increase batch size: `--batch-size 100`
- Use MD5 instead of SHA-256: `--hash md5` (faster but less secure)

### Permission Errors

**Problem:** `[Errno 13] Permission denied`

**Solutions:**
- Check file permissions: `ls -la /path/to/file`
- Run with appropriate privileges
- Skip unreadable files (hashdb automatically continues)

### Database Locked

**Problem:** `database is locked`

**Solutions:**
- Close other programs accessing the database
- Ensure database is on local filesystem (not network share)
- Increase SQLite timeout (edit `db.py` if needed)

### Missing Files in Verification

**Problem:** Many files show as `MISSING` during verification

**Causes:**
- Files were moved or deleted after scanning
- Database is for a different directory
- Path mappings changed (e.g., different mount point)

**Solution:** Rescan the directory to update the database

## Architecture

### Module Overview

| Module | Purpose |
|--------|---------|
| `tool.py` | CLI entry point and mode routing |
| `cli.py` | Command-line interface implementation |
| `toolbox/webui.py` | Browser-based GUI launcher (shared across tools) |
| `db.py` | SQLite database operations |
| `hasher.py` | Multi-threaded hash computation |
| `scanner.py` | Directory traversal and metadata collection |
| `deduper.py` | Duplicate detection and removal logic |
| `exporter.py` | Report generation (CSV, JSON, XML) |
| `reporter.py` | Summary statistics |
| `maintenance.py` | Database cleanup and optimization |

### Data Flow

```
1. Scanner → Collect file metadata (size, timestamps)
2. Scanner → Compare against database (incremental mode)
3. Hasher → Compute hashes for new/modified files (threaded)
4. Database → Batch commit records
5. Reporter → Generate statistics and summaries
```

### Threading Model

HashDB uses `ThreadPoolExecutor` for parallelization:
- **Scanner**: Single-threaded metadata collection (I/O bound)
- **Hasher**: Multi-threaded hash computation (GIL-releasing via `hashlib`)
- **Database**: Single-threaded writes (SQLite limitation)

This design is optimal because:
- `hashlib` releases the GIL during hash computation
- Thread overhead is minimal compared to process overhead
- Shared state (database connection, progress tracking) is simple with threads

## API Usage

Import HashDB modules directly for programmatic use:

```python
from plugins.hashdb import db, hasher, scanner, deduper

# Create database
conn = db.create_database("my_hashes.sqlite", "sha256")

# Scan directory
work_list = scanner.build_work_list(
    conn=conn,
    table_name="files",
    root="/path/to/scan",
    rescan_mode=True,
    db_get_record=lambda fp: db.get_record(conn, "files", fp),
    threads=8,
)

# Hash files
def on_batch(records):
    db.bulk_insert(conn, "files", records)

hasher.run_hashing(
    work_list=work_list,
    hash_type="sha256",
    threads=8,
    batch_callback=on_batch,
)

# Find duplicates
duplicates = deduper.find_duplicates(conn, "files", "sha256")
print(f"Found {len(duplicates)} duplicate sets")
```

## Related Tools

- **Extension Repair**: Fix file extensions based on magic bytes
- **Undo Transfer**: Restore files using hash-based matching

---

**Back to:** [Deer Toolbox Main Documentation](../README.md)
