"""
shared/scanner.py
-----------------

Universal directory scanning utilities with chunked iteration.
Memory-efficient for large directories.

Usage:
    from shared import iter_files, collect_files_chunked

    # Simple iteration
    for path in iter_files("/some/directory"):
        process(path)

    # Chunked with callback
    files = collect_files_chunked(
        "/some/directory",
        chunk_size=500,
        callback=lambda chunk, total: print(f"Found {total} files")
    )

    # Generator of chunks
    for chunk in iter_files_chunked("/some/directory"):
        process_batch(chunk)
"""

import os
from pathlib import Path
from typing import List, Iterator, Optional, Callable, Union

# ------------------------------------------------------------
# Default chunk size for directory scanning
# ------------------------------------------------------------
DEFAULT_CHUNK_SIZE = 500


# ------------------------------------------------------------
# Core Generator - yields paths lazily
# ------------------------------------------------------------
def iter_files(
    root: Union[str, Path],
    as_path: bool = True,
    follow_symlinks: bool = False,
) -> Iterator[Union[Path, str]]:
    """
    Generator that yields file paths lazily.
    More memory-efficient than collecting all paths upfront.
    
    Args:
        root: Directory to scan
        as_path: If True, yield Path objects; if False, yield strings
        follow_symlinks: If True, follow symbolic links (default False)
        
    Yields:
        File paths (Path objects or strings based on as_path)
    """
    root = str(root)
    
    for dirpath, _, filenames in os.walk(root, followlinks=follow_symlinks):
        for f in filenames:
            if as_path:
                yield Path(dirpath) / f
            else:
                yield os.path.join(dirpath, f)


# ------------------------------------------------------------
# Chunked Generator - yields batches of paths
# ------------------------------------------------------------
def iter_files_chunked(
    root: Union[str, Path],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    as_path: bool = True,
    follow_symlinks: bool = False,
) -> Iterator[List[Union[Path, str]]]:
    """
    Generator that yields chunks of file paths.
    
    Args:
        root: Directory to scan
        chunk_size: Number of files per chunk
        as_path: If True, yield Path objects; if False, yield strings
        follow_symlinks: If True, follow symbolic links
        
    Yields:
        Lists of file paths, each up to chunk_size items
    """
    chunk = []
    
    for path in iter_files(root, as_path=as_path, follow_symlinks=follow_symlinks):
        chunk.append(path)
        
        if len(chunk) >= chunk_size:
            yield chunk
            chunk = []
    
    # Final partial chunk
    if chunk:
        yield chunk


# ------------------------------------------------------------
# Collect All Files (with optional chunked callback)
# ------------------------------------------------------------
def collect_files(
    root: Union[str, Path],
    as_path: bool = True,
    follow_symlinks: bool = False,
) -> List[Union[Path, str]]:
    """
    Recursively collect all files under root.
    
    Note: For large directories, prefer iter_files() or collect_files_chunked().
    
    Args:
        root: Directory to scan
        as_path: If True, return Path objects; if False, return strings
        follow_symlinks: If True, follow symbolic links
        
    Returns:
        List of all file paths
    """
    return list(iter_files(root, as_path=as_path, follow_symlinks=follow_symlinks))


def collect_files_chunked(
    root: Union[str, Path],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    callback: Optional[Callable[[List[Union[Path, str]], int], None]] = None,
    as_path: bool = True,
    follow_symlinks: bool = False,
) -> List[Union[Path, str]]:
    """
    Collect files in chunks, optionally calling callback for each chunk.
    
    Args:
        root: Directory to scan
        chunk_size: Number of files per chunk
        callback: Optional function(chunk_list, total_so_far) called per chunk
        as_path: If True, collect Path objects; if False, collect strings
        follow_symlinks: If True, follow symbolic links
        
    Returns:
        Complete list of all files (built incrementally)
    """
    all_files = []
    
    for chunk in iter_files_chunked(root, chunk_size, as_path=as_path, follow_symlinks=follow_symlinks):
        all_files.extend(chunk)
        if callback:
            callback(chunk, len(all_files))
    
    return all_files


# ------------------------------------------------------------
# Filtered Scanning
# ------------------------------------------------------------
def iter_files_filtered(
    root: Union[str, Path],
    extensions: Optional[List[str]] = None,
    exclude_dirs: Optional[List[str]] = None,
    min_size: Optional[int] = None,
    max_size: Optional[int] = None,
    as_path: bool = True,
    follow_symlinks: bool = False,
) -> Iterator[Union[Path, str]]:
    """
    Generator that yields file paths with filtering options.
    
    Args:
        root: Directory to scan
        extensions: List of extensions to include (e.g., ['.jpg', '.png'])
        exclude_dirs: Directory names to skip (e.g., ['__pycache__', '.git'])
        min_size: Minimum file size in bytes
        max_size: Maximum file size in bytes
        as_path: If True, yield Path objects; if False, yield strings
        follow_symlinks: If True, follow symbolic links
        
    Yields:
        Filtered file paths
    """
    root = str(root)
    exclude_dirs = set(exclude_dirs or [])
    extensions = set(ext.lower() if ext.startswith('.') else f'.{ext.lower()}' 
                     for ext in (extensions or []))
    
    for dirpath, dirnames, filenames in os.walk(root, followlinks=follow_symlinks):
        # Modify dirnames in-place to skip excluded directories
        if exclude_dirs:
            dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
        
        for f in filenames:
            # Extension filter
            if extensions:
                ext = os.path.splitext(f)[1].lower()
                if ext not in extensions:
                    continue
            
            full_path = os.path.join(dirpath, f)
            
            # Size filters
            if min_size is not None or max_size is not None:
                try:
                    size = os.path.getsize(full_path)
                    if min_size is not None and size < min_size:
                        continue
                    if max_size is not None and size > max_size:
                        continue
                except OSError:
                    continue
            
            if as_path:
                yield Path(full_path)
            else:
                yield full_path


def collect_files_filtered(
    root: Union[str, Path],
    extensions: Optional[List[str]] = None,
    exclude_dirs: Optional[List[str]] = None,
    min_size: Optional[int] = None,
    max_size: Optional[int] = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    callback: Optional[Callable[[List[Union[Path, str]], int], None]] = None,
    as_path: bool = True,
    follow_symlinks: bool = False,
) -> List[Union[Path, str]]:
    """
    Collect files with filtering, optionally in chunks with callback.
    
    Args:
        root: Directory to scan
        extensions: List of extensions to include
        exclude_dirs: Directory names to skip
        min_size: Minimum file size in bytes
        max_size: Maximum file size in bytes
        chunk_size: Number of files per callback chunk
        callback: Optional function(chunk_list, total_so_far) called per chunk
        as_path: If True, collect Path objects; if False, collect strings
        follow_symlinks: If True, follow symbolic links
        
    Returns:
        List of filtered file paths
    """
    all_files = []
    chunk = []
    
    for path in iter_files_filtered(
        root,
        extensions=extensions,
        exclude_dirs=exclude_dirs,
        min_size=min_size,
        max_size=max_size,
        as_path=as_path,
        follow_symlinks=follow_symlinks,
    ):
        chunk.append(path)
        
        if len(chunk) >= chunk_size:
            all_files.extend(chunk)
            if callback:
                callback(chunk, len(all_files))
            chunk = []
    
    # Final partial chunk
    if chunk:
        all_files.extend(chunk)
        if callback:
            callback(chunk, len(all_files))
    
    return all_files


# ------------------------------------------------------------
# Count files (without collecting)
# ------------------------------------------------------------
def count_files(
    root: Union[str, Path],
    follow_symlinks: bool = False,
) -> int:
    """
    Count files without storing paths in memory.
    
    Args:
        root: Directory to scan
        follow_symlinks: If True, follow symbolic links
        
    Returns:
        Total file count
    """
    count = 0
    for _ in iter_files(root, as_path=False, follow_symlinks=follow_symlinks):
        count += 1
    return count
