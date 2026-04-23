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


# ── C-specific binary patterns ─────────────────────────────────────────────

_ELF_MAGIC = b"\x7fELF"
_COFF_MAGIC = b"\x4d\x5a"  # MZ (PE/COFF)
_AR_MAGIC = b"!<arch>\n"   # .a archive


def is_object_or_archive(data: bytes) -> bool:
    """Return True if data looks like a compiled object, archive, or executable."""
    if len(data) < 4:
        return False
    return (
        data[:4] == _ELF_MAGIC
        or data[:2] == _COFF_MAGIC
        or data[:8] == _AR_MAGIC
    )
