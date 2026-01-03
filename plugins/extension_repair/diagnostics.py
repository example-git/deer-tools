"""
diagnostics.py
--------------

Handles diagnostic-level logic for the Extension Repair Tool.

Features:
- Three diagnostic levels (1 = Standard, 2 = Deep, 3 = Forensic)
- Categorized skip-reason tracking
- Summary generation
- Forensic hex dumps for unknown files
- Output to both console and log

This module does NOT perform detection or renaming.
It only organizes and reports results.
"""

import os
import binascii


# ------------------------------------------------------------
# Skip reason categories
# ------------------------------------------------------------
def init_stats():
    """
    Returns a dictionary of categorized skip-reason lists.
    Each list contains file paths or (path, details).
    """
    return {
        "unknown": [],
        "too_small": [],
        "unreadable": [],
        "correct_ext": [],
        "ambiguous_riff": [],
        "ambiguous_iso": [],
        "rename_conflict": [],
        "permission_denied": [],
        "unicode_issue": [],
        "zero_byte": [],
        "truncated": [],
        "malformed_zip": [],
        "malformed_rar": [],
        "malformed_7z": [],
        "other": [],
    }


# ------------------------------------------------------------
# Helper: write to console + log
# ------------------------------------------------------------
def out(msg, logger):
    if not getattr(logger, "suppress_console", False):
        print(msg)
    logger.log(msg)


# ------------------------------------------------------------
# Diagnostic Level 1 (Standard)
# ------------------------------------------------------------
def summary_level_1(stats, logger):
    out("\n=== SUMMARY (Standard Diagnostics) ===", logger)

    def count(key):
        return len(stats[key])

    out(f"Unknown format: {count('unknown')}", logger)
    out(f"Already correct extension: {count('correct_ext')}", logger)
    out(f"Unreadable files: {count('unreadable')}", logger)
    out(f"Too small to detect: {count('too_small')}", logger)
    out(f"Ambiguous RIFF: {count('ambiguous_riff')}", logger)
    out(f"Ambiguous ISO BMFF: {count('ambiguous_iso')}", logger)
    out(f"Rename conflicts: {count('rename_conflict')}", logger)
    out(f"Permission denied: {count('permission_denied')}", logger)
    out(f"Unicode issues: {count('unicode_issue')}", logger)
    out(f"Other: {count('other')}", logger)


# ------------------------------------------------------------
# Diagnostic Level 2 (Deep)
# ------------------------------------------------------------
def summary_level_2(stats, logger):
    summary_level_1(stats, logger)

    out("\n=== DEEP DIAGNOSTICS ===", logger)

    # Unknown breakdown
    if stats["unknown"]:
        out("\nUnknown Format Breakdown:", logger)
        zero = [p for p in stats["unknown"] if os.path.getsize(p) == 0]
        out(f"  Zero-byte files: {len(zero)}", logger)

        # Header-family breakdown
        riff_like = []
        iso_like = []
        jpeg_like = []
        zip_like = []
        other = []

        for path in stats["unknown"]:
            try:
                with open(path, "rb") as f:
                    h = f.read(16)
            except Exception:
                continue

            if h.startswith(b"RIFF"):
                riff_like.append(path)
            elif h[4:8] == b"ftyp":
                iso_like.append(path)
            elif h.startswith(b"\xFF\xD8"):
                jpeg_like.append(path)
            elif h.startswith(b"PK\x03\x04"):
                zip_like.append(path)
            else:
                other.append(path)

        out(f"  RIFF-like unknowns: {len(riff_like)}", logger)
        out(f"  ISO BMFF-like unknowns: {len(iso_like)}", logger)
        out(f"  JPEG-like unknowns: {len(jpeg_like)}", logger)
        out(f"  ZIP-like unknowns: {len(zip_like)}", logger)
        out(f"  Completely unrecognized: {len(other)}", logger)

    # Ambiguous ISO BMFF details
    if stats["ambiguous_iso"]:
        out("\nAmbiguous ISO BMFF Files:", logger)
        for path in stats["ambiguous_iso"]:
            try:
                with open(path, "rb") as f:
                    h = f.read(12)
                brand = h[8:12]
                out(f"  {path} (brand={brand})", logger)
            except Exception:
                out(f"  {path} (unreadable)", logger)


# ------------------------------------------------------------
# Diagnostic Level 3 (Forensic)
# ------------------------------------------------------------
def summary_level_3(stats, logger):
    summary_level_2(stats, logger)

    out("\n=== FORENSIC MODE ===", logger)

    # Hex dump of unknowns
    if stats["unknown"]:
        out("\nHex Signatures of Unknown Files:", logger)
        for path in stats["unknown"]:
            try:
                with open(path, "rb") as f:
                    h = f.read(16)
                hexstr = binascii.hexlify(h).decode("ascii")
                out(f"  {path}: {hexstr}", logger)
            except Exception:
                out(f"  {path}: <unreadable>", logger)

    # Rename conflicts
    if stats["rename_conflict"]:
        out("\nRename Conflicts:", logger)
        for path, new_path in stats["rename_conflict"]:
            out(f"  {path} -> {new_path}", logger)

    # Unicode issues
    if stats["unicode_issue"]:
        out("\nUnicode Path Issues:", logger)
        for path in stats["unicode_issue"]:
            out(f"  {path}", logger)

    # Truncated signatures
    if stats["truncated"]:
        out("\nTruncated Signature Files:", logger)
        for path in stats["truncated"]:
            out(f"  {path}", logger)


# ------------------------------------------------------------
# Main summary dispatcher
# ------------------------------------------------------------
def generate_summary(stats, diagnostic_level, logger):
    """
    Dispatches to the appropriate summary generator.
    """
    if diagnostic_level == 1:
        summary_level_1(stats, logger)
    elif diagnostic_level == 2:
        summary_level_2(stats, logger)
    else:
        summary_level_3(stats, logger)