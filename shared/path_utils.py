"""
shared/path_utils.py
--------------------

Universal path manipulation utilities for cross-platform file operations.

Features:
- Conflict-free renaming with automatic numbering
- Extension parsing and manipulation
- Directory creation
- Path normalization
- Safe file operations
"""

import os
import shutil


def get_extension(path):
    """
    Returns the lowercase extension without the dot.
    
    Example:
        get_extension('file.JPG') -> 'jpg'
        get_extension('archive.tar.gz') -> 'gz'
    """
    _, ext = os.path.splitext(path)
    return ext[1:].lower()


def ensure_directory(path):
    """
    Ensure the directory for a file exists.
    Creates parent directories as needed.
    
    Args:
        path: File path (directory will be extracted)
    """
    folder = os.path.dirname(path)
    if folder and not os.path.exists(folder):
        os.makedirs(folder, exist_ok=True)


def normalize_path(path):
    """
    Normalize path separators and strip whitespace.
    """
    return os.path.normpath(path.strip())


def build_new_name(base_dir, original_name, new_ext):
    """
    Build a new filename with the given extension inside base_dir.
    Automatically resolves conflicts with _1, _2, etc.

    Example:
        base_dir = '/output'
        original_name = 'photo.jpg'
        new_ext = 'png'

        Returns:
        - /output/photo.png (if doesn't exist)
        - /output/photo_1.png (if photo.png exists)
        - /output/photo_2.png (if photo_1.png exists)
        ...
    """
    name, _old_ext = os.path.splitext(original_name)

    candidate = os.path.join(base_dir, f"{name}.{new_ext}")
    if not os.path.exists(candidate):
        return candidate

    counter = 1
    while True:
        candidate = os.path.join(base_dir, f"{name}_{counter}.{new_ext}")
        if not os.path.exists(candidate):
            return candidate
        counter += 1


def next_nonconflicting_path(base_path):
    """
    Given a target path (which may already exist), return a path that does NOT
    exist by appending _1, _2, ... before the extension.

    Example:
        /dir/photo.png exists
        -> /dir/photo_1.png
        -> /dir/photo_2.png
        ...
    """
    dir_name, base = os.path.split(base_path)
    name, ext = os.path.splitext(base)

    candidate = base_path
    if not os.path.exists(candidate):
        return candidate

    counter = 1
    while True:
        candidate = os.path.join(dir_name, f"{name}_{counter}{ext}")
        if not os.path.exists(candidate):
            return candidate
        counter += 1


def safe_rename(old_path, new_path):
    """
    Attempt to rename a file safely.

    Behavior:
        - If new_path exists, automatically choose a non-conflicting variant
          by appending _1, _2, etc.
        - Never silently overwrite an existing file
        - Falls back to shutil.move for cross-device moves

    Returns:
        ("ok", final_target_path) on success
        ("permission", None) if permission denied
        ("unicode", None) if unicode error
        ("error", exception) for other errors
    """
    try:
        target = next_nonconflicting_path(new_path)
        try:
            os.rename(old_path, target)
        except OSError as e:
            # Handle cross-device link error (errno 18 on Unix, various on Windows)
            if e.errno == 18 or "cross-device" in str(e).lower():
                shutil.move(old_path, target)
            else:
                raise
        return "ok", target

    except PermissionError:
        return "permission", None

    except UnicodeEncodeError:
        return "unicode", None

    except Exception as e:  # pylint: disable=broad-exception-caught
        return "error", e


def is_zero_byte(path):
    """
    Check if a file is zero bytes.
    
    Returns:
        True if file size is 0, False otherwise
    """
    try:
        return os.path.getsize(path) == 0
    except Exception:  # pylint: disable=broad-exception-caught
        return False
