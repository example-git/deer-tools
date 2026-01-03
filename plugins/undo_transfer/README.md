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
  --mode cli \
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
  --mode cli \
  --log transfer.log \
  --temp /temp/dir \
  --restore /output/dir
```

Shows file mappings without creating output files (default behavior).

### MD5 vs SHA-256

**Use MD5 (faster, less secure):**
```bash
python toolbox.py undo-transfer \
  --mode cli \
  --log transfer.log \
  --temp /temp/dir \
  --restore /output/dir \
  --hash md5 \
  --commit
```

**Use SHA-256 (slower, more secure - default):**
```bash
python toolbox.py undo-transfer \
  --mode cli \
  --log transfer.log \
  --temp /temp/dir \
  --restore /output/dir \
  --hash sha256
```

## Transfer Log Format

Undo Transfer parses logs that include an original path and a checksum.

### Windows-Style Paths
```
C:\Users\Alice\Documents\report.pdf | MD5: d41d8cd98f00b204e9800998ecf8427e
C:\Users\Alice\Photos\vacation.jpg | SHA256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

### Unix-Style Paths
```
/Users/alice/Documents/report.pdf | MD5: d41d8cd98f00b204e9800998ecf8427e
/Users/alice/Photos/vacation.jpg | SHA256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

### Mixed Formats (Safe Cross-Platform)
The parser normalizes path separators automatically:
```
C:\Users\Alice\Documents\report.pdf | SHA256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

## How It Works

### Restoration Process

1. **Parse Log**: Extract original paths and hashes
2. **Scan Temp Directory**: Find all files in the temporary directory
3. **Hash Files**: Compute checksums for all temp files (multi-threaded)
4. **Match Hashes**: Compare temp file hashes with log entries
5. **Restore**: Move files to original paths, creating directories as needed

### Hash Matching Algorithm

```python
log_entry = {"original_path": "/docs/report.pdf", "hash_type": "md5", "hash": "…"}
temp_file_hash = compute_hash("/actual/temp/dir/file001.tmp")

if temp_file_hash == log_entry["hash"]:
    move("/actual/temp/dir/file001.tmp", "/restore/docs/report.pdf")
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
  --mode cli \
  --log transfer.log \
  --temp /temp \
  --restore /output \
  --threads 16 \
  --commit
```

Default is 8 threads. Increase for SSDs, decrease for HDDs.

### MD5 Cache

Undo Transfer caches hashes in `<temp_dir>/md5_cache.json` to speed up re-runs:

**Enable cache (default for MD5):**
```bash
python toolbox.py undo-transfer \
  --mode cli \
  --log transfer.log \
  --temp /temp \
  --restore /output \
  --hash md5 \
  --commit
```

*Note: There is no `--no-cache` flag in this implementation.*

The cache can store both MD5 and SHA-256 values when they are computed.

### Force Overwrite

If a destination path already exists, there is no dedicated overwrite/force flag in this implementation.
```bash
python toolbox.py undo-transfer \
  --mode cli \
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
  --mode cli \
  --log flatten_log.txt \
  --temp /temp \
  --restore /photos_restored \
  --commit
```

### Recovering from Batch Rename

After a batch rename operation with log:
```bash
python toolbox.py undo-transfer \
  --mode cli \
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
  --mode cli \
  --log sync_log.txt \
  --temp /downloads \
  --restore /cloud_restored \
  --commit
```

## Log File Requirements

### Minimum Requirements

Transfer logs must:
1. Contain a `|` separator between the original path and the hash
2. Include either `MD5:` or `SHA256:` (or a bare hex digest)
3. Use a consistent original path root that matches your configured `ORIGINAL_ROOT`

### Example Valid Logs

**Simple format:**
```
/original/path/file.txt | MD5: d41d8cd98f00b204e9800998ecf8427e
/original/other/doc.pdf | SHA256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

**With timestamps:**
```
2024-01-15 10:30:45 | /original/path/file.txt | MD5: d41d8cd98f00b204e9800998ecf8427e
2024-01-15 10:31:12 | /original/other/doc.pdf | SHA256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

**With extra metadata (ignored):**
```
[INFO] Hashed: /original/path/file.txt | MD5: d41d8cd98f00b204e9800998ecf8427e (1.2 MB)
```

The parser extracts the original path on the left and the hash on the right, and ignores extra text.

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

Settings are stored in `config/undo_transfer.json` (created/updated on first run). The persisted keys mirror the tool’s internal settings, for example:

```json
{
  "LOG_FILE": "./transfer.log",
  "TEMP_DIRECTORY": "/tmp/files",
  "ORIGINAL_ROOT": "C:/Users/Alice/Pictures",
  "RESTORE_ROOT": "/output/restored",
  "TARGET_SUBFOLDERS": ["LPictures"],
  "AUTO_SCAN_SUBFOLDERS": true,
  "DRY_RUN": true,
  "THREAD_COUNT": 8,
  "HASH_TYPE": "sha256",
  "UNDO_LOG": "/tmp/files/undo_transfer.log",
  "CACHE_FILE": "/tmp/files/md5_cache.json",
  "INTERACTIVE_MODE": true
}
```

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
6. Cache → Store hashes for future runs
```

### Threading Model

Undo Transfer uses `ThreadPoolExecutor` for hashing:
- **Log parsing**: Single-threaded (fast, CPU-light)
- **Directory scanning**: Single-threaded (I/O bound)
- **Hashing**: Multi-threaded (`hashlib` releases GIL)
- **File moving**: Single-threaded-ish (filesystem limitation)

Threading is optimal because:
- `hashlib` releases the GIL during hash computation
- File I/O releases the GIL
- Shared state (cache, progress) is simple with threads

## API Usage

Import Undo Transfer modules for programmatic use:

```python
from plugins.undo_transfer.restorer import UndoWorker

settings = {
  "LOG_FILE": "./transfer.log",
  "TEMP_DIRECTORY": "/tmp/files",
  "ORIGINAL_ROOT": "C:/Users/Alice/Pictures",
  "RESTORE_ROOT": "/output/restored",
  "TARGET_SUBFOLDERS": ["LPictures"],
  "DRY_RUN": True,
  "THREAD_COUNT": 8,
  "HASH_TYPE": "sha256",
  "UNDO_LOG": "/tmp/files/undo_transfer.log",
  "CACHE_FILE": "/tmp/files/md5_cache.json",
}

worker = UndoWorker(settings)
worker.start()
worker.join()
```

## Related Tools

- **HashDB**: Generate and verify file checksums
- **Extension Repair**: Fix file extensions based on magic bytes

---

**Back to:** [Deer Toolbox Main Documentation](../README.md)
