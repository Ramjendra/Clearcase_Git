"""
C File Agent — specialized analysis for C/C++ source files.

Handles the many corner cases that arise when migrating C code from ClearCase:

1.  ClearCase version-extended #include paths
    Some teams accidentally check in headers with @@-extended paths.
    We rewrite these to normal relative paths.

2.  CLEARCASE_ROOT / VIEWROOT macros in Makefiles and .c files
    Some projects embed hard-coded view paths. We replace with $(REPO_ROOT).

3.  Encoding issues
    Many legacy C files are ISO-8859-1, Windows-1252, or even EBCDIC.
    We normalize to UTF-8, preserving content fidelity.

4.  ClearCase keyword expansion (like RCS keywords)
    $Header$, $Id$, $Author$ etc. are expanded inline by ClearCase.
    We optionally strip the expanded value, leaving just $Header$.

5.  Derived-object detection
    .o, .a, .so files sometimes slip into the VOB as checked-in files.
    We detect and either skip or LFS them.

6.  Merge-conflict markers
    Some checked-in files still have <<<< ==== >>>> markers from unresolved
    ClearCase merges. We flag these.

7.  Long lines / NULL bytes
    Very old ANSI C may have null-padded strings in source. We handle.

8.  #pragma ident strings with CC version
    Oracle/Sun toolchain embeds version info; we preserve but annotate.
"""
from __future__ import annotations

import re
import logging
from pathlib import PurePosixPath
from typing import Optional

from utils.binary_detector import (
    is_binary, detect_encoding, normalize_line_endings, is_object_or_archive,
)

log = logging.getLogger(__name__)

# ── patterns ──────────────────────────────────────────────────────────────────

# ClearCase keyword expansion: $Header: ... $  →  $Header$
_CC_KEYWORD_RE = re.compile(
    r"\$(Header|Id|Author|Date|Locker|Name|RCSfile|Revision|Source|State)"
    r":[^$]*\$",
    re.IGNORECASE,
)

# @@-extended include: #include "foo/bar.h@@/main/rel2/3"
_CC_INCLUDE_RE = re.compile(
    r'#\s*include\s*["<]([^">\s]+@@[^">\s]+)[">]'
)

# Hard-coded view root in paths
_VIEW_ROOT_RE = re.compile(
    r'/(?:view|clearcase)/[a-zA-Z0-9_./-]+?/vobs/',
    re.IGNORECASE,
)

# ClearCase merge-conflict markers (they differ from Git's >>>)
_CC_MERGE_CONFLICT_RE = re.compile(
    r'^={8}|^>{8}|^<{8}|>>>.*CHECKEDOUT|<<<.*CHECKEDOUT',
    re.MULTILINE,
)

# #pragma ident with CC version
_PRAGMA_IDENT_RE = re.compile(
    r'#pragma\s+ident\s+"[^"]*@@[^"]*"'
)

# Derived object suffixes that should never be in a VOB
_DERIVED_SUFFIXES = frozenset([
    ".o", ".obj", ".a", ".lib", ".so", ".dll", ".exe",
    ".out", ".d",  # gcc dep files
])

C_EXTENSIONS = frozenset([
    ".c", ".h", ".cpp", ".cxx", ".cc", ".C",
    ".hpp", ".hxx", ".hh", ".H",
    ".inl", ".tcc",
])


class CFileIssue:
    def __init__(self, kind: str, detail: str, line: Optional[int] = None):
        self.kind = kind
        self.detail = detail
        self.line = line

    def __repr__(self):
        loc = f":{self.line}" if self.line else ""
        return f"[{self.kind}{loc}] {self.detail}"


class CFileAnalysis:
    def __init__(self):
        self.is_derived_object = False
        self.is_binary = False
        self.original_encoding = "utf-8"
        self.issues: list[CFileIssue] = []
        self.rewritten_content: Optional[bytes] = None   # None = no change needed

    @property
    def has_issues(self) -> bool:
        return bool(self.issues)


class CFileAgent:
    """
    Stateless analyzer — call analyze() per file version.
    Can be used directly (no BaseAgent overhead needed for per-file work).
    """

    def __init__(self, strip_keywords: bool = True,
                 fix_includes: bool = True,
                 normalize_paths: bool = True,
                 detect_encoding: bool = True):
        self.strip_keywords = strip_keywords
        self.fix_includes = fix_includes
        self.normalize_paths = normalize_paths
        self.do_detect_encoding = detect_encoding

    def analyze(self, path: str, raw_bytes: bytes) -> CFileAnalysis:
        result = CFileAnalysis()
        suffix = PurePosixPath(path).suffix.lower()

        # ── derived object check ──────────────────────────────────────────────
        if suffix in _DERIVED_SUFFIXES or is_object_or_archive(raw_bytes):
            result.is_derived_object = True
            result.is_binary = True
            result.issues.append(CFileIssue(
                "derived_object",
                f"File {path!r} appears to be a compiled object/archive",
            ))
            return result

        # ── binary check ─────────────────────────────────────────────────────
        if is_binary(raw_bytes):
            result.is_binary = True
            return result

        # ── encoding detection ────────────────────────────────────────────────
        from utils.binary_detector import detect_encoding as _detect_enc
        enc = _detect_enc(raw_bytes) if self.do_detect_encoding else "utf-8"
        result.original_encoding = enc

        try:
            text = raw_bytes.decode(enc, errors="replace")
        except LookupError:
            text = raw_bytes.decode("latin-1", errors="replace")
            result.original_encoding = "latin-1"

        modified = False

        # ── ClearCase keyword stripping ───────────────────────────────────────
        if self.strip_keywords and suffix in C_EXTENSIONS:
            new_text, n = _CC_KEYWORD_RE.subn(lambda m: f"${m.group(1)}$", text)
            if n:
                result.issues.append(CFileIssue(
                    "cc_keywords", f"Stripped {n} ClearCase keyword expansion(s)",
                ))
                text = new_text
                modified = True

        # ── @@-extended include paths ─────────────────────────────────────────
        if self.fix_includes and suffix in C_EXTENSIONS:
            def _fix_include(m: re.Match) -> str:
                orig = m.group(1)
                clean = orig.split("@@")[0]
                # preserve < or " delimiter
                delim = m.group(0)[len("#include"):].lstrip()[0]
                close = ">" if delim == "<" else '"'
                return f'#include {delim}{clean}{close}'

            new_text, n = _CC_INCLUDE_RE.subn(_fix_include, text)
            if n:
                result.issues.append(CFileIssue(
                    "cc_include_ext", f"Fixed {n} @@-extended #include path(s)",
                ))
                text = new_text
                modified = True

        # ── hard-coded view-root paths ────────────────────────────────────────
        if self.normalize_paths:
            new_text, n = _VIEW_ROOT_RE.subn("/vobs/", text)
            if n:
                result.issues.append(CFileIssue(
                    "view_root_path", f"Replaced {n} hard-coded view-root path(s)",
                ))
                text = new_text
                modified = True

        # ── merge conflict markers ────────────────────────────────────────────
        if _CC_MERGE_CONFLICT_RE.search(text):
            for lineno, line in enumerate(text.splitlines(), 1):
                if re.match(r'^={8}|^>{8}|^<{8}', line):
                    result.issues.append(CFileIssue(
                        "merge_conflict",
                        f"Unresolved ClearCase merge marker",
                        line=lineno,
                    ))
                    break

        # ── #pragma ident with CC version ────────────────────────────────────
        if _PRAGMA_IDENT_RE.search(text):
            result.issues.append(CFileIssue(
                "pragma_ident",
                "#pragma ident contains ClearCase version string (preserved)",
            ))

        # ── normalize to UTF-8 + LF ───────────────────────────────────────────
        out_bytes = text.encode("utf-8", errors="replace")
        out_bytes = normalize_line_endings(out_bytes, "utf-8")

        if modified or enc not in ("utf-8", "utf-8-sig", "ascii"):
            result.rewritten_content = out_bytes

        return result

    def analyze_makefile(self, path: str, raw_bytes: bytes) -> CFileAnalysis:
        """
        Makefiles often contain ClearCase view-root paths and CLEARCASE_ROOT
        references that break after migration.
        """
        result = self.analyze(path, raw_bytes)
        if result.is_binary:
            return result

        text = (result.rewritten_content or raw_bytes).decode("utf-8", errors="replace")
        modified = False

        # Replace CLEARCASE_ROOT with a neutral variable
        if "CLEARCASE_ROOT" in text or "CLEARCASE_VIEWROOT" in text:
            text = text.replace("$(CLEARCASE_ROOT)", "$(REPO_ROOT)")
            text = text.replace("${CLEARCASE_ROOT}", "$(REPO_ROOT)")
            text = text.replace("$(CLEARCASE_VIEWROOT)", "$(REPO_ROOT)")
            result.issues.append(CFileIssue(
                "makefile_cc_var",
                "Replaced CLEARCASE_ROOT/VIEWROOT references with $(REPO_ROOT)",
            ))
            modified = True

        # Replace view-based paths in make variables
        new_text, n = _VIEW_ROOT_RE.subn("$(REPO_ROOT)/", text)
        if n:
            text = new_text
            result.issues.append(CFileIssue(
                "makefile_view_path", f"Fixed {n} view-root path(s) in Makefile",
            ))
            modified = True

        if modified:
            result.rewritten_content = text.encode("utf-8", errors="replace")
        return result


def build_issue_report(issues_by_file: dict[str, list[CFileIssue]]) -> str:
    """Generate a human-readable issue report for the migration log."""
    lines = ["# C/C++ File Migration Issues", ""]
    for path, issues in sorted(issues_by_file.items()):
        lines.append(f"## {path}")
        for issue in issues:
            loc = f" (line {issue.line})" if issue.line else ""
            lines.append(f"  - [{issue.kind}]{loc} {issue.detail}")
        lines.append("")
    return "\n".join(lines)
