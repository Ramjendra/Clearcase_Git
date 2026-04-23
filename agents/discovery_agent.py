"""
Discovery Agent — scans VOBs to build a complete map of:
  - Elements (files, dirs, symlinks)
  - Branches and their hierarchy
  - Labels / Baselines
  - UCM Streams and Activities

Output is persisted to workspace/discovery.json for use by downstream agents.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from .base_agent import BaseAgent, AgentResult
from core.clearcase_client import ClearCaseClient
from core.config import MigrationConfig
from core.models import VOBInfo, MigrationStatus
from utils.path_sanitizer import is_lost_and_found

log = logging.getLogger(__name__)


class DiscoveryAgent(BaseAgent):
    name = "discovery"

    def __init__(self, cfg: MigrationConfig, cc: ClearCaseClient):
        super().__init__(cfg.workspace_dir, cfg.log_dir)
        self.cfg = cfg
        self.cc = cc

    def run(self, **kwargs) -> AgentResult:
        self._report("Starting VOB discovery")
        result: dict = {
            "vobs": {},
            "branch_git_map": {},
            "all_elements": [],
        }

        for vob_tag in self.cfg.clearcase.vob_tags:
            self._report(f"Discovering VOB: {vob_tag}")
            vob_data = self._discover_vob(vob_tag)
            result["vobs"][vob_tag] = vob_data

        result["branch_git_map"] = self._build_branch_git_map(result["vobs"])
        result["all_elements"] = self._collect_all_elements(result["vobs"])

        out_path = Path(self.cfg.workspace_dir) / "discovery.json"
        out_path.write_text(json.dumps(result, indent=2, default=str))
        self._report(f"Discovery complete — saved to {out_path}")
        self.set_state("discovery_done", True)
        return AgentResult(success=True, data=result)

    def _discover_vob(self, vob_tag: str) -> dict:
        data: dict = {
            "tag": vob_tag,
            "branches": [],
            "labels": [],
            "elements": [],
            "streams": [],
            "activities": [],
        }

        # Branches
        self._report(f"  Listing branches in {vob_tag}")
        try:
            branches = self.cc.list_branches(vob_tag)
            data["branches"] = [
                {"name": b.name, "parent": b.parent_branch,
                 "created_by": b.created_by, "comment": b.comment}
                for b in branches
                if self._branch_included(b.name)
            ]
        except Exception as exc:
            log.warning("Cannot list branches for %s: %s", vob_tag, exc)

        # Labels
        self._report(f"  Listing labels in {vob_tag}")
        try:
            labels = self.cc.list_labels(vob_tag)
            data["labels"] = [
                {"name": lb.name, "vob": lb.vob}
                for lb in labels
                if self._label_included(lb.name)
            ]
        except Exception as exc:
            log.warning("Cannot list labels for %s: %s", vob_tag, exc)

        # Elements
        view_path = str(Path(self.cfg.clearcase.view_root) / vob_tag.lstrip("/"))
        self._report(f"  Finding elements under {view_path}")
        try:
            elements = self.cc.find_elements(
                view_path,
                skip_derived=self.cfg.skip_derived_objects,
                skip_laf=self.cfg.skip_lost_and_found,
            )
            data["elements"] = elements
        except Exception as exc:
            log.warning("Cannot find elements for %s: %s", vob_tag, exc)

        # UCM streams/activities
        if self.cfg.clearcase.is_ucm:
            self._report(f"  Listing UCM streams in {vob_tag}")
            try:
                streams = self.cc.list_streams(vob_tag)
                data["streams"] = streams
                if self.cfg.clearcase.stream_tag:
                    self._report(f"  Listing activities for stream {self.cfg.clearcase.stream_tag}")
                    acts = self.cc.list_activities(self.cfg.clearcase.stream_tag, vob_tag)
                    data["activities"] = [
                        {
                            "id": a.activity_id,
                            "headline": a.headline,
                            "owner": a.owner,
                            "created_at": str(a.created_at),
                            "changeset": a.changeset,
                        }
                        for a in acts
                    ]
            except Exception as exc:
                log.warning("UCM discovery failed for %s: %s", vob_tag, exc)

        log.info(
            "VOB %s: %d branches, %d labels, %d elements",
            vob_tag, len(data["branches"]), len(data["labels"]), len(data["elements"]),
        )
        return data

    def _branch_included(self, name: str) -> bool:
        cfg = self.cfg.clearcase
        if cfg.exclude_branches and name in cfg.exclude_branches:
            return False
        if cfg.include_branches and name not in cfg.include_branches:
            return False
        return True

    def _label_included(self, name: str) -> bool:
        cfg = self.cfg.clearcase
        if cfg.exclude_labels and name in cfg.exclude_labels:
            return False
        if cfg.include_labels and name not in cfg.include_labels:
            return False
        return True

    def _build_branch_git_map(self, vobs: dict) -> dict[str, str]:
        """
        Map ClearCase branch names → Git branch names.
        'main' → default_branch; others get sanitized names.
        """
        from core.git_client import _safe_ref
        mapping: dict[str, str] = {}
        for vob_tag, vob_data in vobs.items():
            for br in vob_data.get("branches", []):
                cc_name = br["name"]
                if cc_name in ("main", "MAIN"):
                    git_name = self.cfg.git.default_branch
                else:
                    git_name = _safe_ref(cc_name)
                mapping[cc_name] = git_name
        return mapping

    def _collect_all_elements(self, vobs: dict) -> list[str]:
        elements = []
        for vob_data in vobs.values():
            elements.extend(vob_data.get("elements", []))
        return elements
