"""
Detect whether a file is binary or text, and detect its encoding.
Falls back gracefully when chardet is not installed.
"""
from __future__ import annotations
import re
import logging

log = logging.getLogger(__name__)

# Null bytes in the first N bytes strongly indicate binary
_SNIFF_BYTES = 8192
_NULL_THRESHOLD = 1   # any null byte → binary
_HIGH_BYTES_RATIO = 0.30  # >30% high bytes → binary


def is_binary(data: bytes) -> bool:
    """Heuristic: return True if data is likely binary content."""
    if not data:
        return False
    # Fast path: known binary magic bytes
    if is_known_binary_format(data):
        return True
    sample = data[:_SNIFF_BYTES]
    # Null bytes → binary
    if b"\x00" in sample:
        return True
    # High ratio of bytes > 0x7F → binary (for non-UTF-8 encodings that's fine,
    # but combined with other signals it suggests binary)
    high = sum(1 for b in sample if b > 0x7F)
    if high / len(sample) > _HIGH_BYTES_RATIO:
        # could be UTF-16 — try decoding
        try:
            sample.decode("utf-16")
            return False
        except UnicodeDecodeError:
            return True
    return False


def detect_encoding(data: bytes) -> str:
    """
    Return the most likely encoding for text data.
    Uses chardet if available, otherwise falls back to heuristics.
    """
    # BOM detection first (most reliable)
    if data[:3] == b"\xef\xbb\xbf":
        return "utf-8-sig"
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return "utf-16"
    if data[:4] in (b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff"):
        return "utf-32"

    try:
        data.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass

    try:
        import chardet
        result = chardet.detect(data[:_SNIFF_BYTES])
        enc = result.get("encoding") or "latin-1"
        conf = result.get("confidence", 0)
        log.debug("chardet detected %s (confidence %.2f)", enc, conf)
        return enc
    except ImportError:
        pass

    # ISO-8859-1 / latin-1 is a safe fallback for C source files
    return "latin-1"


def normalize_line_endings(data: bytes, encoding: str = "utf-8") -> bytes:
    """Convert CRLF → LF in text data."""
    try:
        text = data.decode(encoding, errors="replace")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        return text.encode(encoding, errors="replace")
    except Exception:
        return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


# ── binary magic bytes ────────────────────────────────────────────────────

_ELF_MAGIC   = b"\x7fELF"           # Linux/Unix ELF executable/object
_COFF_MAGIC  = b"\x4d\x5a"          # MZ — Windows PE/COFF executable
_AR_MAGIC    = b"!<arch>\n"          # .a static archive
_PDF_MAGIC   = b"%PDF"               # PDF document
_ZIP_MAGIC   = b"PK\x03\x04"        # ZIP / JAR / WAR / APK
_ZIP_EMPTY   = b"PK\x05\x06"        # empty ZIP
_CLASS_MAGIC = b"\xca\xfe\xba\xbe"  # Java .class file
_MACHO_LE    = b"\xce\xfa\xed\xfe"  # Mach-O 32-bit LE
_MACHO_BE    = b"\xcf\xfa\xed\xfe"  # Mach-O 64-bit LE
_MACHO_FAT   = b"\xca\xfe\xba\xbe"  # Mach-O fat binary (same as .class — checked by extension)
_PNG_MAGIC   = b"\x89PNG"
_GIF_MAGIC   = b"GIF8"
_JPEG_MAGIC  = b"\xff\xd8\xff"


def is_object_or_archive(data: bytes) -> bool:
    """Return True if data looks like a compiled object, archive, or executable."""
    if len(data) < 4:
        return False
    return (
        data[:4] == _ELF_MAGIC
        or data[:2] == _COFF_MAGIC
        or data[:8] == _AR_MAGIC
        or data[:4] == _CLASS_MAGIC
        or data[:4] in (_MACHO_LE, _MACHO_BE)
    )


def is_known_binary_format(data: bytes, path: str = "") -> bool:
    """
    Return True for well-known binary formats (images, PDFs, archives)
    that should never be treated as text, regardless of byte ratios.
    """
    if len(data) < 4:
        return False
    return (
        data[:4] == _PDF_MAGIC
        or data[:4] == _ZIP_MAGIC
        or data[:4] == _ZIP_EMPTY
        or data[:3] == _JPEG_MAGIC
        or data[:4] == _PNG_MAGIC
        or data[:4] == _GIF_MAGIC
        or is_object_or_archive(data)
    )
