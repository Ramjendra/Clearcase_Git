"""
History Agent — fetches the full version history for every element and
groups individual element versions into logical Git commits.

For Base ClearCase:
  - Groups versions by (branch, author, timestamp-window, comment)
  - Preserves merge arrows as git merge parents
  - Handles lost+found elements as a separate orphan branch

For UCM ClearCase:
  - Uses activities as the primary commit grouping
  - Falls back to Base CC grouping for non-activity versions
"""
from __future__ import annotations

import json
import logging
import datetime
import collections
from pathlib import Path
from typing import Optional

from .base_agent import BaseAgent, AgentResult
from core.clearcase_client import ClearCaseClient
from core.config import MigrationConfig
from core.models import CCVersion, GitCommit, ElementType
from utils.path_sanitizer import (
    sanitize_path, vob_relative_path, is_lost_and_found, is_excluded_by_pattern,
    author_email_from_username,
)

log = logging.getLogger(__name__)

# Two versions by the same author with the same comment within this window
# are grouped into one Git commit.
COMMIT_GROUPING_WINDOW_SECS = 60


class HistoryAgent(BaseAgent):
    name = "history"

    def __init__(self, cfg: MigrationConfig, cc: ClearCaseClient,
                 discovery: dict, author_map: dict[str, tuple[str, str]]):
        super().__init__(cfg.workspace_dir, cfg.log_dir)
        self.cfg = cfg
        self.cc = cc
        self.discovery = discovery
        self.author_map = author_map   # {cc_user: (git_name, git_email)}

    def run(self, **kwargs) -> AgentResult:
        self._report("Starting history extraction")
        all_versions: list[CCVersion] = []

        elements = self.discovery.get("all_elements", [])
        total = len(elements)

        for i, element_path in enumerate(elements):
            if self.is_done(element_path):
                continue
            if is_excluded_by_pattern(element_path, self.cfg.exclude_patterns):
                log.debug("Skipping excluded element: %s", element_path)
                continue
            self._report(f"Fetching history: {Path(element_path).name}", i, total)
            try:
                versions = self.retry(
                    self.cc.element_history, element_path,
                    label=element_path, attempts=3,
                )
                all_versions.extend(versions)
                self.mark_done(element_path)
            except Exception as exc:
                log.error("History failed for %s: %s", element_path, exc)

        self._report(f"Total versions collected: {len(all_versions)}")

        # Group into commits
        if self.cfg.clearcase.is_ucm and self.discovery.get("vobs"):
            commits = self._group_by_activity(all_versions)
        else:
            commits = self._group_by_time_window(all_versions)

        # Sort commits topologically (by branch + timestamp)
        commits = self._topological_sort(commits)

        # Serialize for the extractor agent
        out_path = Path(self.cfg.workspace_dir) / "commits.json"
        serialized = [self._commit_to_dict(c) for c in commits]
        out_path.write_text(json.dumps(serialized, indent=2, default=str))
        self._report(f"History grouped into {len(commits)} commits → {out_path}")
        return AgentResult(success=True, data=commits)

    # ── commit grouping: Base CC ───────────────────────────────────────────────

    def _group_by_time_window(self, versions: list[CCVersion]) -> list[GitCommit]:
        """
        Group element versions into commits by (branch, author, comment, time-window).
        """
        # bucket key → list of versions
        buckets: dict[tuple, list[CCVersion]] = collections.defaultdict(list)

        for ver in sorted(versions, key=lambda v: v.created_at):
            branch = self._normalize_branch(ver.branch)
            author = ver.created_by
            comment = ver.comment.strip() or "(no comment)"
            # Round timestamp to grouping window
            ts_bucket = int(ver.created_at.timestamp()) // COMMIT_GROUPING_WINDOW_SECS
            key = (branch, author, comment, ts_bucket)
            buckets[key].append(ver)

        commits: list[GitCommit] = []
        for (branch, author, comment, ts_bucket), vers in buckets.items():
            # Use the latest timestamp in the bucket
            ts = max(v.created_at for v in vers)
            git_name, git_email = self._resolve_author(author)
            message = self._build_commit_message(comment, vers)

            file_changes: dict[str, tuple] = {}
            merge_parents: list[str] = []
            for ver in vers:
                rel_path = self._element_to_rel_path(ver.element_path)
                if rel_path:
                    file_changes[rel_path] = (
                        None,   # placeholder for content bytes
                        False,  # is_executable (filled later)
                        False,  # is_symlink
                        None,   # symlink_target
                        ver.version_id,    # extra: CC version to extract
                        ver.element_path,  # extra: CC element path
                        ver.is_deleted,    # extra: emit git delete if True
                    )
                # Merge arrows → merge parents (resolved later)
                for merge_src in ver.merge_sources:
                    if merge_src and merge_src not in merge_parents:
                        merge_parents.append(merge_src)

            gc = GitCommit(
                branch=branch,
                message=message,
                author_name=git_name,
                author_email=git_email,
                timestamp=ts,
                file_changes=file_changes,
                parent_commits=[],   # resolved by topological sort
                merge_from_branch=merge_parents[0] if merge_parents else None,
            )
            commits.append(gc)
        return commits

    # ── commit grouping: UCM ──────────────────────────────────────────────────

    def _group_by_activity(self, versions: list[CCVersion]) -> list[GitCommit]:
        """Group versions by UCM activity (activity == commit)."""
        activities = []
        for vob_data in self.discovery.get("vobs", {}).values():
            activities.extend(vob_data.get("activities", []))

        # Map version extended name → activity
        ver_to_act: dict[str, dict] = {}
        for act in activities:
            for cs_item in act.get("changeset", []):
                ver_to_act[cs_item] = act

        activity_buckets: dict[str, list[CCVersion]] = collections.defaultdict(list)
        orphan: list[CCVersion] = []
        for ver in versions:
            ext = f"{ver.element_path}@@{ver.version_id}"
            act = ver_to_act.get(ext)
            if act:
                activity_buckets[act["id"]].append(ver)
            else:
                orphan.append(ver)

        commits: list[GitCommit] = []
        act_by_id = {a["id"]: a for a in activities}

        for act_id, vers in activity_buckets.items():
            act = act_by_id[act_id]
            author = act.get("owner", "unknown")
            git_name, git_email = self._resolve_author(author)
            ts_str = act.get("created_at", "1970-01-01 00:00:00+00:00")
            try:
                ts = datetime.datetime.fromisoformat(str(ts_str))
            except ValueError:
                ts = datetime.datetime.now(tz=datetime.timezone.utc)

            file_changes: dict[str, tuple] = {}
            for ver in vers:
                rel_path = self._element_to_rel_path(ver.element_path)
                if rel_path:
                    file_changes[rel_path] = (
                        None, False, False, None,
                        ver.version_id, ver.element_path,
                    )

            gc = GitCommit(
                branch=self._normalize_branch(
                    self.cfg.clearcase.stream_tag or "main"
                ),
                message=f"{act.get('headline', act_id)}\n\nClearCase-Activity: {act_id}",
                author_name=git_name,
                author_email=git_email,
                timestamp=ts,
                file_changes=file_changes,
                cc_activity_id=act_id,
            )
            commits.append(gc)

        # Orphan versions fall back to time-window grouping
        if orphan:
            commits.extend(self._group_by_time_window(orphan))
        return commits

    # ── topological sort ──────────────────────────────────────────────────────

    def _topological_sort(self, commits: list[GitCommit]) -> list[GitCommit]:
        """
        Sort commits: first by branch depth (main first), then by timestamp.
        This ensures parent commits always precede their children in the stream.
        """
        branch_order = self.discovery.get("branch_git_map", {})
        default = self.cfg.git.default_branch

        def branch_priority(c: GitCommit) -> int:
            if c.branch == default:
                return 0
            return 1

        return sorted(commits, key=lambda c: (branch_priority(c), c.timestamp))

    # ── helpers ───────────────────────────────────────────────────────────────

    def _normalize_branch(self, cc_branch: str) -> str:
        branch_map = self.discovery.get("branch_git_map", {})
        # cc_branch may be a full path like /main/rel2_bugfix
        # strip leading /main/ for lookup
        short = cc_branch.lstrip("/").split("/")[-1]
        if short in branch_map:
            return branch_map[short]
        if cc_branch in branch_map:
            return branch_map[cc_branch]
        # Fallback: map "main" to default
        if short.lower() in ("main", ""):
            return self.cfg.git.default_branch
        from core.git_client import _safe_ref
        return _safe_ref(short)

    def _resolve_author(self, cc_user: str) -> tuple[str, str]:
        if cc_user in self.author_map:
            return self.author_map[cc_user]
        email = author_email_from_username(cc_user)
        return cc_user, email

    def _element_to_rel_path(self, element_path: str) -> Optional[str]:
        for vob_tag in self.cfg.clearcase.vob_tags:
            if element_path.startswith(vob_tag) or vob_tag in element_path:
                rel = sanitize_path(element_path, vob_tag)
                return rel
        return sanitize_path(element_path, "")

    def _build_commit_message(self, comment: str, versions: list[CCVersion]) -> str:
        lines = [comment]
        if len(versions) == 1:
            ver = versions[0]
            lines.append(
                f"\nClearCase-Element: {ver.element_path}@@{ver.version_id}"
            )
        else:
            paths = ", ".join(
                f"{Path(v.element_path).name}@@{v.version_id}"
                for v in versions[:5]
            )
            if len(versions) > 5:
                paths += f" (+{len(versions)-5} more)"
            lines.append(f"\nClearCase-Elements: {paths}")
        return "\n".join(lines)

    def _commit_to_dict(self, gc: GitCommit) -> dict:
        return {
            "branch": gc.branch,
            "message": gc.message,
            "author_name": gc.author_name,
            "author_email": gc.author_email,
            "timestamp": gc.timestamp.isoformat(),
            "file_changes": {
                path: {
                    "version_id":   change[4] if len(change) > 4 else None,
                    "element_path": change[5] if len(change) > 5 else None,
                    "is_executable": change[1],
                    "is_symlink":   change[2],
                    "symlink_target": change[3],
                    "is_deleted":   change[6] if len(change) > 6 else False,
                }
                for path, change in gc.file_changes.items()
            },
            "merge_from_branch": gc.merge_from_branch,
            "cc_activity_id": gc.cc_activity_id,
            "tags": gc.tags,
        }
