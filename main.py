#!/usr/bin/env python3
"""
ClearCase → GitHub Multi-Agent Migration Pipeline
==================================================

Orchestrates five specialized agents in sequence:
  1. DiscoveryAgent   — maps VOB structure (branches, labels, elements)
  2. HistoryAgent     — extracts element versions and groups into git commits
  3. ExtractorAgent   — fetches file content, handles C files & LFS
  4. GitConversionAgent — writes full git history via git fast-import
  5. PublisherAgent   — creates GitHub repo and pushes

Run: python3 main.py --config config.yaml [--dry-run] [--resume]
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
import time
from pathlib import Path

from core.config import load_config, validate_config
from core.clearcase_client import ClearCaseClient
from core.git_client import GitClient
from utils.lfs_handler import LFSBlobStore
from agents.discovery_agent import DiscoveryAgent
from agents.history_agent import HistoryAgent
from agents.extractor_agent import ExtractorAgent
from agents.git_conversion_agent import GitConversionAgent
from agents.publisher_agent import PublisherAgent


def setup_logging(log_dir: str, debug: bool = False) -> None:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if debug else logging.INFO
    fmt = "%(asctime)s %(levelname)-8s %(name)s — %(message)s"
    logging.basicConfig(
        level=level,
        format=fmt,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(str(Path(log_dir) / "migration.log")),
        ],
    )


def load_author_map(path: str) -> dict[str, tuple[str, str]]:
    """Load CSV: cc_username,Git Full Name,git@email.com"""
    if not path or not Path(path).exists():
        return {}
    result: dict[str, tuple[str, str]] = {}
    with open(path, newline="") as fh:
        for row in csv.reader(fh):
            if len(row) >= 3 and not row[0].startswith("#"):
                result[row[0].strip()] = (row[1].strip(), row[2].strip())
    return result


def progress_callback(agent: str, message: str, current: int, total: int) -> None:
    pct = f" ({current}/{total})" if total else ""
    print(f"  [{agent}]{pct} {message}", flush=True)


def run_pipeline(config_path: str, dry_run: bool = False,
                  resume: bool = True, skip_to: str = "") -> bool:
    log = logging.getLogger("main")

    # ── load and validate config ──────────────────────────────────────────────
    cfg = load_config(config_path)
    cfg.dry_run = dry_run or cfg.dry_run
    cfg.resume = resume and cfg.resume

    errors = validate_config(cfg)
    if errors:
        for err in errors:
            log.error("Config error: %s", err)
        return False

    log.info("=" * 60)
    log.info("ClearCase → GitHub Migration Pipeline")
    log.info("VOBs: %s", cfg.clearcase.vob_tags)
    log.info("Output: %s", cfg.git.output_dir)
    log.info("Dry-run: %s  Resume: %s", cfg.dry_run, cfg.resume)
    log.info("=" * 60)

    # ── shared clients ────────────────────────────────────────────────────────
    cc = ClearCaseClient(
        view_tag=cfg.clearcase.view_tag,
        view_root=cfg.clearcase.view_root,
        vob_tags=cfg.clearcase.vob_tags,
    )
    git = GitClient(cfg.git.output_dir, default_branch=cfg.git.default_branch)
    lfs = LFSBlobStore(str(Path(cfg.workspace_dir) / "lfs_objects"))
    author_map = load_author_map(cfg.git.author_map_file)

    # Start the ClearCase view
    if not cfg.dry_run:
        try:
            cc.start_view()
        except Exception as exc:
            log.warning("Could not start view (may already be running): %s", exc)

    # ── Stage 1: Discovery ────────────────────────────────────────────────────
    stage("1. Discovery", log)
    discovery_agent = DiscoveryAgent(cfg, cc)
    discovery_agent.add_progress_callback(progress_callback)

    discovery_path = Path(cfg.workspace_dir) / "discovery.json"
    if cfg.resume and discovery_path.exists() and skip_to not in ("discovery",):
        log.info("Resuming — using existing discovery.json")
        discovery = json.loads(discovery_path.read_text())
    else:
        result = discovery_agent.execute()
        if not result.success:
            log.error("Discovery failed: %s", result.error)
            return False
        discovery = result.data

    # ── Stage 2: History ──────────────────────────────────────────────────────
    stage("2. History extraction & commit grouping", log)
    history_agent = HistoryAgent(cfg, cc, discovery, author_map)
    history_agent.add_progress_callback(progress_callback)

    commits_path = Path(cfg.workspace_dir) / "commits.json"
    if cfg.resume and commits_path.exists() and skip_to not in ("discovery", "history"):
        log.info("Resuming — using existing commits.json")
    else:
        result = history_agent.execute()
        if not result.success:
            log.error("History extraction failed: %s", result.error)
            return False

    # ── Stage 3: Content extraction ───────────────────────────────────────────
    stage("3. File content extraction (C files, LFS, encoding)", log)
    extractor_agent = ExtractorAgent(cfg, cc, git, lfs)
    extractor_agent.add_progress_callback(progress_callback)

    enriched_path = Path(cfg.workspace_dir) / "enriched_commits.json"
    if cfg.resume and enriched_path.exists() and skip_to not in ("discovery", "history", "extract"):
        log.info("Resuming — using existing enriched_commits.json")
    else:
        result = extractor_agent.execute()
        if not result.success:
            log.error("Extraction failed: %s", result.error)
            return False

    # ── Stage 4: Git conversion ───────────────────────────────────────────────
    stage("4. Git history construction (fast-import)", log)
    conversion_agent = GitConversionAgent(cfg, git, discovery)
    conversion_agent.add_progress_callback(progress_callback)

    result = conversion_agent.execute()
    if not result.success:
        log.error("Git conversion failed: %s", result.error)
        return False

    branches = result.data.get("branches", []) if result.data else []
    log.info("Git repo built with %d branches: %s", len(branches), branches)

    # ── Stage 5: GitHub publish ───────────────────────────────────────────────
    stage("5. GitHub publish", log)
    publisher_agent = PublisherAgent(cfg, git)
    publisher_agent.add_progress_callback(progress_callback)

    result = publisher_agent.execute()
    if not result.success:
        log.error("GitHub publish failed: %s", result.error)
        return False

    if result.data and not result.data.get("skipped"):
        log.info("Published to: %s", result.data.get("repo_url"))

    log.info("=" * 60)
    log.info("Migration pipeline COMPLETE")
    log.info("=" * 60)
    return True


def stage(label: str, log: logging.Logger) -> None:
    log.info("")
    log.info("─" * 55)
    log.info("  Stage: %s", label)
    log.info("─" * 55)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ClearCase → GitHub multi-agent migration pipeline",
    )
    parser.add_argument("--config", default="config.yaml",
                        help="Path to config.yaml (default: config.yaml)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse and plan without writing git history or pushing")
    parser.add_argument("--no-resume", action="store_true",
                        help="Start fresh, ignoring any saved state")
    parser.add_argument("--skip-to", default="",
                        choices=["", "history", "extract", "convert", "publish"],
                        help="Skip ahead to a later stage (requires prior stage outputs)")
    parser.add_argument("--debug", action="store_true",
                        help="Enable DEBUG logging")
    args = parser.parse_args()

    # Peek at config just for log_dir
    try:
        _cfg = load_config(args.config)
        log_dir = _cfg.log_dir
    except Exception:
        log_dir = "logs"

    setup_logging(log_dir, debug=args.debug)
    log = logging.getLogger("main")

    start = time.time()
    ok = run_pipeline(
        config_path=args.config,
        dry_run=args.dry_run,
        resume=not args.no_resume,
        skip_to=args.skip_to,
    )
    elapsed = time.time() - start
    log.info("Total time: %.0f seconds", elapsed)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
