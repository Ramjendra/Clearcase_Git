"""
Extractor Agent — fetches actual file content for every version referenced
in the commit plan produced by HistoryAgent, then feeds the content into
the GitConversionAgent.

Key responsibilities:
  - Extract file bytes via cleartool get
  - Detect binary vs text
  - Run CFileAgent for C/C++ source and Makefiles
  - Apply LFS decisions
  - Handle symlinks, empty dirs (.gitkeep), and deleted files
  - Cache extracted versions to disk to survive restarts
"""
from __future__ import annotations

import json
import logging
import hashlib
from pathlib import Path
from typing import Optional
import concurrent.futures

from .base_agent import BaseAgent, AgentResult
from .c_file_agent import CFileAgent, build_issue_report
from core.clearcase_client import ClearCaseClient
from core.config import MigrationConfig
from core.git_client import GitClient
from core.models import ElementType
from utils.binary_detector import is_binary, detect_encoding
from utils.lfs_handler import LFSBlobStore, should_use_lfs, lfs_pointer
from utils.path_sanitizer import is_excluded_by_pattern

log = logging.getLogger(__name__)


class ExtractorAgent(BaseAgent):
    name = "extractor"

    def __init__(self, cfg: MigrationConfig, cc: ClearCaseClient,
                 git: GitClient, lfs_store: LFSBlobStore):
        super().__init__(cfg.workspace_dir, cfg.log_dir)
        self.cfg = cfg
        self.cc = cc
        self.git = git
        self.lfs = lfs_store
        self.c_agent = CFileAgent(
            strip_keywords=True,
            fix_includes=True,
            normalize_paths=True,
            detect_encoding=cfg.detect_encoding,
        )
        self._cache_dir = Path(cfg.workspace_dir) / "version_cache"
        self._cache_dir.mkdir(exist_ok=True)
        self._issues: dict[str, list] = {}

    def run(self, **kwargs) -> AgentResult:
        commits_path = Path(self.cfg.workspace_dir) / "commits.json"
        if not commits_path.exists():
            return AgentResult(success=False, error="commits.json not found — run HistoryAgent first")

        commits = json.loads(commits_path.read_text())
        self._report(f"Extracting content for {len(commits)} commits")

        # Pre-fetch all unique versions in parallel to warm the disk cache,
        # then enrich commits sequentially (preserves order).
        self._prefetch_versions_parallel(commits)

        enriched_commits = []
        for i, commit in enumerate(commits):
            self._report(f"Processing commit {i+1}/{len(commits)}", i, len(commits))
            enriched = self._enrich_commit(commit)
            enriched_commits.append(enriched)

        # Write issue report
        if self._issues:
            report = build_issue_report({
                path: [type('Issue', (), {'kind': iss['kind'],
                                          'detail': iss['detail'],
                                          'line': iss.get('line')})()
                        for iss in issues]
                for path, issues in self._issues.items()
            })
            issue_path = Path(self.cfg.log_dir) / "c_file_issues.md"
            issue_path.write_text(report)
            log.info("C file issue report: %s", issue_path)

        out_path = Path(self.cfg.workspace_dir) / "enriched_commits.json"
        out_path.write_text(json.dumps(enriched_commits, indent=2, default=str))
        self._report(f"Extraction complete → {out_path}")
        return AgentResult(success=True, data=enriched_commits)

    def _prefetch_versions_parallel(self, commits: list[dict]) -> None:
        """
        Fetch all unique (element_path, version_id) pairs from ClearCase in
        parallel using a thread pool, writing results to the version cache.
        Sequential enrichment can then read from cache without blocking on I/O.
        """
        seen: set[str] = set()
        work: list[tuple[str, str]] = []
        for commit in commits:
            for change_meta in commit.get("file_changes", {}).values():
                if change_meta.get("is_deleted") or change_meta.get("is_symlink"):
                    continue
                ep = change_meta.get("element_path", "")
                vid = change_meta.get("version_id", "")
                if not ep or not vid or vid.endswith("/0"):
                    continue
                key = f"{ep}@@{vid}"
                if key in seen:
                    continue
                seen.add(key)
                cache_key = __import__("hashlib").md5(key.encode()).hexdigest()
                if not (self._cache_dir / cache_key).exists():
                    work.append((ep, vid))

        if not work:
            return

        workers = min(self.cfg.max_workers, len(work))
        log.info("[extractor] Pre-fetching %d unique versions with %d workers",
                 len(work), workers)

        def _fetch(item: tuple[str, str]) -> None:
            ep, vid = item
            cache_key = __import__("hashlib").md5(f"{ep}@@{vid}".encode()).hexdigest()
            cache_file = self._cache_dir / cache_key
            if cache_file.exists():
                return
            try:
                raw = self.retry(
                    self.cc.get_version_content, ep, vid,
                    label=f"{ep}@@{vid}",
                )
                cache_file.write_bytes(raw)
            except Exception as exc:
                log.warning("Pre-fetch failed %s@@%s: %s", ep, vid, exc)

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(_fetch, work))

    def _enrich_commit(self, commit: dict) -> dict:
        """Fill in actual file content bytes (base64) into commit's file_changes."""
        enriched_changes: dict[str, dict] = {}

        for rel_path, change_meta in commit.get("file_changes", {}).items():
            if is_excluded_by_pattern(rel_path, self.cfg.exclude_patterns):
                continue

            version_id = change_meta.get("version_id")
            element_path = change_meta.get("element_path")

            # Deleted element (rmname/rmelem) — emit a delete, no content needed
            if change_meta.get("is_deleted"):
                enriched_changes[rel_path] = {
                    "content_b64": None, "deleted": True,
                    "is_executable": False, "is_symlink": False,
                    "symlink_target": None, "lfs": False,
                }
                continue

            if not version_id or not element_path:
                continue

            # Skip version 0 on any branch (directory creation pseudo-version)
            if version_id.endswith("/0"):
                continue

            enriched_changes[rel_path] = self._extract_version(
                rel_path, element_path, version_id, change_meta,
            )

        # Add .gitkeep for empty directories if configured
        if self.cfg.preserve_empty_dirs:
            enriched_changes = self._add_gitkeep_if_needed(enriched_changes)

        commit["file_changes"] = enriched_changes
        return commit

    def _extract_version(self, rel_path: str, element_path: str,
                           version_id: str, meta: dict) -> dict:
        """Extract one version and return an enriched change dict."""
        cache_key = hashlib.md5(f"{element_path}@@{version_id}".encode()).hexdigest()
        cache_file = self._cache_dir / cache_key

        if meta.get("is_symlink"):
            target = self.retry(
                self.cc.get_symlink_target, element_path, version_id,
                label=f"symlink:{element_path}",
            )
            return {
                "content_b64": None,
                "is_executable": False,
                "is_symlink": True,
                "symlink_target": target,
                "lfs": False,
                "deleted": False,
            }

        # Try cache first
        raw: Optional[bytes] = None
        if cache_file.exists():
            raw = cache_file.read_bytes()
        else:
            try:
                raw = self.retry(
                    self.cc.get_version_content, element_path, version_id,
                    label=f"{element_path}@@{version_id}",
                )
                cache_file.write_bytes(raw)
            except Exception as exc:
                log.error("Failed to extract %s@@%s: %s", element_path, version_id, exc)
                return {"content_b64": None, "is_executable": False,
                        "is_symlink": False, "symlink_target": None,
                        "lfs": False, "deleted": False, "error": str(exc)}

        if raw is None:
            return {"content_b64": None, "deleted": True,
                    "is_executable": False, "is_symlink": False,
                    "symlink_target": None, "lfs": False}

        # File mode / executable bit
        try:
            mode = self.cc.get_file_mode(element_path, version_id)
            is_exec = bool(mode & 0o111)
        except Exception:
            is_exec = False

        # C/Makefile analysis
        import base64
        suffix = Path(rel_path).suffix.lower()
        name_lower = Path(rel_path).name.lower()
        use_lfs = False

        if not is_binary(raw):
            if suffix in (".c", ".h", ".cpp", ".cxx", ".cc", ".hpp",
                          ".hxx", ".hh", ".C", ".H", ".inl", ".tcc",
                          ".pc", ".pcc"):
                analysis = self.c_agent.analyze(rel_path, raw)
                if analysis.rewritten_content is not None:
                    raw = analysis.rewritten_content
                if analysis.has_issues:
                    self._issues.setdefault(rel_path, []).extend([
                        {"kind": iss.kind, "detail": iss.detail, "line": iss.line}
                        for iss in analysis.issues
                    ])
                if analysis.is_derived_object:
                    if self.cfg.skip_derived_objects:
                        return {"content_b64": None, "deleted": False,
                                "skipped": True, "reason": "derived_object",
                                "is_executable": False, "is_symlink": False,
                                "symlink_target": None, "lfs": False}
            elif name_lower in ("makefile", "gnumakefile") or name_lower.endswith(".mk"):
                analysis = self.c_agent.analyze_makefile(rel_path, raw)
                if analysis.rewritten_content is not None:
                    raw = analysis.rewritten_content
                if analysis.has_issues:
                    self._issues.setdefault(rel_path, []).extend([
                        {"kind": iss.kind, "detail": iss.detail, "line": iss.line}
                        for iss in analysis.issues
                    ])
            elif name_lower in ("cmakelists.txt", "cmakelists.txt.in") or suffix in (".cmake",):
                analysis = self.c_agent.analyze_cmake(rel_path, raw)
                if analysis.rewritten_content is not None:
                    raw = analysis.rewritten_content
                if analysis.has_issues:
                    self._issues.setdefault(rel_path, []).extend([
                        {"kind": iss.kind, "detail": iss.detail, "line": iss.line}
                        for iss in analysis.issues
                    ])

        # LFS decision
        if self.cfg.git.use_lfs and should_use_lfs(
            raw, rel_path,
            self.cfg.git.lfs_threshold_mb,
            self.cfg.git.lfs_patterns,
        ):
            sha = self.lfs.add(raw)
            raw = lfs_pointer(raw)  # replace content with pointer
            use_lfs = True
            log.debug("LFS: %s → sha256:%s", rel_path, sha[:12])

        content_b64 = base64.b64encode(raw).decode()

        return {
            "content_b64": content_b64,
            "is_executable": is_exec,
            "is_symlink": False,
            "symlink_target": None,
            "lfs": use_lfs,
            "deleted": False,
        }

    def _add_gitkeep_if_needed(self, changes: dict[str, dict]) -> dict[str, dict]:
        """
        If a commit only creates directories (no files), add .gitkeep entries
        so git has something to track.
        This is a heuristic — we detect when a path is a dir-only change.
        """
        import base64
        dirs_only = all(
            c.get("content_b64") is None and not c.get("is_symlink") and not c.get("deleted")
            for c in changes.values()
        )
        if dirs_only and changes:
            first_dir = next(iter(changes))
            gitkeep_path = first_dir.rstrip("/") + "/.gitkeep"
            changes[gitkeep_path] = {
                "content_b64": base64.b64encode(b"").decode(),
                "is_executable": False,
                "is_symlink": False,
                "symlink_target": None,
                "lfs": False,
                "deleted": False,
            }
        return changes
