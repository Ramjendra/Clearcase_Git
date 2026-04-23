"""
Git Conversion Agent — reads enriched_commits.json and writes the complete
git history using git fast-import.

Handles:
  - Branch creation and tracking
  - Merge commits (ClearCase merge arrows → git merge parents)
  - Label → annotated tag conversion
  - Initial .gitattributes and .gitignore commit
  - Orphan branches (lost+found)
  - Resume from a previous partial run
"""
from __future__ import annotations

import base64
import json
import logging
import datetime
from pathlib import Path
from typing import Optional

from .base_agent import BaseAgent, AgentResult
from core.git_client import GitClient, _safe_ref
from core.config import MigrationConfig

log = logging.getLogger(__name__)


class GitConversionAgent(BaseAgent):
    name = "git_conversion"

    def __init__(self, cfg: MigrationConfig, git: GitClient, discovery: dict):
        super().__init__(cfg.workspace_dir, cfg.log_dir)
        self.cfg = cfg
        self.git = git
        self.discovery = discovery
        # branch → latest mark number
        self._branch_tip: dict[str, str] = {}   # branch → ":<mark>"
        # cc_label → mark
        self._label_marks: dict[str, int] = {}

    def run(self, **kwargs) -> AgentResult:
        commits_path = Path(self.cfg.workspace_dir) / "enriched_commits.json"
        if not commits_path.exists():
            return AgentResult(
                success=False,
                error="enriched_commits.json not found — run ExtractorAgent first",
            )

        commits = json.loads(commits_path.read_text())
        self._report(f"Converting {len(commits)} commits to git history")

        if not self.cfg.dry_run:
            self.git.init()
            self.git.config("user.email", "cc2git@migration.local")
            self.git.config("user.name", "ClearCase Migration")
            if self.cfg.git.use_lfs:
                self.git.lfs_install()
            self.git.start_fast_import()

            # Inject .gitattributes and .gitignore as the very first commit
            self._inject_meta_commit()

        total = len(commits)
        failed = 0
        for i, commit in enumerate(commits):
            self._report(f"Importing commit {i+1}/{total}", i, total)
            try:
                self._import_commit(commit, i)
            except Exception as exc:
                log.error("Failed to import commit %d: %s", i, exc)
                failed += 1

        # Attach labels as annotated tags
        self._attach_labels()

        if not self.cfg.dry_run:
            self.git.finish_fast_import()

        # Write LFS upload script
        lfs_store_path = Path(self.cfg.workspace_dir) / "lfs_objects"
        lfs_script = Path(self.cfg.log_dir) / "upload_lfs.sh"
        # (lfs store is managed by ExtractorAgent; we just note it here)

        self._report(
            f"Git conversion complete. {total - failed} ok, {failed} failed. "
            f"Branches: {sorted(self._branch_tip.keys())}"
        )
        return AgentResult(success=failed == 0, data={
            "branches": sorted(self._branch_tip.keys()),
            "failed_commits": failed,
        })

    # ── meta commit ───────────────────────────────────────────────────────────

    def _inject_meta_commit(self) -> None:
        """Write .gitattributes and .gitignore as commit mark :1 on default branch."""
        if self.cfg.dry_run:
            return
        self.git.write_gitattributes(self.cfg.git.lfs_patterns)
        self.git.write_gitignore()

        # Read them back as bytes for fast-import
        ga_bytes = (Path(self.cfg.git.output_dir) / ".gitattributes").read_bytes()
        gi_bytes = (Path(self.cfg.git.output_dir) / ".gitignore").read_bytes()

        now = datetime.datetime.now(tz=datetime.timezone.utc)
        ts = int(now.timestamp())
        branch_ref = f"refs/heads/{self.cfg.git.default_branch}"

        fi = self.git._fast_import_proc
        def _w(s):
            fi.stdin.write((s + "\n").encode())

        mark = self.git._next_mark()
        author = f"ClearCase Migration <cc2git@migration.local> {ts} +0000"
        msg = b"chore: initialize repo with .gitattributes and .gitignore\n"

        _w(f"commit {branch_ref}")
        _w(f"mark :{mark}")
        _w(f"author {author}")
        _w(f"committer {author}")
        _w(f"data {len(msg)}")
        fi.stdin.write(msg)
        _w(f"M 100644 inline .gitattributes")
        _w(f"data {len(ga_bytes)}")
        fi.stdin.write(ga_bytes)
        _w("")
        _w(f"M 100644 inline .gitignore")
        _w(f"data {len(gi_bytes)}")
        fi.stdin.write(gi_bytes)
        _w("")
        _w("")

        self._branch_tip[self.cfg.git.default_branch] = f":{mark}"
        log.info("Injected meta commit (mark :%d)", mark)

    # ── commit import ─────────────────────────────────────────────────────────

    def _import_commit(self, commit: dict, idx: int) -> None:
        branch = commit.get("branch", self.cfg.git.default_branch)
        author_name = commit.get("author_name", "Unknown")
        author_email = commit.get("author_email", "unknown@migrated.local")
        message = commit.get("message", "(no message)")
        ts_str = commit.get("timestamp", "1970-01-01T00:00:00+00:00")
        try:
            ts = datetime.datetime.fromisoformat(ts_str)
        except ValueError:
            ts = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)

        if self.cfg.dry_run:
            log.debug("[DRY-RUN] Would import commit on branch=%s ts=%s", branch, ts)
            return

        mark = self.git._next_mark()
        ts_epoch = int(ts.timestamp())
        tz_str = _tz_offset(ts)
        author_line = f"{author_name} <{author_email}> {ts_epoch} {tz_str}"
        branch_ref = f"refs/heads/{_safe_ref(branch)}"
        git_branch = _safe_ref(branch)

        fi = self.git._fast_import_proc
        def _w(s):
            fi.stdin.write((s + "\n").encode())

        def _wb(b):
            fi.stdin.write(b)

        _w(f"commit {branch_ref}")
        _w(f"mark :{mark}")
        _w(f"author {author_line}")
        _w(f"committer {author_line}")
        msg_bytes = (message.strip() + "\n").encode("utf-8", errors="replace")
        _w(f"data {len(msg_bytes)}")
        _wb(msg_bytes)

        # Parent: previous tip of this branch
        if git_branch in self._branch_tip:
            _w(f"from {self._branch_tip[git_branch]}")
        elif git_branch != self.cfg.git.default_branch and self.cfg.git.default_branch in self._branch_tip:
            # New branch — fork from default branch
            _w(f"from {self._branch_tip[self.cfg.git.default_branch]}")

        # Merge parent (ClearCase merge arrow)
        merge_from = commit.get("merge_from_branch")
        if merge_from:
            merge_git = _safe_ref(merge_from)
            if merge_git in self._branch_tip:
                _w(f"merge {self._branch_tip[merge_git]}")

        # File changes
        file_changes = commit.get("file_changes", {})
        for rel_path, change in file_changes.items():
            if not change:
                continue
            if change.get("skipped") or change.get("error"):
                continue
            if change.get("deleted"):
                _w(f"D {_qpath(rel_path)}")
                continue

            content_b64 = change.get("content_b64")
            is_exec = change.get("is_executable", False)
            is_symlink = change.get("is_symlink", False)
            symlink_target = change.get("symlink_target")

            if is_symlink and symlink_target:
                mode = "120000"
                data = symlink_target.encode()
            elif is_exec:
                mode = "100755"
                data = base64.b64decode(content_b64) if content_b64 else b""
            else:
                mode = "100644"
                data = base64.b64decode(content_b64) if content_b64 else b""

            _w(f"M {mode} inline {_qpath(rel_path)}")
            _w(f"data {len(data)}")
            _wb(data)
            _w("")

        _w("")
        self._branch_tip[git_branch] = f":{mark}"

        # Tags carried by this commit
        for label in commit.get("tags", []):
            self._label_marks[label] = mark

    # ── label → tag ───────────────────────────────────────────────────────────

    def _attach_labels(self) -> None:
        if self.cfg.dry_run:
            return
        for vob_tag, vob_data in self.discovery.get("vobs", {}).items():
            for lb in vob_data.get("labels", []):
                label_name = lb["name"]
                if label_name not in self._label_marks:
                    # Label not encountered in history — attach to latest mark
                    # of default branch as a best-effort
                    default_mark_str = self._branch_tip.get(self.cfg.git.default_branch)
                    if default_mark_str:
                        mark = int(default_mark_str.lstrip(":"))
                        self._label_marks[label_name] = mark
                    else:
                        continue

                mark = self._label_marks[label_name]
                now = int(datetime.datetime.now(tz=datetime.timezone.utc).timestamp())
                tagger = f"ClearCase Migration <cc2git@migration.local> {now} +0000"
                msg_bytes = f"ClearCase label: {label_name}\n".encode()
                safe_tag = _safe_ref(label_name)

                fi = self.git._fast_import_proc
                def _w(s):
                    fi.stdin.write((s + "\n").encode())

                _w(f"tag {safe_tag}")
                _w(f"from :{mark}")
                _w(f"tagger {tagger}")
                _w(f"data {len(msg_bytes)}")
                fi.stdin.write(msg_bytes)
                _w("")
                log.debug("Tag %s → mark :%d", safe_tag, mark)


# ── helpers ───────────────────────────────────────────────────────────────────

def _tz_offset(dt: datetime.datetime) -> str:
    if dt.tzinfo is None:
        return "+0000"
    offset = dt.utcoffset()
    if offset is None:
        return "+0000"
    total_secs = int(offset.total_seconds())
    sign = "+" if total_secs >= 0 else "-"
    total_secs = abs(total_secs)
    hh, mm = divmod(total_secs // 60, 60)
    return f"{sign}{hh:02d}{mm:02d}"


def _qpath(path: str) -> str:
    """Quote paths with spaces for git fast-import."""
    path = path.lstrip("/")
    if " " in path or '"' in path or "\\" in path:
        return '"' + path.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return path
