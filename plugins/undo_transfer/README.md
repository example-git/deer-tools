# ↩️ Undo Transfer - File Restoration Tool

**Undo Transfer** is a recovery tool that restores files to their original directory structure using hash-based matching. It parses transfer logs from file moving operations and rebuilds folder hierarchies by matching files in a temporary directory.

## Features

- **Hash-Based Matching**: MD5 and SHA-256 support for reliable file identification
- **Log Parsing**: Supports Windows-style paths (safely handles backslashes on Unix)
- **Deterministic Behavior**: Handles duplicate hash collisions consistently
- **Multi-threaded Processing**: Parallel hashing with progress tracking
- **Cache Management**: MD5 cache for faster re-runs
- **Dry-Run Mode**: Preview restoration without making changes
- **Progress Tracking**: Real-time updates during hashing and restoration

## Quick Start

### Basic Restoration

**Restore files from transfer log:**
```bash
python toolbox.py undo-transfer \
  --log transfer.log \
  --temp /temp/dir \
  --restore /output/dir \
  --commit
```

This reads `transfer.log`, hashes files in `/temp/dir`, and restores them to `/output/dir` with original folder structure.

### Dry-Run Mode

**Preview what would be restored:**
```bash
python toolbox.py undo-transfer \
  --log transfer.log \
  --temp /temp/dir \
  --restore /output/dir
```

Shows file mappings without creating output files (default behavior).

### MD5 vs SHA-256

**Use MD5 (faster, less secure):**
```bash
python toolbox.py undo-transfer \
  --log transfer.log \
  --temp /temp/dir \
  --restore /output/dir \
  --hash md5 \
  --commit
```

**Use SHA-256 (slower, more secure - default):**
```bash
python toolbox.py undo-transfer restore \
  --log transfer.log \
  --temp /temp/dir \
  --restore /output/dir \
  --hash sha256
```

## Transfer Log Format

Undo Transfer parses logs with the following formats:

### Windows-Style Paths
```
C:\Users\Alice\Documents\report.pdf -> C:\Temp\file001.tmp
C:\Users\Alice\Photos\vacation.jpg -> C:\Temp\file002.tmp
```

### Unix-Style Paths
```
/Users/alice/Documents/report.pdf -> /tmp/file001.tmp
/Users/alice/Photos/vacation.jpg -> /tmp/file002.tmp
```

### Mixed Formats (Safe Cross-Platform)
The parser normalizes path separators automatically:
```
C:\Users\Alice\Documents\report.pdf -> /tmp/file001.tmp
```

## How It Works

### Restoration Process

1. **Parse Log**: Extract original paths and temp file mappings
2. **Scan Temp Directory**: Find all files in the temporary directory
3. **Hash Files**: Compute checksums for all temp files (multi-threaded)
4. **Match Hashes**: Compare temp file hashes with log entries
5. **Restore**: Copy files to original paths, creating directories as needed

### Hash Matching Algorithm

```python
log_entry = {"original_path": "/docs/report.pdf", "temp_path": "/tmp/file001.tmp"}
temp_file_hash = compute_hash("/actual/temp/dir/file001.tmp")

if temp_file_hash == log_entry_hash:
    copy("/actual/temp/dir/file001.tmp", "/restore/docs/report.pdf")
```

### Duplicate Hash Handling

If multiple temp files have the same hash:
- **First match wins**: Uses the first temp file encountered
- **Deterministic**: Same input always produces same output
- **Logged**: Warns about duplicate hashes

## Advanced Options

### Thread Count

Adjust hashing parallelization:
```bash
python toolbox.py undo-transfer \
  --log transfer.log \
  --temp /temp \
  --restore /output \
  --threads 16 \
  --commit
```

Default is 8 threads. Increase for SSDs, decrease for HDDs.

### MD5 Cache

Undo Transfer caches MD5 hashes in `<temp_dir>/.md5_cache.json` to speed up re-runs:

**Enable cache (default for MD5):**
```bash
python toolbox.py undo-transfer \
  --log transfer.log \
  --temp /temp \
  --restore /output \
  --hash md5 \
  --commit
```

**Disable cache:**
```bash
python toolbox.py undo-transfer \
  --log transfer.log \
  --temp /temp \
  --restore /output \
  --hash md5 \
  --commit
```

*Note: MD5 cache is always used when available; there's no --no-cache flag in this implementation.*

Cache is automatically disabled for SHA-256 (different hash algorithm).

### Force Overwrite

By default, restoration skips existing files. To overwrite:
```bash
python toolbox.py undo-transfer \
  --log transfer.log \
  --temp /temp \
  --restore /output \
  --commit
```

*Note: This implementation doesn't have a separate --force flag; --commit performs the restoration.*

## Common Use Cases

### Undoing File Flattening

After accidentally flattening a directory structure:

```bash
# Original structure:
#   /photos/2024/january/img1.jpg
#   /photos/2024/february/img2.jpg
#
# Flattened to:
#   /temp/img1.jpg
#   /temp/img2.jpg

# Restore with transfer log
python toolbox.py undo-transfer \
  --log flatten_log.txt \
  --temp /temp \
  --restore /photos_restored \
  --commit
```

### Recovering from Batch Rename

After a batch rename operation with log:
```bash
python toolbox.py undo-transfer \
  --log rename_log.txt \
  --temp /renamed_files \
  --restore /original_structure \
  --commit
```

### Cloud Sync Recovery

Restore files after cloud sync flattened folder structure:
```bash
# Download flattened files to /downloads
# Get transfer log from sync software

python toolbox.py undo-transfer \
  --log sync_log.txt \
  --temp /downloads \
  --restore /cloud_restored \
  --commit
```

## Log File Requirements

### Minimum Requirements

Transfer logs must:
1. Contain `->` separator between original and temp paths
2. Have at least one path pair per line
3. Use consistent path format (Windows or Unix)

### Example Valid Logs

**Simple format:**
```
/original/path/file.txt -> /temp/abc123.tmp
/original/other/doc.pdf -> /temp/def456.tmp
```

**With timestamps:**
```
2024-01-15 10:30:45 | /original/path/file.txt -> /temp/abc123.tmp
2024-01-15 10:31:12 | /original/other/doc.pdf -> /temp/def456.tmp
```

**With extra metadata (ignored):**
```
[INFO] Transferring: /original/path/file.txt -> /temp/abc123.tmp (1.2 MB)
```

The parser extracts paths on either side of `->` and ignores extra text.

## Troubleshooting

### Hash Mismatches

**Problem:** Files not restored (hash mismatch)

**Causes:**
- Temp files modified after log was created
- Wrong hash algorithm (log uses MD5, you specified SHA-256)
- File corruption

**Solutions:**
- Check log format: does it specify hash type?
- Verify temp files haven't been modified: `ls -l /temp`
- Try both hash algorithms: `--hash md5` and `--hash sha256`

### Path Not Found

**Problem:** `FileNotFoundError` during restoration

**Causes:**
- Original path references a different root
- Path contains special characters
- Permission issues

**Solutions:**
- Use `--dry-run` to see what paths would be created
- Check log paths match expected structure
- Ensure restore directory is writable

### Duplicate Hashes

**Problem:** Warning about duplicate hashes

**Cause:** Multiple temp files have identical content

**Behavior:** Tool uses first match (deterministic)

**Impact:** Some files may not restore if temp directory has duplicates

**Solution:** Review log and temp directory for unexpected duplicates

### Slow Performance

**Problem:** Hashing takes too long

**Solutions:**
- Reduce thread count for HDDs: `--threads 4`
- Use MD5 instead of SHA-256: `--hash md5`
- Enable cache for repeated runs (MD5 only)

## Configuration

Settings are stored in `config/undo_transfer.json`:

```json
{
  "default_hash_algorithm": "sha256",
  "default_threads": 8,
  "enable_md5_cache": true,
  "cache_file_name": ".md5_cache.json",
  "overwrite_existing": false
}
```

**Key settings:**
- `default_hash_algorithm`: `"md5"` or `"sha256"`
- `enable_md5_cache`: Speed up MD5 re-runs
- `overwrite_existing`: Allow overwriting files in restore directory

## GUI Mode

Launch the graphical interface:
```bash
python toolbox.py
# Select "Undo Transfer" from the menu
```

The GUI provides:
- File pickers for log, temp, and restore directories
- Hash algorithm selector
- Dry-run checkbox
- Live progress bar with phase tracking
- Scrollable log output

## Architecture

### Module Overview

| Module | Purpose |
|--------|---------|
| `tool.py` | CLI entry point and mode routing |
| `toolbox/webui.py` | Browser-based GUI launcher (shared across tools) |
| `log_parser.py` | Parse transfer logs (Windows/Unix paths) |
| `restorer.py` | Hash matching and file restoration logic |
| `md5_cache.py` | Cache management for faster MD5 re-runs |
| `config.py` | Settings persistence |
| `utils.py` | Path normalization and file operations |
| `cli_progress.py` | Progress bar for CLI mode |

### Data Flow

```
1. Log Parser → Extract (original_path, temp_path) pairs
2. Scanner → Find all files in temp directory
3. Hasher → Compute hashes (multi-threaded, GIL-releasing)
4. Matcher → Map temp_hash → original_path
5. Restorer → Copy temp_file → original_path
6. Cache → Store MD5 hashes for future runs
```

### Threading Model

Undo Transfer uses `ThreadPoolExecutor` for hashing:
- **Log parsing**: Single-threaded (fast, CPU-light)
- **Directory scanning**: Single-threaded (I/O bound)
- **Hashing**: Multi-threaded (`hashlib` releases GIL)
- **File copying**: Single-threaded (filesystem limitation)

Threading is optimal because:
- `hashlib` releases the GIL during hash computation
- File I/O releases the GIL
- Shared state (cache, progress) is simple with threads

## API Usage

Import Undo Transfer modules for programmatic use:

```python
from plugins.undo_transfer import log_parser, restorer, md5_cache

# Parse log
entries = log_parser.parse_log("transfer.log")
print(f"Found {len(entries)} entries")

# Build temp file mapping
cache = md5_cache.MD5Cache("/temp", enabled=True)
temp_map = restorer.build_temp_hash_map(
    temp_dir="/temp",
    hash_algorithm="md5",
    threads=8,
    cache=cache,
)

# Restore files
stats = restorer.restore_files(
    log_entries=entries,
    temp_map=temp_map,
    restore_dir="/output",
    dry_run=False,
)

print(f"Restored: {stats['restored']}")
print(f"Skipped: {stats['skipped']}")
print(f"Failed: {stats['failed']}")
```

## Related Tools

- **HashDB**: Generate and verify file checksums
- **Extension Repair**: Fix file extensions based on magic bytes

---

**Back to:** [Deer Toolbox Main Documentation](../README.md)
