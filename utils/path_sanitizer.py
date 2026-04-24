"""
Path and filename sanitization for ClearCase → Git migration.

ClearCase allows characters in file/dir names that are problematic on some
filesystems or in Git (NUL, leading dots, Windows-reserved names, etc.).
"""
from __future__ import annotations
import re
import unicodedata
import logging
from pathlib import PurePosixPath

log = logging.getLogger(__name__)

# Characters illegal in most filesystems or confusing for shell/git
_ILLEGAL = re.compile(r'[<>:"|?*\x00-\x1f\\]')
# Windows reserved device names (case-insensitive)
_WIN_RESERVED = re.compile(
    r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)", re.IGNORECASE
)
_CLEARCASE_SUFFIXES = frozenset([
    ".contrib", ".keep", ".keep.contrib",
    ".unloaded", ".mkelem",
])


def sanitize_path(cc_path: str, vob_root: str) -> str:
    """
    Convert a ClearCase element path to a relative Git-safe path.

    - Strip the VOB root prefix
    - Strip version-extended name (@@...)
    - Sanitize each path component
    - Return POSIX-style relative path (no leading slash)
    """
    # Strip version extended name
    if "@@" in cc_path:
        cc_path = cc_path.split("@@")[0]

    # Strip vob root prefix (handle trailing slash on vob_root)
    vob_root = vob_root.rstrip("/")
    if cc_path.startswith(vob_root):
        rel = cc_path[len(vob_root):]
    else:
        rel = cc_path

    rel = rel.lstrip("/")
    # Collapse double slashes that sometimes appear in ClearCase paths
    while "//" in rel:
        rel = rel.replace("//", "/")
    parts = rel.split("/")
    sanitized = [_sanitize_component(p) for p in parts if p]
    result = "/".join(sanitized)
    if result != rel:
        log.debug("Path sanitized: %s → %s", rel, result)
    return result


def _sanitize_component(name: str) -> str:
    """Sanitize a single path component."""
    # Normalize Unicode to NFC (macOS VOBs may store NFD; git/Linux expects NFC)
    name = unicodedata.normalize("NFC", name)

    # Strip leading and trailing spaces (invisible, causes issues on Windows/git)
    name = name.strip()

    # Replace illegal chars with underscore
    name = _ILLEGAL.sub("_", name)

    # Remove trailing dots (Windows FS issue)
    name = name.rstrip(".")

    # Windows reserved names
    if _WIN_RESERVED.match(name):
        name = "_" + name

    # Guard against components that would confuse git itself
    if name == ".git" or name.lower() == ".git":
        name = "_git"

    # ClearCase-specific suffixes that git doesn't need
    for suf in _CLEARCASE_SUFFIXES:
        if name.endswith(suf):
            name = name[: -len(suf)]
            break

    # Empty result fallback
    return name or "_empty_"


def vob_relative_path(element_path: str, vob_tag: str) -> str:
    """Strip the VOB tag from the front of an element path."""
    vob_tag = vob_tag.rstrip("/")
    if element_path.startswith(vob_tag):
        return element_path[len(vob_tag):].lstrip("/")
    return element_path.lstrip("/")


def is_lost_and_found(path: str) -> bool:
    return "lost+found" in path.lower().split("/")


def is_excluded_by_pattern(path: str, patterns: list[str]) -> bool:
    import fnmatch
    name = PurePosixPath(path).name
    for pat in patterns:
        if fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(path, pat):
            return True
    return False


def author_email_from_username(username: str,
                                domain: str = "migrated.local") -> str:
    """Create a placeholder email from a ClearCase username."""
    safe = re.sub(r"[^a-zA-Z0-9._+-]", "_", username)
    return f"{safe}@{domain}"
