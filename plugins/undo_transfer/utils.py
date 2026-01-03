import os
from pathlib import Path, PurePath, PureWindowsPath
from shared.path_utils import ensure_directory


def normalize_log_path(raw_path: str) -> PureWindowsPath:
    """
    Normalize a path from the transfer log (which uses Windows conventions)
    into a PureWindowsPath for consistent parsing regardless of host OS.
    """
    # Log paths may mix / and \; normalize to Windows style for parsing
    return PureWindowsPath(raw_path.replace("/", "\\"))


def get_relative_path(full_path: PureWindowsPath, root: PureWindowsPath) -> PurePath:
    """
    Get the relative portion of full_path under root.
    Returns a PurePath (platform-agnostic parts) or None if not under root.
    """
    try:
        return full_path.relative_to(root)
    except ValueError:
        return None


def load_log_entries(log_path, target_subfolders, original_root):
    r"""
    Parse the original transfer log and extract entries for the target subfolders.

    Each line is expected to look like:
    D:/Pictures/LPictures\gamingfurry2\file.jpg | MD5: abcdef....

    Returns a list of tuples:
        (original_path_str, hash_value, rel_path, hash_type)

    hash_type is "md5" or "sha256".
    """
    entries = []
    normalized_targets = [t.lower() for t in target_subfolders]
    original_root_win = normalize_log_path(original_root)

    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or "|" not in line:
                continue

            original_path_raw, hash_part = line.split("|", 1)
            original_path_win = normalize_log_path(original_path_raw.strip())

            hash_part_clean = hash_part.strip()
            hash_type = None
            hash_value = None

            upper = hash_part_clean.upper()
            if "SHA256:" in upper:
                hash_type = "sha256"
                hash_value = hash_part_clean.split(":", 1)[1].strip()
            elif "MD5:" in upper:
                hash_type = "md5"
                hash_value = hash_part_clean.split(":", 1)[1].strip()
            else:
                # Fallback: guess by hex length
                candidate = hash_part_clean.split()[-1]
                if len(candidate) == 64:
                    hash_type = "sha256"
                    hash_value = candidate
                elif len(candidate) == 32:
                    hash_type = "md5"
                    hash_value = candidate
                else:
                    continue

            # Check if path is under original_root
            rel_path = get_relative_path(original_path_win, original_root_win)
            if rel_path is None:
                continue

            # Check if any target subfolder is in the path
            path_parts_lower = [p.lower() for p in original_path_win.parts]
            if not any(target in path_parts_lower or
                       any(target in part for part in path_parts_lower)
                       for target in normalized_targets):
                continue

            # Store the original Windows path string (for matching/logging)
            # but also store rel_path for cross-platform restore
            entries.append((str(original_path_win), hash_value, rel_path, hash_type))

    return entries