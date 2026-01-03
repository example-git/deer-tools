"""
HashDB Toolbox Package
----------------------

This package provides a modular, extensible system for:

- Multi-threaded file hashing (MD5 / SHA-256)
- SQLite-backed hash database management
- Duplicate detection and safe deletion
- Database cleanup and maintenance
- Hash exporting (flat files, chunked, Hydrus-style)
- Reporting and diagnostics
- Browser-based web UI launcher (via toolbox) and CLI interface

Modules:
    db.py           - Database layer (schema, indexes, upserts)
    scanner.py      - Directory traversal + rescan logic
    hasher.py       - Threaded hashing engine
    deduper.py      - Duplicate detection + safe delete
    maintenance.py  - Cleanup (missing files, zero-byte, VACUUM)
    exporter.py     - Hash export utilities
    reporter.py     - Stats + duplicate reports
    cli.py          - Command-line interface
    tool.py         - Toolbox entry point

This file exposes the public API for external tools and integrations.
"""

__all__ = [
    "db",
    "scanner",
    "hasher",
    "deduper",
    "maintenance",
    "exporter",
    "reporter",
    "cli",
    "tool",
]

# Optional version metadata
__version__ = "1.0.0"