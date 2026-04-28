"""
Configuration loader and validator for ClearCase → Git migration.
"""
from __future__ import annotations
import os
import yaml
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ClearCaseConfig:
    vob_tags: list[str]               # ["/vobs/project1", "/vobs/project2"]
    view_tag: str                      # name of the snapshot/dynamic view
    view_root: str                     # local mount point, e.g. /view/my_view
    config_spec: str = ""              # optional inline config spec
    include_branches: list[str] = field(default_factory=list)   # empty = all
    exclude_branches: list[str] = field(default_factory=list)
    include_labels: list[str] = field(default_factory=list)     # empty = all
    exclude_labels: list[str] = field(default_factory=list)
    is_ucm: bool = False
    stream_tag: str = ""               # UCM stream
    baseline_tag: str = ""             # UCM baseline


@dataclass
class GitConfig:
    output_dir: str                    # local path for the git repo
    default_branch: str = "main"
    author_map_file: str = ""          # CSV: cc_user,git_name,git_email
    use_lfs: bool = True
    lfs_threshold_mb: float = 50.0
    lfs_patterns: list[str] = field(default_factory=lambda: [
        "*.o", "*.a", "*.so", "*.dll", "*.exe", "*.lib",
        "*.zip", "*.tar", "*.gz", "*.bz2", "*.7z",
        "*.pdf", "*.bin", "*.img", "*.iso",
    ])


@dataclass
class GitHubConfig:
    enabled: bool = False
    org: str = ""
    repo_name: str = ""
    token_env_var: str = "GITHUB_TOKEN"
    visibility: str = "private"        # private | public | internal
    push_force: bool = False
    use_ssh: bool = False              # True = git@github.com (SSH key auth, no token needed)
    ssh_key_path: str = ""             # optional path to a specific SSH key (~/.ssh/id_rsa)


@dataclass
class MigrationConfig:
    clearcase: ClearCaseConfig
    git: GitConfig
    github: GitHubConfig
    workspace_dir: str = "workspace"
    log_dir: str = "logs"
    max_workers: int = 4
    batch_size: int = 200              # versions per batch
    resume: bool = True               # resume from saved state
    dry_run: bool = False
    preserve_empty_dirs: bool = True   # add .gitkeep
    sanitize_filenames: bool = True    # replace ClearCase illegal chars
    detect_encoding: bool = True       # chardet for non-utf8 C files
    skip_derived_objects: bool = True
    skip_lost_and_found: bool = False  # include lost+found as a branch
    generate_gitattributes: bool = True
    generate_gitignore: bool = True
    exclude_patterns: list[str] = field(default_factory=lambda: [
        "*.o", "*.a", "*.so.d", "lost+found",
    ])


def load_config(path: str) -> MigrationConfig:
    with open(path, "r") as fh:
        raw = yaml.safe_load(fh)

    cc_raw = raw.get("clearcase", {})
    git_raw = raw.get("git", {})
    gh_raw = raw.get("github", {})
    top = {k: v for k, v in raw.items() if k not in ("clearcase", "git", "github")}

    cc = ClearCaseConfig(
        vob_tags=cc_raw.get("vob_tags", []),
        view_tag=cc_raw.get("view_tag", ""),
        view_root=cc_raw.get("view_root", "/view"),
        config_spec=cc_raw.get("config_spec", ""),
        include_branches=cc_raw.get("include_branches", []),
        exclude_branches=cc_raw.get("exclude_branches", []),
        include_labels=cc_raw.get("include_labels", []),
        exclude_labels=cc_raw.get("exclude_labels", []),
        is_ucm=cc_raw.get("is_ucm", False),
        stream_tag=cc_raw.get("stream_tag", ""),
        baseline_tag=cc_raw.get("baseline_tag", ""),
    )
    git_cfg = GitConfig(
        output_dir=git_raw.get("output_dir", "git_output"),
        default_branch=git_raw.get("default_branch", "main"),
        author_map_file=git_raw.get("author_map_file", ""),
        use_lfs=git_raw.get("use_lfs", True),
        lfs_threshold_mb=float(git_raw.get("lfs_threshold_mb", 50.0)),
        lfs_patterns=git_raw.get("lfs_patterns", GitConfig.__dataclass_fields__["lfs_patterns"].default_factory()),
    )
    gh = GitHubConfig(
        enabled=gh_raw.get("enabled", False),
        org=gh_raw.get("org", ""),
        repo_name=gh_raw.get("repo_name", ""),
        token_env_var=gh_raw.get("token_env_var", "GITHUB_TOKEN"),
        visibility=gh_raw.get("visibility", "private"),
        push_force=gh_raw.get("push_force", False),
        use_ssh=gh_raw.get("use_ssh", False),
        ssh_key_path=gh_raw.get("ssh_key_path", ""),
    )

    return MigrationConfig(
        clearcase=cc,
        git=git_cfg,
        github=gh,
        workspace_dir=top.get("workspace_dir", "workspace"),
        log_dir=top.get("log_dir", "logs"),
        max_workers=int(top.get("max_workers", 4)),
        batch_size=int(top.get("batch_size", 200)),
        resume=bool(top.get("resume", True)),
        dry_run=bool(top.get("dry_run", False)),
        preserve_empty_dirs=bool(top.get("preserve_empty_dirs", True)),
        sanitize_filenames=bool(top.get("sanitize_filenames", True)),
        detect_encoding=bool(top.get("detect_encoding", True)),
        skip_derived_objects=bool(top.get("skip_derived_objects", True)),
        skip_lost_and_found=bool(top.get("skip_lost_and_found", False)),
        generate_gitattributes=bool(top.get("generate_gitattributes", True)),
        generate_gitignore=bool(top.get("generate_gitignore", True)),
        exclude_patterns=top.get("exclude_patterns", MigrationConfig.__dataclass_fields__["exclude_patterns"].default_factory()),
    )


def validate_config(cfg: MigrationConfig) -> list[str]:
    """Return list of validation errors (empty = OK)."""
    errors = []
    if not cfg.clearcase.vob_tags:
        errors.append("clearcase.vob_tags must not be empty")
    if not cfg.clearcase.view_tag:
        errors.append("clearcase.view_tag must not be empty")
    if not cfg.git.output_dir:
        errors.append("git.output_dir must not be empty")
    if cfg.clearcase.is_ucm and not cfg.clearcase.stream_tag:
        errors.append("clearcase.stream_tag required when is_ucm=true")
    if cfg.github.enabled:
        if not cfg.github.repo_name:
            errors.append("github.repo_name required when github.enabled=true")
        if not cfg.github.use_ssh and not os.environ.get(cfg.github.token_env_var):
            errors.append(
                f"env var {cfg.github.token_env_var} not set "
                f"(or set github.use_ssh=true to use SSH key authentication)"
            )
    return errors
