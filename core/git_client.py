"""
Git repository operations for the migration output.
Uses git fast-import for bulk history import (orders of magnitude faster than
individual commits) and falls back to standard git commands for final setup.
"""
from __future__ import annotations

import os
import re
import subprocess
import datetime
import logging
import shutil
from pathlib import Path
from typing import Optional

from .models import GitCommit

log = logging.getLogger(__name__)


def _run(args: list[str], cwd: Optional[str] = None,
         check: bool = True, input_data: Optional[bytes] = None,
         timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        args, cwd=cwd, capture_output=True,
        input=input_data, timeout=timeout, check=check,
    )


class GitClient:
    def __init__(self, repo_path: str, default_branch: str = "main"):
        self.repo_path = Path(repo_path)
        self.default_branch = default_branch
        self._fast_import_proc: Optional[subprocess.Popen] = None
        self._mark_counter = 0
        self._mark_map: dict[str, int] = {}   # version_ext → mark

    # ── repo init ─────────────────────────────────────────────────────────────

    def init(self, bare: bool = False) -> None:
        self.repo_path.mkdir(parents=True, exist_ok=True)
        args = ["git", "init", "-b", self.default_branch]
        if bare:
            args.append("--bare")
        _run(args, cwd=str(self.repo_path))
        log.info("Initialized git repo at %s", self.repo_path)

    def config(self, key: str, value: str) -> None:
        _run(["git", "config", key, value], cwd=str(self.repo_path))

    # ── git fast-import stream ────────────────────────────────────────────────

    def start_fast_import(self) -> None:
        """Open a long-running git fast-import process for bulk commit import."""
        self._fast_import_proc = subprocess.Popen(
            ["git", "fast-import", "--quiet", "--force"],
            cwd=str(self.repo_path),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        log.info("git fast-import started")

    def _fi_write(self, data: bytes) -> None:
        assert self._fast_import_proc and self._fast_import_proc.stdin
        self._fast_import_proc.stdin.write(data)

    def _fi_writeln(self, line: str) -> None:
        self._fi_write((line + "\n").encode())

    def _next_mark(self) -> int:
        self._mark_counter += 1
        return self._mark_counter

    def import_commit(self, commit: GitCommit) -> int:
        """
        Write one commit to the fast-import stream.
        Returns the mark number (use to build parent references).
        """
        mark = self._next_mark()
        ts = int(commit.timestamp.timestamp())
        tz = commit.timezone or "+0000"
        author_line = (
            f"{commit.author_name} <{commit.author_email}> {ts} {tz}"
        )
        branch_ref = f"refs/heads/{_safe_ref(commit.branch)}"

        self._fi_writeln(f"commit {branch_ref}")
        self._fi_writeln(f"mark :{mark}")
        self._fi_writeln(f"author {author_line}")
        self._fi_writeln(f"committer {author_line}")

        msg_bytes = (commit.message.strip() + "\n").encode("utf-8", errors="replace")
        self._fi_writeln(f"data {len(msg_bytes)}")
        self._fi_write(msg_bytes)

        if commit.parent_commits:
            for i, parent in enumerate(commit.parent_commits):
                prefix = "from" if i == 0 else "merge"
                if parent.startswith(":"):
                    self._fi_writeln(f"{prefix} {parent}")
                else:
                    self._fi_writeln(f"{prefix} {parent}")

        # file changes
        for rel_path, change in commit.file_changes.items():
            safe_path = _safe_path(rel_path)
            if change is None:
                # deletion
                self._fi_writeln(f"D {safe_path}")
                continue
            content_bytes, is_executable, is_symlink, symlink_target = change
            if is_symlink:
                mode = "120000"
                data = symlink_target.encode() if symlink_target else b""
            elif is_executable:
                mode = "100755"
                data = content_bytes or b""
            else:
                mode = "100644"
                data = content_bytes or b""

            self._fi_writeln(f"M {mode} inline {safe_path}")
            self._fi_writeln(f"data {len(data)}")
            self._fi_write(data)
            self._fi_writeln("")

        self._fi_writeln("")
        return mark

    def import_tag(self, tag_name: str, commit_mark: int,
                    tagger: str, timestamp: datetime.datetime,
                    message: str = "") -> None:
        safe_tag = _safe_ref(tag_name)
        ts = int(timestamp.timestamp())
        msg_bytes = (message.strip() + "\n").encode("utf-8", errors="replace")
        self._fi_writeln(f"tag {safe_tag}")
        self._fi_writeln(f"from :{commit_mark}")
        self._fi_writeln(f"tagger {tagger} {ts} +0000")
        self._fi_writeln(f"data {len(msg_bytes)}")
        self._fi_write(msg_bytes)
        self._fi_writeln("")

    def finish_fast_import(self) -> None:
        """Close the fast-import stream and wait for completion."""
        if not self._fast_import_proc:
            return
        self._fi_write(b"done\n")
        self._fast_import_proc.stdin.close()
        rc = self._fast_import_proc.wait(timeout=300)
        stderr = self._fast_import_proc.stderr.read().decode(errors="replace")
        if rc != 0:
            raise RuntimeError(f"git fast-import failed (rc={rc}): {stderr}")
        if stderr:
            log.debug("fast-import stderr: %s", stderr[:500])
        self._fast_import_proc = None
        log.info("git fast-import finished (%d marks)", self._mark_counter)

    # ── standard git operations ───────────────────────────────────────────────

    def checkout(self, branch: str, create: bool = False) -> None:
        args = ["git", "checkout"]
        if create:
            args += ["-b", branch]
        else:
            args.append(branch)
        _run(args, cwd=str(self.repo_path))

    def write_gitattributes(self, lfs_patterns: list[str],
                             text_patterns: list[str] | None = None) -> None:
        lines = [
            "# Auto-generated by cc2git migration",
            "* text=auto",
            "*.c text eol=lf diff=c",
            "*.h text eol=lf diff=c",
            "*.cpp text eol=lf diff=cpp",
            "*.hpp text eol=lf diff=cpp",
            "*.mk text eol=lf",
            "Makefile text eol=lf",
        ]
        for pat in lfs_patterns:
            lines.append(f"{pat} filter=lfs diff=lfs merge=lfs -text")
        ga_path = self.repo_path / ".gitattributes"
        ga_path.write_text("\n".join(lines) + "\n")

    def write_gitignore(self) -> None:
        lines = [
            "# ClearCase derived objects & cruft",
            "*.o", "*.a", "*.so", "*.so.*",
            "*.obj", "*.lib", "*.dll", "*.exe",
            "*.d",                          # gcc dependency files
            ".cmake_meta/",
            "lost+found/",
            ".clearcase_store",
        ]
        gi_path = self.repo_path / ".gitignore"
        gi_path.write_text("\n".join(lines) + "\n")

    def add_remote(self, name: str, url: str) -> None:
        _run(["git", "remote", "add", name, url],
             cwd=str(self.repo_path), check=False)

    def push(self, remote: str = "origin", all_branches: bool = True,
              all_tags: bool = True, force: bool = False) -> None:
        args = ["git", "push", remote]
        if all_branches:
            args.append("--all")
        if all_tags:
            args.append("--tags")
        if force:
            args.append("--force")
        _run(args, cwd=str(self.repo_path), timeout=1800)

    def lfs_install(self) -> None:
        _run(["git", "lfs", "install"], cwd=str(self.repo_path), check=False)

    def current_sha(self, branch: str) -> Optional[str]:
        try:
            r = _run(
                ["git", "rev-parse", f"refs/heads/{branch}"],
                cwd=str(self.repo_path), check=False,
            )
            return r.stdout.decode().strip() or None
        except Exception:
            return None

    def list_branches(self) -> list[str]:
        r = _run(["git", "branch", "--format=%(refname:short)"],
                 cwd=str(self.repo_path), check=False)
        return r.stdout.decode().splitlines()

    def list_tags(self) -> list[str]:
        r = _run(["git", "tag"], cwd=str(self.repo_path), check=False)
        return r.stdout.decode().splitlines()

    def clone_for_push(self, remote_url: str) -> None:
        """Add remote and push everything."""
        self.add_remote("origin", remote_url)
        self.push(force=True)


# ── ref name sanitization ─────────────────────────────────────────────────────

_BAD_REF = re.compile(r"[^\w./-]|\.lock$|@\{|\.\.|\s")


def _safe_ref(name: str) -> str:
    """Convert a ClearCase branch/label name to a valid Git ref component."""
    name = name.strip("/")
    # ClearCase branches use / as hierarchy separator — map to --
    name = name.replace("/", "--")
    name = _BAD_REF.sub("_", name)
    name = name.strip(".-")
    return name or "unnamed"


def _safe_path(path: str) -> str:
    """
    Make a file path safe for git fast-import data lines.
    Paths with spaces or special chars must be quoted.
    """
    # Remove leading slash
    path = path.lstrip("/")
    # fast-import requires quoting paths with spaces
    if " " in path or '"' in path or "\\" in path:
        path = '"' + path.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return path
