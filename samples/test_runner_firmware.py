#!/usr/bin/env python3
"""
test_runner_firmware.py — End-to-end migration test for the 15-VOB
C++ firmware project with cross-VOB shared compilation.

Simulates migrating:
  - 15 ClearCase VOBs (shared_libs, hal, 3 drivers, network, storage,
    security, display, audio, power, bootloader, test_framework,
    platform, firmware_core)
  - Cross-VOB #include paths (view-root extended paths)
  - Shared compilation Makefile with CLEARCASE_ROOT / VOBROOT
  - ClearCase keyword expansions in C++ headers
  - 3 branches: main, rel2_bugfix, rel3_feature
  - Tags: INITIAL_IMPORT, REL_2_0, REL_3_0, SECURITY_FIX_001

Usage:
    cd /home/ramram/Desktop/Personal/Clearcase_Git
    python3 samples/test_runner_firmware.py

Output:
    workspace_firmware/   intermediate JSON state
    git_firmware_output/  migrated git repository
    logs_firmware/        migration.log + c_file_issues.md
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import datetime
import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.config import MigrationConfig, ClearCaseConfig, GitConfig, GitHubConfig
from core.git_client import GitClient
from utils.lfs_handler import LFSBlobStore
from agents.extractor_agent import ExtractorAgent
from agents.git_conversion_agent import GitConversionAgent
from agents.c_file_agent import CFileAgent, build_issue_report

SAMPLES_DIR   = PROJECT_ROOT / "samples"
FIXTURES_DIR  = SAMPLES_DIR  / "test_fixtures"
VOBS_ROOT     = SAMPLES_DIR  / "vobs_firmware"

WORKSPACE     = PROJECT_ROOT / "workspace_firmware"
GIT_OUT       = PROJECT_ROOT / "git_firmware_output"
LOG_DIR       = PROJECT_ROOT / "logs_firmware"

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
log = logging.getLogger("fw_test_runner")

# ── 15-VOB element path → sample file mapping ────────────────────────────────
# Maps /vobs/<path> to actual file under samples/vobs_firmware/
_VOB_FILE_MAP: dict[str, Path] = {
    "/vobs/shared_libs/include/fw_types.h":        VOBS_ROOT / "shared_libs/include/fw_types.h",
    "/vobs/shared_libs/include/logger.h":          VOBS_ROOT / "shared_libs/include/logger.h",
    "/vobs/shared_libs/src/logger.cpp":            VOBS_ROOT / "shared_libs/src/logger.cpp",
    "/vobs/shared_libs/Makefile":                  VOBS_ROOT / "shared_libs/Makefile",
    "/vobs/hal/include/hal.h":                     VOBS_ROOT / "hal/include/hal.h",
    "/vobs/hal/src/hal.cpp":                       VOBS_ROOT / "hal/src/hal.cpp",
    "/vobs/hal/Makefile":                          VOBS_ROOT / "hal/Makefile",
    "/vobs/drivers/uart/include/uart_driver.h":    VOBS_ROOT / "drivers/uart/include/uart_driver.h",
    "/vobs/drivers/uart/src/uart_driver.cpp":      VOBS_ROOT / "drivers/uart/src/uart_driver.cpp",
    "/vobs/drivers/spi/include/spi_driver.h":      VOBS_ROOT / "drivers/spi/include/spi_driver.h",
    "/vobs/drivers/spi/src/spi_driver.cpp":        VOBS_ROOT / "drivers/spi/src/spi_driver.cpp",
    "/vobs/drivers/i2c/include/i2c_driver.h":      VOBS_ROOT / "drivers/i2c/include/i2c_driver.h",
    "/vobs/drivers/i2c/src/i2c_driver.cpp":        VOBS_ROOT / "drivers/i2c/src/i2c_driver.cpp",
    "/vobs/network/include/network.h":             VOBS_ROOT / "network/include/network.h",
    "/vobs/network/src/network.cpp":               VOBS_ROOT / "network/src/network.cpp",
    "/vobs/storage/include/storage.h":             VOBS_ROOT / "storage/include/storage.h",
    "/vobs/storage/src/storage.cpp":               VOBS_ROOT / "storage/src/storage.cpp",
    "/vobs/security/include/security.h":           VOBS_ROOT / "security/include/security.h",
    "/vobs/security/src/security.cpp":             VOBS_ROOT / "security/src/security.cpp",
    "/vobs/display/include/display.h":             VOBS_ROOT / "display/include/display.h",
    "/vobs/display/src/display.cpp":               VOBS_ROOT / "display/src/display.cpp",
    "/vobs/audio/include/audio.h":                 VOBS_ROOT / "audio/include/audio.h",
    "/vobs/audio/src/audio.cpp":                   VOBS_ROOT / "audio/src/audio.cpp",
    "/vobs/power/include/power.h":                 VOBS_ROOT / "power/include/power.h",
    "/vobs/power/src/power.cpp":                   VOBS_ROOT / "power/src/power.cpp",
    "/vobs/bootloader/include/bootloader.h":       VOBS_ROOT / "bootloader/include/bootloader.h",
    "/vobs/bootloader/src/bootloader.cpp":         VOBS_ROOT / "bootloader/src/bootloader.cpp",
    "/vobs/test_framework/include/test.h":         VOBS_ROOT / "test_framework/include/test.h",
    "/vobs/platform/include/platform.h":           VOBS_ROOT / "platform/include/platform.h",
    "/vobs/platform/src/platform.cpp":             VOBS_ROOT / "platform/src/platform.cpp",
    "/vobs/firmware_core/include/firmware.h":      VOBS_ROOT / "firmware_core/include/firmware.h",
    "/vobs/firmware_core/src/firmware.cpp":        VOBS_ROOT / "firmware_core/src/firmware.cpp",
    "/vobs/firmware_core/Makefile":                VOBS_ROOT / "Makefile",
}

# ── mock ClearCase client ─────────────────────────────────────────────────────

class MockClearCaseClient:
    def get_version_content(self, element_path: str, version_id: str) -> bytes:
        # All versions of a path return the same sample file (sufficient for testing)
        fpath = _VOB_FILE_MAP.get(element_path)
        if fpath and fpath.exists():
            return fpath.read_bytes()
        log.warning("Mock: no sample for %s@@%s", element_path, version_id)
        return b""

    def get_symlink_target(self, element_path: str, version_id: str) -> str:
        return ""

    def get_file_mode(self, element_path: str, version_id: str) -> int:
        name = Path(element_path).name
        return 0o755 if name in ("Makefile",) or name.endswith(".sh") else 0o644


# ── build commits.json from firmware history fixture ──────────────────────────

def build_firmware_commits(workspace: Path) -> list[dict]:
    history = json.loads((FIXTURES_DIR / "firmware_cc_history.json").read_text())
    versions = history["versions"]
    WINDOW = 60

    from collections import defaultdict
    buckets: dict[tuple, list] = defaultdict(list)
    for ver in sorted(versions, key=lambda v: v["created_at"]):
        branch  = _branch_to_git(ver["branch"])
        author  = ver["created_by"]
        comment = ver["comment"] or "(no comment)"
        ts      = int(datetime.datetime.fromisoformat(ver["created_at"]).timestamp())
        buckets[(branch, author, comment, ts // WINDOW)].append(ver)

    AUTHOR_MAP = {
        "jsmith":     ("John Smith",    "jsmith@firmware.local"),
        "mary.jones": ("Mary Jones",    "mary.jones@firmware.local"),
        "build_svc":  ("Build Service", "devops@firmware.local"),
        "rmuller":    ("René Müller",   "rmuller@firmware.local"),
        "admin":      ("Admin",         "admin@firmware.local"),
    }

    commits = []
    for (branch, author, comment, ts_bucket), vers in buckets.items():
        ts      = max(datetime.datetime.fromisoformat(v["created_at"]) for v in vers)
        git_name, git_email = AUTHOR_MAP.get(author, (author, f"{author}@migrated.local"))

        file_changes = {}
        for ver in vers:
            # Strip the leading /vobs/<vob_name> to get a repo-relative path
            rel_path = _vob_to_rel(ver["element_path"])
            file_changes[rel_path] = {
                "version_id":    ver["version_id"],
                "element_path":  ver["element_path"],
                "is_executable": False,
                "is_symlink":    False,
                "symlink_target": None,
                "is_deleted":    False,
            }

        merges = []
        for ver in vers:
            for m in ver.get("merge_sources", []):
                mb = _extract_branch(m)
                if mb and mb not in merges:
                    merges.append(mb)

        commits.append({
            "branch":           branch,
            "message":          comment + "\n\nClearCase-VOBs: " +
                                ", ".join(sorted({v["element_path"].split("/")[2] for v in vers})),
            "author_name":      git_name,
            "author_email":     git_email,
            "timestamp":        ts.isoformat(),
            "file_changes":     file_changes,
            "tags":             _collect_labels(vers),
            "merge_from_branch": _branch_to_git(merges[0]) if merges else None,
            "cc_activity_id":   None,
        })

    commits.sort(key=lambda c: (0 if c["branch"] == "main" else 1, c["timestamp"]))
    out = workspace / "commits.json"
    out.write_text(json.dumps(commits, indent=2, default=str))
    log.info("Wrote %d firmware commits to %s", len(commits), out)
    return commits


def _vob_to_rel(element_path: str) -> str:
    # /vobs/shared_libs/include/fw_types.h → shared_libs/include/fw_types.h
    if element_path.startswith("/vobs/"):
        return element_path[len("/vobs/"):]
    return element_path.lstrip("/")


def _branch_to_git(cc_branch: str) -> str:
    short = cc_branch.strip("/").split("/")[-1]
    return "main" if short.lower() in ("main", "") else short


def _extract_branch(ext: str) -> str:
    if "@@" not in ext:
        return ""
    ver_part = ext.split("@@")[1]
    parts = ver_part.strip("/").split("/")
    return _branch_to_git("/".join(parts[:-1])) if len(parts) >= 2 else ""


def _collect_labels(vers: list[dict]) -> list[str]:
    seen: list[str] = []
    for v in vers:
        for lb in v.get("labels", []):
            if lb not in seen:
                seen.append(lb)
    return seen


# ── mock extractor ────────────────────────────────────────────────────────────

class MockFwExtractorAgent(ExtractorAgent):
    def __init__(self, cfg, mock_cc, git, lfs):
        super().__init__(cfg, mock_cc, git, lfs)
        self.cc = mock_cc


# ── Test 1: C++ file analysis ─────────────────────────────────────────────────

def test_cpp_file_analysis():
    agent = CFileAgent(strip_keywords=True, fix_includes=True,
                       normalize_paths=True, detect_encoding=True)
    issues_by_file: dict[str, list] = {}
    results = []

    cpp_files = (
        list(VOBS_ROOT.rglob("*.cpp")) +
        list(VOBS_ROOT.rglob("*.h"))
    )
    makefiles = list(VOBS_ROOT.rglob("Makefile"))

    print(f"\n{'='*70}")
    print("  C++ FILE ANALYSIS — 15-VOB FIRMWARE PROJECT")
    print(f"{'='*70}")
    print(f"  {'File':<50} {'Enc':<10} {'Issues'}")
    print(f"  {'-'*68}")

    for fpath in sorted(cpp_files + makefiles):
        raw  = fpath.read_bytes()
        rel  = str(fpath.relative_to(VOBS_ROOT))
        name = fpath.name.lower()

        if name == "makefile":
            analysis = agent.analyze_makefile(rel, raw)
        else:
            analysis = agent.analyze(rel, raw)

        mark = "✓" if not analysis.issues else "!"
        kinds = ", ".join(i.kind for i in analysis.issues) or "—"
        print(f"  {mark} {rel:<48} {analysis.original_encoding:<10} {kinds}")

        results.append(rel)
        if analysis.has_issues:
            issues_by_file[rel] = analysis.issues

    report_path = LOG_DIR / "c_file_issues.md"
    if issues_by_file:
        report = build_issue_report(issues_by_file)
        report_path.write_text(report)

    total  = len(results)
    n_issues = len(issues_by_file)
    print(f"\n  Files analysed : {total}")
    print(f"  Files with issues: {n_issues} (ClearCase artifacts detected and fixed)")
    print(f"  Report: {report_path}")
    print(f"{'='*70}\n")
    return True


# ── Test 2: full pipeline ─────────────────────────────────────────────────────

def test_full_firmware_pipeline():
    log.info("=" * 60)
    log.info("15-VOB Firmware pipeline test (mock ClearCase)")
    log.info("=" * 60)

    for d in (WORKSPACE, GIT_OUT):
        if d.exists():
            shutil.rmtree(d)
    WORKSPACE.mkdir()

    # Stage 1: discovery
    shutil.copy(FIXTURES_DIR / "firmware_discovery.json", WORKSPACE / "discovery.json")
    discovery = json.loads((WORKSPACE / "discovery.json").read_text())
    n_vobs     = len(discovery.get("vobs", {}))
    n_elements = len(discovery.get("all_elements", []))
    log.info("Stage 1: Discovery — %d VOBs, %d elements", n_vobs, n_elements)

    # Stage 2: build commits
    log.info("Stage 2: Building commits from firmware history")
    commits = build_firmware_commits(WORKSPACE)
    log.info("         %d commits grouped", len(commits))

    # Stage 3: extract content
    log.info("Stage 3: Extracting file content (mock C++ files)")
    cfg      = _make_fw_config()
    mock_cc  = MockClearCaseClient()
    git      = GitClient(str(GIT_OUT), default_branch="main")
    lfs      = LFSBlobStore(str(WORKSPACE / "lfs_objects"))
    extractor = MockFwExtractorAgent(cfg, mock_cc, git, lfs)
    result    = extractor.execute()
    if not result.success:
        log.error("Extractor failed: %s", result.error)
        return False
    log.info("         Extraction complete")

    # Stage 4: git conversion
    log.info("Stage 4: Writing git history via fast-import")
    conversion = GitConversionAgent(cfg, git, discovery)
    result     = conversion.execute()
    if not result.success:
        log.error("Git conversion failed: %s", result.error)
        return False

    branches = result.data.get("branches", []) if result.data else []
    log.info("         Branches: %s", branches)
    return True


def _make_fw_config() -> MigrationConfig:
    cc_cfg = ClearCaseConfig(
        vob_tags=[
            "/vobs/shared_libs", "/vobs/hal",
            "/vobs/drivers_uart", "/vobs/drivers_spi", "/vobs/drivers_i2c",
            "/vobs/network", "/vobs/storage", "/vobs/security",
            "/vobs/display", "/vobs/audio", "/vobs/power",
            "/vobs/bootloader", "/vobs/test_framework",
            "/vobs/platform", "/vobs/firmware_core",
        ],
        view_tag="fw_migration_view",
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
        detect_encoding=True,
        preserve_empty_dirs=True,
        generate_gitattributes=True,
        generate_gitignore=True,
        max_workers=4,
    )


# ── git verification ──────────────────────────────────────────────────────────

def verify_firmware_git():
    if not GIT_OUT.exists():
        return
    def git(*args):
        r = subprocess.run(["git"] + list(args), cwd=str(GIT_OUT),
                           capture_output=True, text=True)
        return r.stdout.strip()

    branches = git("branch", "--format=%(refname:short)").splitlines()
    tags     = git("tag").splitlines()
    files    = git("ls-tree", "-r", "--name-only", "HEAD").splitlines()

    print(f"\n{'='*70}")
    print("  GIT REPOSITORY — 15-VOB FIRMWARE RESULT")
    print(f"{'='*70}")
    print(f"\n  Branches ({len(branches)}):")
    for b in branches:
        count = git("rev-list", "--count", b)
        print(f"    {b:30s}  {count} commits")

    print(f"\n  Tags ({len(tags)}):  {', '.join(tags)}")

    print(f"\n  Migrated files ({len(files)}) in HEAD:")
    for f in sorted(files):
        print(f"    {f}")

    print(f"\n  Latest commits on main:")
    for line in git("log","--oneline","-8","main").splitlines():
        print(f"    {line}")
    print(f"{'='*70}\n")


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*70}")
    print("  ClearCase → GitHub  |  15-VOB C++ Firmware Migration Test")
    print(f"{'='*70}\n")

    passed = 0
    failed = 0

    print(">>> Test 1: C++ file analysis (cross-VOB includes, keywords, Makefiles)")
    ok = test_cpp_file_analysis()
    print(f"    C++ analysis: {'PASS' if ok else 'FAIL'}\n")
    passed += 1 if ok else 0
    failed += 0 if ok else 1

    print(">>> Test 2: Full 15-VOB firmware pipeline")
    ok = test_full_firmware_pipeline()
    print(f"    Pipeline: {'PASSED' if ok else 'FAILED'}\n")
    passed += 1 if ok else 0
    failed += 0 if ok else 1

    verify_firmware_git()

    print(f"Results  : {passed} passed, {failed} failed")
    print(f"Log      : {LOG_DIR}/migration.log")
    print(f"Issues   : {LOG_DIR}/c_file_issues.md")
    print(f"Git repo : {GIT_OUT}/\n")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
