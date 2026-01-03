"""
detector.py
-----------

Strict-mode file type detection logic.

Handles:
- Reading magic bytes
- Matching fixed signatures
- RIFF container parsing (AVI, WAV, WEBP)
- ISO BMFF parsing (MP4, MOV, M4V, AVIF, HEIC, etc.)
- Ambiguity detection for unknown ISO BMFF brands
- Returning canonical extensions or skip reasons

Strict Mode Rules:
- Only classify when magic bytes match a known signature.
- Unknown or ambiguous formats must be skipped.
- No extension-based heuristics.
"""

import os

from .magic_signatures import (
    SIGNATURE_LENGTH,
    MAGIC_SIGNATURES,
    RIFF_TYPES,
    ISO_BRANDS,
)


# ------------------------------------------------------------
# Helper: read header bytes
# ------------------------------------------------------------
def read_header(path, length=SIGNATURE_LENGTH):
    try:
        with open(path, "rb") as f:
            return f.read(length)
    except Exception:
        return None


# ------------------------------------------------------------
# RIFF container detection (AVI, WAV, WEBP)
# ------------------------------------------------------------
def detect_riff(header):
    """
    RIFF files start with:
        52 49 46 46  (RIFF)
    Then at offset 8, the subtype:
        AVI  -> AVI
        WAVE -> WAV
        WEBP -> WEBP
    """
    if not header.startswith(b"RIFF"):
        return None

    if len(header) < 12:
        return "ambiguous_riff"

    subtype = header[8:12]
    return RIFF_TYPES.get(subtype, "ambiguous_riff")


# ------------------------------------------------------------
# ISO BMFF detection (MP4, MOV, M4V, AVIF, HEIC, etc.)
# ------------------------------------------------------------
def detect_iso_bmff(header):
    """
    ISO BMFF files begin with:
        00 00 00 ?? 66 74 79 70  ('ftyp')
    Brand is at offset 8:
        ftypisom -> mp4
        ftypmp42 -> mp4
        ftypavif -> avif
        ftypheic -> heic
        ftypqt   -> mov

    Strict Mode:
        - Only classify known brands.
        - Unknown brands are ambiguous.
    """
    if len(header) < 12:
        return None

    # Check for 'ftyp' at offset 4
    if header[4:8] != b"ftyp":
        return None

    brand = header[8:12]

    # Known brand?
    if brand in ISO_BRANDS:
        return ISO_BRANDS[brand]

    # Unknown brand → ambiguous ISO BMFF
    return "ambiguous_iso"


# ------------------------------------------------------------
# Fixed magic-byte signature detection
# ------------------------------------------------------------
def detect_fixed_magic(header):
    """
    Check against all fixed signatures (strict).
    """
    if header is None:
        return None

    for sig, offset, ext in MAGIC_SIGNATURES:
        if header[offset:offset + len(sig)] == sig:
            return ext

    return None


# ------------------------------------------------------------
# Main detection function
# ------------------------------------------------------------
def detect_file_type(path):
    """
    Returns:
        (ext, reason)

    ext:
        - canonical extension (e.g., 'jpg', 'mp4')
        - None if unknown or ambiguous

    reason:
        - None if ext is known
        - "unknown"
        - "too_small"
        - "unreadable"
        - "ambiguous_riff"
        - "ambiguous_iso"
    """
    header = read_header(path)

    if header is None:
        return None, "unreadable"

    if len(header) < 4:
        return None, "too_small"

    # 1. Fixed signatures
    ext = detect_fixed_magic(header)
    if ext:
        return ext, None

    # 2. RIFF container
    if header.startswith(b"RIFF"):
        ext = detect_riff(header)
        if ext == "ambiguous_riff":
            return None, "ambiguous_riff"
        return ext, None

    # 3. ISO BMFF container
    iso = detect_iso_bmff(header)
    if iso == "ambiguous_iso":
        return None, "ambiguous_iso"
    if iso:
        return iso, None

    # 4. Unknown
    return None, "unknown"