"""
magic_signatures.py
-------------------

Strict-mode magic-byte signatures for the Extension Repair Tool.

Defines:
- MAGIC_SIGNATURES: exact byte signatures for formats with fixed headers
- ISO_BRANDS: known ISO BMFF brands (MP4, MOV, M4V, AVIF, HEIC, etc.)
- RIFF_TYPES: RIFF subtypes (AVI, WAV, WEBP)
- SIGNATURE_LENGTH: how many bytes to read for detection

Strict Mode Rules:
- Only classify a file if its magic bytes match a known signature.
- No guessing, no extension-based heuristics.
- Unknown or ambiguous formats must be skipped and logged.
"""

# How many bytes to read from each file for detection
SIGNATURE_LENGTH = 64


# ------------------------------------------------------------
# 1. FIXED MAGIC-BYTE SIGNATURES (strict)
# ------------------------------------------------------------
# Format:
#   (signature_bytes, offset, canonical_extension)
#
# These are formats with stable, unambiguous headers.
MAGIC_SIGNATURES = [

    # ============================
    # IMAGE FORMATS
    # ============================

    # JPEG
    (b"\xFF\xD8\xFF", 0, "jpg"),

    # PNG
    (b"\x89PNG\r\n\x1a\n", 0, "png"),

    # GIF
    (b"GIF87a", 0, "gif"),
    (b"GIF89a", 0, "gif"),

    # BMP
    (b"BM", 0, "bmp"),

    # TIFF (little endian)
    (b"\x49\x49\x2A\x00", 0, "tif"),

    # TIFF (big endian)
    (b"\x4D\x4D\x00\x2A", 0, "tif"),

    # JPEG2000 (JP2)
    (b"\x00\x00\x00\x0CjP  ", 0, "jp2"),

    # ICO
    (b"\x00\x00\x01\x00", 0, "ico"),


    # ============================
    # ARCHIVE FORMATS
    # ============================

    # ZIP / DOCX / XLSX / APK / JAR
    (b"PK\x03\x04", 0, "zip"),

    # RAR v1.5–4.0
    (b"Rar!\x1A\x07\x00", 0, "rar"),

    # RAR v5+
    (b"Rar!\x1A\x07\x01\x00", 0, "rar"),

    # 7z
    (b"7z\xBC\xAF\x27\x1C", 0, "7z"),

    # BZ2
    (b"BZh", 0, "bz2"),

    # XZ
    (b"\xFD7zXZ\x00", 0, "xz"),

    # GZIP
    (b"\x1F\x8B\x08", 0, "gz"),


    # ============================
    # AUDIO FORMATS
    # ============================

    # MP3 (ID3)
    (b"ID3", 0, "mp3"),

    # MP3 (frame sync)
    (b"\xFF\xFB", 0, "mp3"),

    # AAC (ADTS)
    (b"\xFF\xF1", 0, "aac"),
    (b"\xFF\xF9", 0, "aac"),

    # FLAC
    (b"fLaC", 0, "flac"),

    # OGG / Opus
    (b"OggS", 0, "ogg"),

    # AIFF
    (b"FORM", 0, "aiff"),


    # ============================
    # VIDEO FORMATS (non-ISO)
    # ============================

    # MKV / WebM
    (b"\x1A\x45\xDF\xA3", 0, "mkv"),

    # FLV
    (b"FLV", 0, "flv"),

    # WMV / ASF
    (b"\x30\x26\xB2\x75\x8E\x66\xCF\x11", 0, "wmv"),
]


# ------------------------------------------------------------
# 2. RIFF CONTAINER TYPES (AVI, WAV, WEBP)
# ------------------------------------------------------------
RIFF_TYPES = {
    b"AVI ": "avi",
    b"WAVE": "wav",
    b"WEBP": "webp",
}


# ------------------------------------------------------------
# 3. ISO BMFF BRANDS (MP4, MOV, M4V, AVIF, HEIC, etc.)
# ------------------------------------------------------------
ISO_BRANDS = {
    # MP4 family
    b"isom": "mp4",
    b"iso2": "mp4",
    b"mp41": "mp4",
    b"mp42": "mp4",
    b"M4V ": "m4v",

    # QuickTime
    b"qt  ": "mov",

    # AVIF
    b"avif": "avif",

    # HEIC / HEIF
    b"heic": "heic",
    b"heix": "heic",
    b"hevc": "heic",
    b"hevx": "heic",
}