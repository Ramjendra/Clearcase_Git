"""
Publisher Agent — pushes the converted git repository to GitHub.

Responsibilities:
  1. Create the GitHub repository (if it doesn't exist) via the REST API
  2. Set branch protection rules on the default branch
  3. Push all branches and tags
  4. Push LFS objects (if any)
  5. Create a migration summary issue on GitHub
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from typing import Optional

from .base_agent import BaseAgent, AgentResult
from core.config import MigrationConfig
from core.git_client import GitClient

log = logging.getLogger(__name__)


class PublisherAgent(BaseAgent):
    name = "publisher"

    def __init__(self, cfg: MigrationConfig, git: GitClient):
        super().__init__(cfg.workspace_dir, cfg.log_dir)
        self.cfg = cfg
        self.git = git
        self._token = os.environ.get(cfg.github.token_env_var, "")

    def _build_repo_url(self, owner: str) -> str:
        """Return the correct remote URL based on SSH vs HTTPS auth preference."""
        gh = self.cfg.github
        if gh.use_ssh:
            return f"git@github.com:{owner}/{gh.repo_name}.git"
        # HTTPS with embedded token
        return f"https://{owner}:{self._token}@github.com/{owner}/{gh.repo_name}.git"

    def _ssh_env(self) -> dict:
        """Build environment override for SSH key if a custom path is set."""
        gh = self.cfg.github
        if gh.use_ssh and gh.ssh_key_path:
            key = os.path.expanduser(gh.ssh_key_path)
            return {"GIT_SSH_COMMAND": f"ssh -i {key} -o StrictHostKeyChecking=accept-new"}
        return {}

    def run(self, **kwargs) -> AgentResult:
        gh = self.cfg.github
        if not gh.enabled:
            self._report("GitHub publishing disabled — skipping")
            return AgentResult(success=True, data={"skipped": True})

        if not gh.use_ssh and not self._token:
            return AgentResult(
                success=False,
                error=f"GitHub token not set in env var {gh.token_env_var}. "
                      f"Set github.use_ssh=true in config to use SSH key auth instead.",
            )

        # 1. Create or verify repo (API call — only possible with token)
        repo_url = self._ensure_repo()
        if not repo_url:
            return AgentResult(success=False, error="Failed to create/find GitHub repo")

        # 2. Add remote and push
        self._report(f"Pushing to {repo_url}")
        self.git.add_remote("origin", repo_url)
        ssh_env = self._ssh_env()
        try:
            self.git.push(
                remote="origin",
                all_branches=True,
                all_tags=True,
                force=gh.push_force,
                extra_env=ssh_env,
            )
        except Exception as exc:
            return AgentResult(success=False, error=f"Push failed: {exc}")

        # 3. Push LFS objects if any
        lfs_script = Path(self.cfg.log_dir) / "upload_lfs.sh"
        if lfs_script.exists():
            self._push_lfs(str(lfs_script))

        # 4. Branch protection on default branch
        self._set_branch_protection()

        # 5. Migration summary issue
        self._create_summary_issue(repo_url)

        self._report(f"Published to {repo_url}")
        return AgentResult(success=True, data={"repo_url": repo_url})

    # ── GitHub REST helpers ───────────────────────────────────────────────────

    def _api(self, method: str, path: str,
              body: Optional[dict] = None, expected_codes=(200, 201)) -> Optional[dict]:
        url = f"https://api.github.com{path}"
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(
            url, data=data, method=method,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode(errors="replace")
            if exc.code not in expected_codes:
                log.error("GitHub API %s %s → %d: %s", method, path, exc.code, body_text[:300])
            return None

    def _ensure_repo(self) -> Optional[str]:
        gh = self.cfg.github
        owner = gh.org or self._get_authenticated_user()
        if not owner:
            # SSH-only mode with no token: assume repo already exists, build URL directly
            if gh.use_ssh:
                url = self._build_repo_url(gh.org or "unknown")
                log.info("SSH mode, no API token — assuming repo exists: %s", url)
                return url
            return None

        # Check if repo exists via API (requires token)
        if self._token:
            existing = self._api("GET", f"/repos/{owner}/{gh.repo_name}", expected_codes=(200, 404))
            if existing and "clone_url" in existing:
                log.info("Repo already exists: %s", existing["clone_url"])
                return self._build_repo_url(owner)

            # Create it
            endpoint = f"/orgs/{gh.org}/repos" if gh.org else "/user/repos"
            payload = {
                "name": gh.repo_name,
                "private": gh.visibility == "private",
                "visibility": gh.visibility,
                "description": "Migrated from ClearCase",
                "auto_init": False,
            }
            result = self._api("POST", endpoint, body=payload, expected_codes=(201,))
            if result:
                log.info("Created repo: %s", result.get("ssh_url" if gh.use_ssh else "clone_url"))
                return self._build_repo_url(owner)
        else:
            # SSH + no token: assume repo exists
            log.info("SSH auth, no token — skipping repo creation API call")

        return self._build_repo_url(owner)

    def _get_authenticated_user(self) -> Optional[str]:
        result = self._api("GET", "/user")
        return result.get("login") if result else None

    def _set_branch_protection(self) -> None:
        gh = self.cfg.github
        owner = gh.org or self._get_authenticated_user()
        branch = self.cfg.git.default_branch
        if not owner:
            return
        payload = {
            "required_status_checks": None,
            "enforce_admins": False,
            "required_pull_request_reviews": None,
            "restrictions": None,
        }
        self._api(
            "PUT",
            f"/repos/{owner}/{gh.repo_name}/branches/{branch}/protection",
            body=payload,
            expected_codes=(200,),
        )
        log.info("Branch protection set on %s", branch)

    def _create_summary_issue(self, repo_url: str) -> None:
        gh = self.cfg.github
        owner = gh.org or self._get_authenticated_user()
        if not owner:
            return

        branches = self.git.list_branches()
        tags = self.git.list_tags()
        body = (
            f"## ClearCase Migration Summary\n\n"
            f"**VOBs migrated:** {', '.join(self.cfg.clearcase.vob_tags)}\n\n"
            f"**Branches created:** {len(branches)}\n"
            + "\n".join(f"  - `{b}`" for b in sorted(branches)) + "\n\n"
            f"**Tags created:** {len(tags)}\n"
            + "\n".join(f"  - `{t}`" for t in sorted(tags)[:20])
            + ("\n  - _(more…)_\n" if len(tags) > 20 else "\n") + "\n"
            f"**Migration tool:** cc2git multi-agent pipeline\n"
        )
        self._api(
            "POST",
            f"/repos/{owner}/{gh.repo_name}/issues",
            body={
                "title": "ClearCase Migration Complete",
                "body": body,
                "labels": ["migration"],
            },
            expected_codes=(201,),
        )
        log.info("Migration summary issue created")

    def _push_lfs(self, script_path: str) -> None:
        try:
            subprocess.run(
                ["bash", script_path],
                cwd=self.cfg.git.output_dir,
                timeout=1800,
                check=True,
            )
            log.info("LFS objects pushed")
        except Exception as exc:
            log.error("LFS push failed: %s", exc)
