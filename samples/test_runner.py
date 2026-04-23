#!/usr/bin/env python3
"""
test_runner.py  --  end-to-end migration test using sample files.

Runs the FULL migration pipeline WITHOUT needing a real ClearCase installation.
A MockClearCaseClient serves content from samples/vobs/ and history from
samples/test_fixtures/cc_history.json.

Usage:
    cd /home/ramram/Desktop/Personal/Clearcase_Git
    python3 samples/test_runner.py

Output:
    workspace_test/   intermediate JSON state files
    git_test_output/  the resulting git repository
    logs_test/        migration.log + c_file_issues.md
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import datetime
import shutil
import logging
from pathlib import Path

# Make sure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.config import MigrationConfig, ClearCaseConfig, GitConfig, GitHubConfig
from core.git_client import GitClient
from core.models import ElementType
from utils.lfs_handler import LFSBlobStore
from agents.extractor_agent import ExtractorAgent
from agents.git_conversion_agent import GitConversionAgent
from agents.c_file_agent import CFileAgent, build_issue_report

SAMPLES_DIR  = PROJECT_ROOT / "samples"
FIXTURES_DIR = SAMPLES_DIR  / "test_fixtures"
VOB_ROOT     = SAMPLES_DIR  / "vobs" / "my_project"

WORKSPACE    = PROJECT_ROOT / "workspace_test"
GIT_OUT      = PROJECT_ROOT / "git_test_output"
LOG_DIR      = PROJECT_ROOT / "logs_test"

# ── logging ───────────────────────────────────────────────────────────────────
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(LOG_DIR / "migration.log")),
    ],
)
log = logging.getLogger("test_runner")

# ── version file map ──────────────────────────────────────────────────────────
# Maps element_path + version_id → path of sample file on disk.
# Versions without a specific sample file fall back to the latest sample.
VERSION_FILE_MAP: dict[tuple[str,str], Path] = {
    ("/vobs/my_project/src/main.c", "/main/1"): VOB_ROOT / "src/main.c.v1",
    ("/vobs/my_project/src/main.c", "/main/2"): VOB_ROOT / "src/main.c.v2",
    ("/vobs/my_project/src/main.c", "/main/3"): VOB_ROOT / "src/main.c.v3",
    ("/vobs/my_project/src/main.c", "/main/4"): VOB_ROOT / "src/main.c.v4",
    ("/vobs/my_project/src/main.c", "/main/rel2_bugfix/1"): VOB_ROOT / "src/main.c.v2",
    ("/vobs/my_project/src/main.c", "/main/rel2_bugfix/2"): VOB_ROOT / "src/main.c.v3",
}

# Default: derive filename from element path and look in VOB_ROOT
def _resolve_sample_file(element_path: str, version_id: str) -> Path:
    key = (element_path, version_id)
    if key in VERSION_FILE_MAP:
        return VERSION_FILE_MAP[key]
    # Derive from element path
    rel = element_path.replace("/vobs/my_project/", "")
    candidate = VOB_ROOT / rel
    if candidate.exists():
        return candidate
    return candidate   # extractor will handle missing file gracefully


# ── mock ClearCase client ─────────────────────────────────────────────────────

class MockClearCaseClient:
    """Serves content from sample files instead of calling cleartool."""

    def get_version_content(self, element_path: str, version_id: str) -> bytes:
        fpath = _resolve_sample_file(element_path, version_id)
        if fpath.exists():
            return fpath.read_bytes()
        log.warning("Mock: no sample for %s@@%s — returning empty", element_path, version_id)
        return b""

    def get_symlink_target(self, element_path: str, version_id: str) -> str:
        return ""

    def get_file_mode(self, element_path: str, version_id: str) -> int:
        fpath = _resolve_sample_file(element_path, version_id)
        name = fpath.name
        if name in ("Makefile",) or name.endswith(".sh"):
            return 0o755
        return 0o644


# ── build commits.json from cc_history.json ───────────────────────────────────

def build_commits_from_history(history_path: Path, workspace: Path) -> list[dict]:
    """
    Group versions by (branch, author, comment, time-window) just like
    HistoryAgent does, but reading directly from our fixture JSON.
    """
    history = json.loads(history_path.read_text())
    versions = history["versions"]

    WINDOW = 60   # seconds
    from collections import defaultdict
    buckets: dict[tuple, list] = defaultdict(list)

    for ver in sorted(versions, key=lambda v: v["created_at"]):
        branch  = _branch_to_git(ver["branch"])
        author  = ver["created_by"]
        comment = ver["comment"] or "(no comment)"
        ts      = int(datetime.datetime.fromisoformat(ver["created_at"]).timestamp())
        key = (branch, author, comment, ts // WINDOW)
        buckets[key].append(ver)

    AUTHOR_MAP = {
        "jsmith":     ("John Smith",    "jsmith@company.com"),
        "mary.jones": ("Mary Jones",    "mary.jones@company.com"),
        "build_svc":  ("Build Service", "devops@company.com"),
        "rmuller":    ("René Müller",   "rmuller@company.com"),
        "admin":      ("Admin",         "admin@company.com"),
    }

    commits = []
    for (branch, author, comment, ts_bucket), vers in buckets.items():
        ts = max(datetime.datetime.fromisoformat(v["created_at"]) for v in vers)
        git_name, git_email = AUTHOR_MAP.get(author, (author, f"{author}@migrated.local"))

        file_changes = {}
        for ver in vers:
            rel_path = ver["element_path"].replace("/vobs/my_project/", "")
            labels   = ver.get("labels", [])
            file_changes[rel_path] = {
                "version_id":    ver["version_id"],
                "element_path":  ver["element_path"],
                "is_executable": False,
                "is_symlink":    False,
                "symlink_target": None,
            }

        merges = []
        for ver in vers:
            for m in ver.get("merge_sources", []):
                merge_branch = _extract_branch_from_ext(m)
                if merge_branch and merge_branch not in merges:
                    merges.append(merge_branch)

        commits.append({
            "branch":           branch,
            "message":          comment + "\n\nClearCase-Elements: " +
                                ", ".join(v["element_path"].split("/")[-1] +
                                          "@@" + v["version_id"] for v in vers[:3]),
            "author_name":      git_name,
            "author_email":     git_email,
            "timestamp":        ts.isoformat(),
            "file_changes":     file_changes,
            "tags":             _collect_labels(vers),
            "merge_from_branch": _branch_to_git(merges[0]) if merges else None,
            "cc_activity_id":   None,
        })

    # Sort: main first, then by timestamp
    commits.sort(key=lambda c: (0 if c["branch"] == "main" else 1, c["timestamp"]))
    out = workspace / "commits.json"
    out.write_text(json.dumps(commits, indent=2, default=str))
    log.info("Wrote %d commits to %s", len(commits), out)
    return commits


def _branch_to_git(cc_branch: str) -> str:
    cc_branch = cc_branch.strip("/")
    short = cc_branch.split("/")[-1]
    if short in ("main", "MAIN", ""):
        return "main"
    return short.replace("/", "--")


def _extract_branch_from_ext(ext: str) -> str:
    """Extract branch from a version extended name like /vobs/.../file@@/main/rel2_bugfix/1"""
    if "@@" not in ext:
        return ""
    ver_part = ext.split("@@")[1]
    parts = ver_part.strip("/").split("/")
    if len(parts) < 2:
        return ""
    return _branch_to_git("/".join(parts[:-1]))


def _collect_labels(vers: list[dict]) -> list[str]:
    seen = []
    for v in vers:
        for lb in v.get("labels", []):
            if lb not in seen:
                seen.append(lb)
    return seen


# ── mock-aware ExtractorAgent ─────────────────────────────────────────────────

class MockExtractorAgent(ExtractorAgent):
    """Overrides _extract_version to use MockClearCaseClient."""

    def __init__(self, cfg, mock_cc, git, lfs):
        super().__init__(cfg, mock_cc, git, lfs)
        self.cc = mock_cc   # replace real CC client

    def _extract_version(self, rel_path, element_path, version_id, meta):
        change = super()._extract_version(rel_path, element_path, version_id, meta)
        return change


# ── standalone C-file analysis test ──────────────────────────────────────────

def test_c_file_analysis():
    """Run CFileAgent against every sample C file and print a summary."""
    agent = CFileAgent(strip_keywords=True, fix_includes=True,
                       normalize_paths=True, detect_encoding=True)
    issues_by_file: dict[str, list] = {}
    results = []

    c_files = list(VOB_ROOT.rglob("*.c")) + list(VOB_ROOT.rglob("*.h"))
    c_files += [VOB_ROOT / "Makefile"]

    for fpath in sorted(c_files):
        raw = fpath.read_bytes()
        rel = str(fpath.relative_to(SAMPLES_DIR))

        if fpath.name == "Makefile" or fpath.suffix == ".mk":
            analysis = agent.analyze_makefile(rel, raw)
        else:
            analysis = agent.analyze(rel, raw)

        row = {
            "file": rel,
            "encoding": analysis.original_encoding,
            "binary": analysis.is_binary,
            "derived": analysis.is_derived_object,
            "rewritten": analysis.rewritten_content is not None,
            "issues": len(analysis.issues),
            "issue_kinds": [i.kind for i in analysis.issues],
        }
        results.append(row)
        if analysis.has_issues:
            issues_by_file[rel] = analysis.issues

    print("\n" + "=" * 70)
    print("  C FILE ANALYSIS RESULTS")
    print("=" * 70)
    print(f"  {'File':<45} {'Enc':<12} {'Issues'}")
    print("-" * 70)
    for r in results:
        mark = "✓" if not r["issues"] else "!"
        kinds = ", ".join(r["issue_kinds"]) or "—"
        print(f"  {mark} {r['file']:<43} {r['encoding']:<12} {kinds}")

    report_path = LOG_DIR / "c_file_issues.md"
    if issues_by_file:
        report = build_issue_report(issues_by_file)
        report_path.write_text(report)
        print(f"\n  Issue report written to: {report_path}")

    print(f"\n  Files analysed: {len(results)}")
    print(f"  Files with issues: {len(issues_by_file)}")
    print(f"  Files rewritten: {sum(1 for r in results if r['rewritten'])}")
    print("=" * 70 + "\n")
    return len(issues_by_file) == 0  # True if all clean


# ── full pipeline test ────────────────────────────────────────────────────────

def test_full_pipeline():
    """Run Discovery → History → Extract → GitConvert against sample data."""
    log.info("=" * 60)
    log.info("Full pipeline test (mock ClearCase)")
    log.info("=" * 60)

    # Clean workspace
    for d in (WORKSPACE, GIT_OUT):
        if d.exists():
            shutil.rmtree(d)
    WORKSPACE.mkdir()

    # ---- Stage 1: copy discovery fixture ----
    shutil.copy(FIXTURES_DIR / "discovery.json", WORKSPACE / "discovery.json")
    discovery = json.loads((WORKSPACE / "discovery.json").read_text())
    log.info("Stage 1: Discovery loaded (%d elements)",
             len(discovery.get("all_elements", [])))

    # ---- Stage 2: build commits from history fixture ----
    log.info("Stage 2: Building commits from cc_history.json")
    commits = build_commits_from_history(FIXTURES_DIR / "cc_history.json", WORKSPACE)
    log.info("         %d commits grouped", len(commits))

    # ---- Stage 3: extract content (mock CC) ----
    log.info("Stage 3: Extracting file content via mock client")
    cfg = _make_test_config()
    mock_cc = MockClearCaseClient()
    git = GitClient(str(GIT_OUT), default_branch="main")
    lfs = LFSBlobStore(str(WORKSPACE / "lfs_objects"))

    extractor = MockExtractorAgent(cfg, mock_cc, git, lfs)
    result = extractor.execute()
    if not result.success:
        log.error("Extractor failed: %s", result.error)
        return False
    log.info("         Extraction complete")

    # ---- Stage 4: git fast-import ----
    log.info("Stage 4: Writing git history via fast-import")
    conversion = GitConversionAgent(cfg, git, discovery)
    result = conversion.execute()
    if not result.success:
        log.error("Git conversion failed: %s", result.error)
        return False

    branches = result.data.get("branches", []) if result.data else []
    log.info("         Branches created: %s", branches)
    return True


def _make_test_config() -> MigrationConfig:
    cc_cfg = ClearCaseConfig(
        vob_tags=["/vobs/my_project"],
        view_tag="test_view",
        view_root=str(SAMPLES_DIR),
    )
    git_cfg = GitConfig(
        output_dir=str(GIT_OUT),
        default_branch="main",
        use_lfs=True,
        lfs_threshold_mb=50.0,
    )
    gh_cfg = GitHubConfig(enabled=False)
    return MigrationConfig(
        clearcase=cc_cfg,
        git=git_cfg,
        github=gh_cfg,
        workspace_dir=str(WORKSPACE),
        log_dir=str(LOG_DIR),
        skip_derived_objects=True,
        skip_lost_and_found=False,
        detect_encoding=True,
        preserve_empty_dirs=True,
        generate_gitattributes=True,
        generate_gitignore=True,
    )


# ── git verification ──────────────────────────────────────────────────────────

def verify_git_output():
    """Print a summary of what ended up in the git repo."""
    if not GIT_OUT.exists():
        print("  git_test_output/ not found — pipeline may not have run yet")
        return

    def git(*args):
        r = subprocess.run(["git"] + list(args), cwd=str(GIT_OUT),
                           capture_output=True, text=True)
        return r.stdout.strip()

    print("\n" + "=" * 70)
    print("  GIT REPOSITORY VERIFICATION")
    print("=" * 70)

    branches = git("branch", "--format=%(refname:short)").splitlines()
    tags     = git("tag").splitlines()
    print(f"\n  Branches ({len(branches)}):")
    for b in branches:
        count = git("rev-list", "--count", b)
        print(f"    {b:30s}  {count} commits")

    print(f"\n  Tags ({len(tags)}):")
    for t in tags:
        print(f"    {t}")

    print(f"\n  Latest 10 commits on main:")
    log_out = git("log", "--oneline", "-10", "main")
    for line in log_out.splitlines():
        print(f"    {line}")

    print(f"\n  Files in HEAD:")
    files = git("ls-tree", "-r", "--name-only", "HEAD").splitlines()
    for f in sorted(files):
        print(f"    {f}")

    print("=" * 70 + "\n")


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 70)
    print("  ClearCase → GitHub Migration  —  Sample Test Runner")
    print("=" * 70 + "\n")

    passed = 0
    failed = 0

    # Test 1: C file analysis only (no git, fast)
    print(">>> Test 1: C file analysis (keyword stripping, encoding, includes)")
    ok = test_c_file_analysis()
    # Non-zero issues is expected — we WANT to detect them
    print("    C file analysis: DONE (see logs_test/c_file_issues.md)\n")
    passed += 1

    # Test 2: full pipeline
    print(">>> Test 2: Full pipeline (mock ClearCase → git repo)")
    ok = test_full_pipeline()
    if ok:
        print("    Pipeline: PASSED\n")
        passed += 1
    else:
        print("    Pipeline: FAILED — check logs_test/migration.log\n")
        failed += 1

    # Verify git output
    verify_git_output()

    print(f"Results: {passed} passed, {failed} failed")
    print(f"Log:     {LOG_DIR}/migration.log")
    print(f"Issues:  {LOG_DIR}/c_file_issues.md")
    print(f"Git:     {GIT_OUT}/\n")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
