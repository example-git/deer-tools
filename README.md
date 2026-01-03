# 🦌 Deer Toolbox

**Deer Toolbox** is an extensible Python-based file management toolkit designed for system administrators, power users, and developers who need robust command-line tools with optional GUI interfaces.

The toolbox framework automatically discovers and integrates tools from subdirectories, providing:

- 🖥️ **Unified CLI interface** with argument parsing and help documentation
- 🎨 **Modern TUI** using Rich and Questionary (cross-platform terminal UI)
- 🌐 **Web-based GUI** using Flask (accessible via browser)
- 🪟 **Native desktop wrapper** using pywebview (Electron-like experience)
- 📊 **Shared utilities** for parallel processing, directory scanning, and progress tracking

## Included Tools

### 🔒 HashDB

Comprehensive file integrity management system. Scan directories, compute cryptographic hashes (MD5/SHA-256), store records in SQLite, verify file integrity, deduplicate files, and export reports.

[→ View HashDB Documentation](plugins/hashdb/README.md)

### 📁 Extension Repair

Magic-byte file type detector with automated extension correction. Uses strict signature matching to identify file types and safely rename files with incorrect extensions.

[→ View Extension Repair Documentation](plugins/extension_repair/README.md)

### ↩️ Undo Transfer

Recovery tool for restoring files from flattened directory structures. Parses transfer logs and matches files by hash to rebuild original folder hierarchies.

[→ View Undo Transfer Documentation](plugins/undo_transfer/README.md)

---

## Quick Start

### Installation

**Requirements:**

- Python 3.8 or later
- Core CLI/tool logic runs on the Python standard library

**Optional dependencies for enhanced UIs:**

```bash
# Install all optional dependencies
pip install -r requirements.txt

# Or install individually:
pip install rich questionary  # Modern TUI
pip install flask              # Web GUI
pip install pywebview          # Desktop wrapper
pip install markdown           # Enhanced markdown rendering
```

### Running Deer Toolbox

**Interactive TUI (Terminal UI):**

```bash
python toolbox.py
```

You can also force the menu explicitly:

```bash
python toolbox.py menu
```

**Web GUI:**

```bash
python toolbox.py gui
```

Note: `gui` prefers the desktop wrapper (pywebview) if available, otherwise it falls back to the browser-based web UI.

**Desktop GUI:**

```bash
python toolbox.py desktop
```

**Command-line help:**

```bash
python toolbox.py --help
python toolbox.py hashdb --help
```

---

## Architecture

Deer Toolbox uses a plugin-style architecture where each tool is a self-contained package under `plugins/`:

```text
plugins/tool_name/
├── tool.py           # Main entry point implementing standard interface
├── metadata.json     # Tool metadata (name, description, version)
├── README.md         # Tool-specific documentation
└── ...               # Supporting modules for business logic
```

### Standard Tool Interface

Each tool must implement in `tool.py`:

- `register_cli(subparsers)` - Register CLI commands with argparse
- `run(mode='cli', **kwargs)` - Execute the tool in specified mode

### Shared Utilities

The `shared/` directory provides common functionality:

| Module | Purpose |
| ------ | ------- |
| `worker.py` | Base worker class for threaded operations with progress tracking |
| `scanner.py` | Efficient directory traversal with chunked iteration |
| `task_runner.py` | Subprocess management with log streaming and killable handles |
| `log_watcher.py` | Real-time log file monitoring on background threads |

These utilities use `ThreadPoolExecutor` for parallelization, which is optimal for the I/O-bound and GIL-releasing operations (like file hashing) that dominate these workloads.

---

## Usage Examples

### HashDB Examples

**Scan a directory and compute SHA-256 hashes (default):**

```bash
python toolbox.py hashdb scan /path/to/files
```

**Verify file integrity:**

```bash
python toolbox.py hashdb verify /path/to/.hashdb.sqlite
```

**Find and remove duplicate files:**

```bash
python toolbox.py hashdb dedupe /path/to/.hashdb.sqlite --hash sha256
```

### Extension Repair Examples

**Preview file type corrections (dry-run):**

```bash
python toolbox.py extension-repair /path/to/files --mode cli --dry-run
```

**Apply corrections in-place:**

```bash
python toolbox.py extension-repair /path/to/files --mode cli --commit
```

**Move corrected files to output directory:**

```bash
python toolbox.py extension-repair /path/to/files --mode cli --commit --out /output/dir
```

### Undo Transfer Examples

**Restore files from transfer log:**

```bash
python toolbox.py undo-transfer --mode cli --log transfer.log --temp /temp/dir --restore /output --commit
```

---

## Creating Custom Tools

To add a new tool to Deer Toolbox:

1. **Create a subdirectory** with your tool name:

   ```bash
    mkdir -p plugins/my_tool
   ```

2. **Create `metadata.json`:**

   ```json
   {
     "id": "my_tool",
     "name": "My Tool",
     "version": "1.0",
     "description": "What my tool does",
     "category": "Utilities",
     "supports_gui": true,
     "supports_cli": true
   }
   ```

3. **Create `tool.py` implementing the standard interface:**

   ```python
   def register_cli(subparsers):
       """Register CLI commands with argparse."""
       parser = subparsers.add_parser('my-tool', help='My tool description')
       parser.add_argument('--option', help='An option')
       parser.set_defaults(func=lambda args: run('cli', args=args))
   
   def run(mode='cli', **kwargs):
       """Execute the tool."""
       if mode == 'cli':
           # CLI implementation
           pass
       elif mode == 'gui':
           # GUI implementation
           pass
   ```

4. **Add tool-specific documentation:**
   Create `README.md` with usage examples and configuration details.

The toolbox will automatically discover and integrate your tool on next launch.

---

## Configuration

Some tools persist settings under `config/` (created/updated on first run):

- `config/extension_repair.json`
- `config/undo_transfer.json`

For automation, use `-y/--yes` (non-interactive) and pass explicit CLI flags instead of relying on saved configuration.

---

## Performance Characteristics

Deer Toolbox uses **threading** (via `ThreadPoolExecutor`) for parallelization, which is typically a good fit for:

✅ **I/O-bound operations** (file scanning, reading, writing)
✅ **GIL-releasing operations** (cryptographic hashing via `hashlib`)
✅ **Lightweight coordination** (shared state, queues, progress tracking)

In practice, performance depends on your storage (SSD vs HDD), file sizes, and CPU. The GIL is commonly released during:

- File I/O operations
- `hashlib` hash computation (MD5, SHA-256)
- Directory traversal via `os.walk`

---

## Troubleshooting

### GUI not available

If GUI modes fail, ensure you have the required dependencies:

```bash
pip install rich questionary flask pywebview
```

For TUI-only environments (no display server), use CLI mode:

```bash
python toolbox.py hashdb scan /path --hash sha256
```

### Console UI doesn't show

The `--console-ui` flag only works in real terminals (TTY). It won't activate when:

- Output is redirected to a file
- Running in non-interactive environments (cron, CI/CD)

### Permission errors

If tools fail with permission errors:

- Check file/directory permissions: `ls -la /path`
- Run with appropriate privileges if needed
- Use `--dry-run` mode to preview changes first

---

## Environment Checks

Run the built-in doctor command to validate your environment:

```bash
python toolbox.py doctor
```

This checks:

- Python version (3.8+ recommended)
- Core module imports
- Optional GUI dependencies
- Tool discovery and registration

---

## Project Structure

```text
deer-toolbox/
├── toolbox.py              # Main launcher and tool discovery
├── toolbox/                # UI modules
│   ├── tool_parser.py      # Shared CLI parsing utilities
│   ├── textui.py           # Modern TUI (rich + questionary)
│   ├── tui.py              # Legacy curses TUI (fallback)
│   ├── webui.py            # Flask web interface
│   └── desktopui.py        # pywebview desktop wrapper
├── README.md               # This file
├── config/                 # Persistent tool configurations
│   ├── extension_repair.json
│   └── undo_transfer.json
├── shared/                 # Shared utilities
│   ├── worker.py           # Base worker with progress tracking
│   ├── scanner.py          # Directory traversal utilities
│   ├── task_runner.py      # Subprocess management
│   └── log_watcher.py      # Log file monitoring
└── plugins/                # Tool plugins
    ├── hashdb/             # HashDB tool
    │   ├── tool.py
    │   ├── metadata.json
    │   ├── README.md
    │   └── ...
    ├── extension_repair/   # Extension Repair tool
    │   ├── tool.py
    │   ├── metadata.json
    │   ├── README.md
    │   └── ...
    └── undo_transfer/      # Undo Transfer tool
        ├── tool.py
        ├── metadata.json
        ├── README.md
        └── ...
```

---

## License

This project is provided as-is for educational and utility purposes.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for code guidelines and development notes.

To contribute a new tool:

1. Follow the "Creating Custom Tools" guide above
2. Ensure your tool includes comprehensive tests
3. Add documentation to `plugins/tool_name/README.md`
4. Submit a pull request with your changes

---

## Python Version

Deer Toolbox is tested with Python 3.8+ on macOS, Linux, and Windows. All tools avoid non-stdlib dependencies for core functionality, with optional enhancements available via pip.
