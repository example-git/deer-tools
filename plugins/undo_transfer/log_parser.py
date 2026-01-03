"""
log_parser.py
-------------

Parses the original transfer log and extracts entries relevant to the
Undo Transfer Tool.

Each log line is expected to look like:

    r"D:/Pictures/LPictures\\gamingfurry2\\file.jpg | MD5: abcdef..."

This module:
- Normalizes slashes
- Filters by ORIGINAL_ROOT
- Filters by TARGET_SUBFOLDERS (case-insensitive)
- Extracts (original_path, md5_hash) tuples
"""

from .utils import load_log_entries as _load_log_entries


def load_log_entries(log_path, target_subfolders, original_root):
    """
    Compatibility wrapper.

    Historically this module returned list[(original_path, md5_hash)]. The
    cross-platform implementation now lives in undo_transfer.utils and returns
    a richer tuple including the relative path.

    This wrapper preserves the original return shape.
    """
    entries = _load_log_entries(log_path, target_subfolders, original_root)
    return [(original_path_str, hash_value) for (original_path_str, hash_value, _rel, _algo) in entries]