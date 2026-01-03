# 📁 Extension Repair - Magic-Byte File Type Detector

**Extension Repair** is a strict-mode file type detection tool that uses magic-byte signatures to identify files and optionally rename them with correct extensions. It handles ambiguous formats intelligently and provides multiple operation modes for safety.

## Features

- **Strict Magic-Byte Detection**: No guessing - only classify files with known signatures
- **Multi-threaded Processing**: Parallel file type detection and renaming
- **Conflict-Free Renaming**: Automatic numeric suffixes to prevent overwrites
- **Multiple Operation Modes**: Dry-run, report-only, quarantine, and commit
- **Output Directory Support**: Move corrected files to separate location
- **Comprehensive Logging**: JSON and text log formats
- **Console UI**: Split-pane curses interface with live progress

## Supported File Types

### Images
- JPEG (`.jpg`)
- PNG (`.png`)
- GIF (`.gif`)
- BMP (`.bmp`)
- TIFF (`.tif`)
- JPEG2000 (`.jp2`)
- ICO (`.ico`)
- WEBP (`.webp`)
- AVIF (`.avif`)
- HEIC/HEIF (`.heic`)

### Archives
- ZIP (`.zip`)
- RAR (`.rar`)
- 7-Zip (`.7z`)
- BZ2 (`.bz2`)
- XZ (`.xz`)
- GZIP (`.gz`)

### Audio
- MP3 (`.mp3`)
- AAC (`.aac`)
- FLAC (`.flac`)
- OGG/Opus (`.ogg`)
- WAV (`.wav`)
- AIFF (`.aiff`)

### Video
- MP4 (`.mp4`)
- MOV (`.mov`)
- M4V (`.m4v`)
- AVI (`.avi`)
- MKV/WebM (`.mkv`)
- FLV (`.flv`)
- WMV (`.wmv`)

## Quick Start

### Preview Mode (Dry-Run)

**Scan directory and preview what would be changed:**
```bash
python toolbox.py extension-repair /path/to/files --dry-run
```

This shows what changes would be made without actually modifying files.

### Commit Mode (Apply Changes)

**Fix extensions in-place:**
```bash
python toolbox.py extension-repair /path/to/files --commit
```

**Fix extensions and move to output directory:**
```bash
python toolbox.py extension-repair /path/to/files --commit --out /corrected/files
```

### Report-Only Mode

**Generate a report without making any changes:**
```bash
python toolbox.py extension-repair /path/to/files --report --log report.txt
```

### Quarantine Mode

**Move problematic files to quarantine instead of renaming:**
```bash
python toolbox.py extension-repair /path/to/files --quarantine
```

Files are moved to `_quarantine/` subdirectory for manual review.

## Operation Modes

| Mode | Description | Files Modified | Use Case |
|------|-------------|----------------|----------|
| **Dry-run** | Preview only | ❌ No | Test before committing changes |
| **Commit** | Rename files | ✅ Yes | Apply corrections |
| **Report-only** | Log to file | ❌ No | Generate audit reports |
| **Quarantine** | Move to `_quarantine/` | ✅ Yes (moved) | Isolate problematic files |

Combine with `--output` to move corrected files to a separate directory tree (preserves folder structure).

## Advanced Options

### Force Rename Ambiguous Files

By default, files with ambiguous ISO BMFF brands (unknown MP4-like formats) are skipped. To force rename them:

```bash
python toolbox.py extension-repair /path --commit --force-rename
```

⚠️ **Warning**: This may incorrectly classify some files.

### Adjust Thread Count

Control parallelization based on CPU and disk speed:

```bash
python toolbox.py extension-repair /path --commit --threads 16
```

Default is 8 threads. Reduce for HDDs, increase for SSDs.

### Console UI (Split-Pane View)

Launch with live log scrolling in a fixed-height window:

```bash
python toolbox.py extension-repair /path --commit --console-ui
```

Controls:
- Scrolls automatically as new logs appear
- Press `q` to exit viewer
- Only works in real TTY (not redirected output)

### JSON Logging

Generate machine-parseable logs:

```bash
python toolbox.py extension-repair /path --commit --json --log repair.jsonl
```

Each line is a JSON object with timestamp, level, and message.

## Detection Algorithm

### Strict Mode Rules

Extension Repair uses **strict mode** detection:
1. ✅ **Known signature** → Classify and rename
2. ❌ **Unknown signature** → Skip (log as `unknown`)
3. ⚠️ **Ambiguous signature** → Skip by default (override with `--force-rename`)

### Magic-Byte Signatures

The tool reads the first 64 bytes of each file and matches against:

#### Fixed Signatures
Files with unique header bytes (e.g., PNG: `89 50 4E 47 0D 0A 1A 0A`)

#### RIFF Containers
Files starting with `RIFF` followed by subtype:
- `RIFF....AVI ` → AVI
- `RIFF....WAVE` → WAV  
- `RIFF....WEBP` → WEBP

#### ISO BMFF Containers
Files starting with `ftyp` box (MP4 family):
- `ftypisom`, `ftypmp42` → MP4
- `ftypqt  ` → MOV
- `ftypavif` → AVIF
- `ftypheic` → HEIC
- Unknown brands → Ambiguous (skip unless `--force-rename`)

### Handling Ambiguity

**Ambiguous RIFF**: Unknown RIFF subtype → Skip
**Ambiguous ISO**: Unknown `ftyp` brand → Skip (unless `--force-rename`)

This prevents misclassification of proprietary or rare formats.

## Conflict Resolution

When renaming files, Extension Repair handles conflicts automatically:

**Original name:** `document.txt` (actually a JPEG)
**Target name:** `document.jpg`

If `document.jpg` already exists:
- `document_1.jpg`
- `document_2.jpg`
- ... (increments until unique)

Conflict-free renaming ensures no data loss.

## Common Use Cases

### Fixing Downloaded Files

After downloading files without extensions:
```bash
python toolbox.py extension-repair ~/Downloads --commit
```

### Repairing Photo Libraries

Fix extensions in merged photo libraries:
```bash
python toolbox.py extension-repair /photos --commit --threads 12
```

### Quarantine Unknown Files

Isolate files with unknown or ambiguous types:
```bash
python toolbox.py extension-repair /mixed --quarantine
```

Review `_quarantine/` directory manually.

### Audit Before Committing

Generate a full report before making changes:
```bash
python toolbox.py extension-repair /important --report --log audit.txt
```

Review `audit.txt`, then commit if satisfied:
```bash
python toolbox.py extension-repair /important --commit
```

## Diagnostics

The tool tracks detailed statistics during operation:

```
=== Extension Repair Statistics ===
Files scanned: 1523
Correct extensions: 1401
Renamed: 98
Skipped (unknown): 15
Skipped (ambiguous RIFF): 2
Skipped (ambiguous ISO): 4
Zero-byte files: 3
Unreadable: 0
Permission denied: 0
```

**Explanation:**
- **Correct extensions**: Files already have the right extension
- **Renamed**: Files successfully corrected
- **Unknown**: No matching magic-byte signature
- **Ambiguous**: Known container but unknown subtype/brand
- **Zero-byte**: Empty files (cannot detect type)
- **Unreadable**: Permission or I/O errors

## Configuration

Settings are stored in `config/extension_repair.json`:

```json
{
  "default_dry_run": true,
  "default_threads": 8,
  "skip_ambiguous_iso": true,
  "quarantine_dir_name": "_quarantine",
  "in_place": true
}
```

**Key settings:**
- `default_dry_run`: Always preview first (safety)
- `skip_ambiguous_iso`: Skip unknown MP4-like formats
- `in_place`: Rename files in original location (vs. output directory)

## GUI Mode

Launch the graphical interface:
```bash
python toolbox.py
# Select "Extension Repair" from the menu
```

The GUI provides:
- Directory picker
- Mode selection (dry-run, commit, quarantine)
- Live progress bar
- Scrollable log output
- Statistics summary

## Troubleshooting

### False Negatives

**Problem:** Some files not detected

**Causes:**
- Proprietary format not in signature database
- Corrupted file headers
- File is encrypted or compressed

**Solution:** 
- Check file with `file` command: `file -b suspicious.dat`
- Add signature to `magic_signatures.py` if it's a known format
- Use `--force-rename` for ambiguous formats (risky)

### False Positives

**Problem:** File classified incorrectly

**Cause:** Signature collision (very rare with proper magic-byte databases)

**Solution:**
- Review with `hexdump -C file.ext | head`
- Verify with external tool: `file file.ext`
- Report issue with hex dump for signature database update

### Permission Denied

**Problem:** Cannot rename files

**Solutions:**
- Check ownership: `ls -la /path/to/file`
- Run with appropriate privileges
- Use `--output` mode to copy instead of rename
- Check filesystem is writable (not read-only mount)

### Files Not Renamed

**Problem:** Dry-run mode is active

**Solution:** Add `--commit` flag to actually apply changes

**Problem:** Files already have correct extension

**Solution:** Normal behavior - tool skips files that don't need correction

## Architecture

### Module Overview

| Module | Purpose |
|--------|---------|
| `tool.py` | CLI entry point and mode routing |
| `toolbox/webui.py` | Browser-based GUI launcher (shared across tools) |
| `tui.py` | Curses-based console UI |
| `detector.py` | Magic-byte signature matching |
| `magic_signatures.py` | Signature database (JPEG, PNG, MP4, etc.) |
| `worker.py` | Multi-threaded file processing |
| `utils.py` | File operations and path handling |
| `diagnostics.py` | Statistics tracking |
| `config.py` | Settings persistence |
| `logger.py` | Log file management |

### Data Flow

```
1. Scanner → Collect file paths (chunked iteration)
2. Worker → Process files in parallel (ThreadPoolExecutor)
   a. Read first 64 bytes
   b. Match against magic signatures
   c. Detect file type (strict mode)
   d. Build new filename
3. Rename/Move → Safe file operations with conflict resolution
4. Logger → Record all actions (text or JSON)
5. Diagnostics → Aggregate statistics
```

### Threading Model

The worker uses `ThreadPoolExecutor` for I/O-bound operations:
- **File reading**: Parallel header reads (I/O bound)
- **Type detection**: CPU-light (byte comparison)
- **File renaming**: Sequential (filesystem limitation)

Threading is optimal here because:
- File I/O releases the GIL
- Type detection is fast (no heavy computation)
- Shared state (logger, stats) is simple with threads

## Extending Signature Database

To add support for new file types, edit `magic_signatures.py`:

```python
# Add to MAGIC_SIGNATURES list
MAGIC_SIGNATURES = [
    # ... existing entries ...
    
    # My Custom Format
    (b"\x4D\x59\x46\x4D\x54", 0, "myfmt"),  # "MYFMT" at offset 0
]
```

Or for ISO BMFF containers:
```python
ISO_BRANDS = {
    # ... existing entries ...
    b"mybr": "myext",  # ftypmybr → .myext
}
```

Format: `(signature_bytes, offset, canonical_extension)`

## Related Tools

- **HashDB**: Verify file integrity using checksums
- **Undo Transfer**: Restore files to original locations

---

**Back to:** [Deer Toolbox Main Documentation](../README.md)
