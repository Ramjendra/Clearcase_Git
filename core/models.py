"""
Core data models for ClearCase → Git migration.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import datetime


class ElementType(Enum):
    FILE = "file"
    DIRECTORY = "directory"
    SYMLINK = "symlink"
    DERIVED = "derived_object"
    UNKNOWN = "unknown"


class MigrationStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class CCVersion:
    """One version of a ClearCase element."""
    element_path: str          # VOB path, e.g. /vobs/myproject/src/main.c
    version_id: str            # e.g. /main/rel2_bugfix/3
    branch: str                # e.g. main/rel2_bugfix
    version_number: int        # e.g. 3
    created_by: str
    created_at: datetime.datetime
    comment: str
    predecessor: Optional[str] = None
    labels: list[str] = field(default_factory=list)
    merge_sources: list[str] = field(default_factory=list)
    element_type: ElementType = ElementType.FILE
    is_binary: Optional[bool] = None
    symlink_target: Optional[str] = None
    file_mode: int = 0o644


@dataclass
class CCElement:
    """A ClearCase versioned element (file or directory)."""
    vob_path: str
    element_oid: str
    element_type: ElementType
    versions: list[CCVersion] = field(default_factory=list)
    is_lost_and_found: bool = False
    encoding: str = "utf-8"


@dataclass
class CCBranch:
    """A ClearCase branch with its version history."""
    name: str                   # full branch type name
    vob: str
    parent_branch: Optional[str] = None
    created_by: str = ""
    created_at: Optional[datetime.datetime] = None
    comment: str = ""
    elements: list[str] = field(default_factory=list)  # element paths on this branch


@dataclass
class CCLabel:
    """A ClearCase label (version label) → becomes a Git tag."""
    name: str
    vob: str
    created_by: str = ""
    created_at: Optional[datetime.datetime] = None
    comment: str = ""
    labeled_versions: dict[str, str] = field(default_factory=dict)  # path → version_id


@dataclass
class CCActivity:
    """A UCM ClearCase activity → maps to a Git commit."""
    activity_id: str
    headline: str
    owner: str
    stream: str
    created_at: Optional[datetime.datetime] = None
    changeset: list[str] = field(default_factory=list)  # list of version extended names
    comment: str = ""


@dataclass
class GitCommit:
    """Staged Git commit ready to write."""
    branch: str
    message: str
    author_name: str
    author_email: str
    timestamp: datetime.datetime
    timezone: str = "+0000"
    # path → (content_bytes | None for delete, is_executable, is_symlink, symlink_target)
    file_changes: dict[str, tuple] = field(default_factory=dict)
    parent_commits: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    cc_activity_id: Optional[str] = None
    merge_from_branch: Optional[str] = None


@dataclass
class VOBInfo:
    """Discovered VOB metadata."""
    tag: str                   # /vobs/myproject
    uuid: str
    host: str
    storage_path: str
    is_admin_vob: bool = False
    components: list[str] = field(default_factory=list)  # UCM components
    branches: list[CCBranch] = field(default_factory=list)
    labels: list[CCLabel] = field(default_factory=list)


@dataclass
class MigrationState:
    """Persisted migration state for resume-on-failure."""
    vob_tag: str
    git_repo_path: str
    github_repo: str
    status: MigrationStatus = MigrationStatus.PENDING
    processed_versions: set[str] = field(default_factory=set)
    branch_map: dict[str, str] = field(default_factory=dict)   # cc_branch → git_branch
    label_map: dict[str, str] = field(default_factory=dict)    # cc_label  → git_tag
    commit_map: dict[str, str] = field(default_factory=dict)   # cc_version_ext → git_sha
    error_log: list[str] = field(default_factory=list)
    large_files: list[str] = field(default_factory=list)
    skipped_elements: list[str] = field(default_factory=list)
