"""
ClearCase CLI wrapper — all subprocess calls to cleartool live here.
Handles both Base ClearCase and UCM.
"""
from __future__ import annotations

import os
import re
import subprocess
import datetime
import logging
from typing import Optional
from pathlib import Path

from .models import (
    CCVersion, CCElement, CCBranch, CCLabel, CCActivity,
    VOBInfo, ElementType,
)

log = logging.getLogger(__name__)

# ── helpers ──────────────────────────────────────────────────────────────────

def _run(args: list[str], cwd: Optional[str] = None,
         timeout: int = 120) -> tuple[int, str, str]:
    """Run a shell command and return (returncode, stdout, stderr)."""
    try:
        r = subprocess.run(
            args, cwd=cwd, capture_output=True, text=True,
            timeout=timeout, errors="replace",
        )
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        log.warning("Timeout running: %s", " ".join(args))
        return -1, "", "TIMEOUT"
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"cleartool not found — make sure ClearCase client is installed and "
            f"on PATH. Original error: {exc}"
        )


def _ct(*args, cwd=None, timeout=120) -> str:
    """Run cleartool, return stdout, raise on failure."""
    rc, out, err = _run(["cleartool"] + list(args), cwd=cwd, timeout=timeout)
    if rc != 0:
        raise RuntimeError(f"cleartool {args[0]} failed: {err.strip()}")
    return out


_TS_FORMATS = [
    "%Y%m%d.%H%M%S",          # 20240415.143022  (most common cleartool format)
    "%d-%b-%Y.%H:%M:%S",      # 15-Apr-2024.14:30:22
    "%Y-%m-%dT%H:%M:%S%z",    # ISO 8601 with timezone
    "%Y-%m-%dT%H:%M:%S",      # ISO 8601 without timezone
    "%m/%d/%y %H:%M:%S",      # Windows ClearCase: 04/15/24 14:30:22
    "%m/%d/%Y %H:%M:%S",      # Windows ClearCase: 04/15/2024 14:30:22
    "%d/%m/%Y %H:%M:%S",      # European locale variant
    "%Y-%m-%d %H:%M:%S",      # SQL-style
    "%d-%b-%y.%H:%M:%S",      # 15-Apr-24.14:30:22 (2-digit year)
]


def _parse_ts(ts_str: str) -> datetime.datetime:
    ts_str = ts_str.strip()
    for fmt in _TS_FORMATS:
        try:
            dt = datetime.datetime.strptime(ts_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return dt
        except ValueError:
            continue
    log.debug("Unparseable timestamp '%s', using epoch", ts_str)
    return datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)


# ── view management ───────────────────────────────────────────────────────────

class ClearCaseClient:
    def __init__(self, view_tag: str, view_root: str, vob_tags: list[str]):
        self.view_tag = view_tag
        self.view_root = Path(view_root)
        self.vob_tags = vob_tags

    # ── view ──────────────────────────────────────────────────────────────────

    def start_view(self) -> None:
        """Start the view if not already started."""
        rc, out, _ = _run(["cleartool", "startview", self.view_tag])
        if rc != 0:
            log.debug("startview returned non-zero (may already be running)")

    def set_config_spec(self, spec_text: str) -> None:
        """Write a config spec to the view."""
        spec_file = Path("/tmp") / f"{self.view_tag}_cs.txt"
        spec_file.write_text(spec_text)
        _ct("setcs", "-tag", self.view_tag, str(spec_file))

    # ── VOB discovery ─────────────────────────────────────────────────────────

    def list_vobs(self) -> list[str]:
        out = _ct("lsvob", "-short")
        return [line.strip().lstrip("*").strip() for line in out.splitlines() if line.strip()]

    def vob_info(self, vob_tag: str) -> VOBInfo:
        out = _ct("describe", "-long", f"vob:{vob_tag}")
        uuid = ""
        host = ""
        storage = ""
        for line in out.splitlines():
            if "VOB family uuid" in line or "family uuid" in line.lower():
                m = re.search(r"([0-9a-f]{8}-[0-9a-f-]+)", line)
                if m:
                    uuid = m.group(1)
            if "VOB server access path" in line or "global path" in line.lower():
                storage = line.split(":", 1)[-1].strip()
            if "Master replica" in line or "master" in line.lower():
                m = re.search(r"@(\S+)", line)
                if m:
                    host = m.group(1)
        return VOBInfo(tag=vob_tag, uuid=uuid, host=host, storage_path=storage)

    # ── branch enumeration ────────────────────────────────────────────────────

    def list_branches(self, vob_tag: str) -> list[CCBranch]:
        out = _ct("lstype", "-kind", "brtype", "-short", f"vob:{vob_tag}")
        branches = []
        for name in out.splitlines():
            name = name.strip()
            if not name:
                continue
            try:
                info = self._describe_brtype(name, vob_tag)
                branches.append(info)
            except Exception as exc:
                log.warning("Cannot describe branch %s: %s", name, exc)
                branches.append(CCBranch(name=name, vob=vob_tag))
        return branches

    def _describe_brtype(self, branch_name: str, vob_tag: str) -> CCBranch:
        out = _ct("describe", "-long", f"brtype:{branch_name}@{vob_tag}")
        cb = CCBranch(name=branch_name, vob=vob_tag)
        for line in out.splitlines():
            if line.strip().startswith("owner:"):
                cb.created_by = line.split(":", 1)[-1].strip()
            if "created" in line.lower():
                m = re.search(r"(\d{8}\.\d{6}|\d+-\w+-\d+\.\d+:\d+:\d+)", line)
                if m:
                    cb.created_at = _parse_ts(m.group(1))
            if "comment:" in line.lower():
                cb.comment = line.split(":", 1)[-1].strip()
            if "derived from" in line.lower() or "parent" in line.lower():
                m = re.search(r"brtype:(\S+)", line)
                if m:
                    cb.parent_branch = m.group(1)
        return cb

    # ── label enumeration ─────────────────────────────────────────────────────

    def list_labels(self, vob_tag: str) -> list[CCLabel]:
        out = _ct("lstype", "-kind", "lbtype", "-short", f"vob:{vob_tag}")
        labels = []
        for name in out.splitlines():
            name = name.strip()
            if not name or name.startswith("CHECKEDOUT"):
                continue
            labels.append(CCLabel(name=name, vob=vob_tag))
        return labels

    def get_labeled_versions(self, label_name: str, vob_tag: str,
                              view_path: str) -> dict[str, str]:
        """Return {element_path: version_id} for all versions carrying this label."""
        out = _ct(
            "find", view_path,
            "-version", f"lbtype({label_name})",
            "-print",
            timeout=600,
        )
        result: dict[str, str] = {}
        for line in out.splitlines():
            line = line.strip()
            if "@@" not in line:
                continue
            path, ver = line.split("@@", 1)
            result[path] = "/" + ver.lstrip("/")
        return result

    # ── element history ───────────────────────────────────────────────────────

    def element_history(self, element_path: str,
                         branch_filter: Optional[str] = None) -> list[CCVersion]:
        """
        Return all versions of an element across all branches (or a specific branch).
        Uses 'cleartool lshistory -minor' to get every version including rmname events.
        """
        fmt = (
            r"---CCVER---\n"
            r"element:%En\n"
            r"version:%Vn\n"
            r"branch:%Bn\n"
            r"user:%u\n"
            r"date:%Nd\n"
            r"comment:%c\n"
            r"labels:%Nl\n"
            r"merges:%Nm\n"
            r"event:%e\n"
        )
        args = [
            "lshistory", "-minor", "-nco",
            "-fmt", fmt,
            element_path,
        ]
        if branch_filter:
            args += ["-branch", branch_filter]

        out = _ct(*args, timeout=300)
        return self._parse_lshistory(out, element_path)

    def directory_history(self, dir_element_path: str) -> list[dict]:
        """
        Return rmname events for a directory element so we can emit git deletes.
        Each entry: {name, branch, user, date, comment}
        """
        fmt = (
            r"---CCDIR---\n"
            r"event:%e\n"
            r"name:%n\n"
            r"branch:%Bn\n"
            r"user:%u\n"
            r"date:%Nd\n"
            r"comment:%c\n"
        )
        try:
            out = _ct("lshistory", "-minor", "-nco", "-fmt", fmt,
                      dir_element_path, timeout=300)
        except Exception as exc:
            log.warning("directory_history failed for %s: %s", dir_element_path, exc)
            return []

        events = []
        for block in out.split("---CCDIR---"):
            block = block.strip()
            if not block:
                continue
            kv: dict[str, str] = {}
            for line in block.splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    kv[k.strip()] = v.strip()
            event_type = kv.get("event", "")
            if event_type in ("rmname", "rmelem"):
                events.append({
                    "event": event_type,
                    "name": kv.get("name", ""),
                    "branch": kv.get("branch", "main"),
                    "user": kv.get("user", "unknown"),
                    "date": kv.get("date", "19700101.000000"),
                    "comment": kv.get("comment", ""),
                })
        return events

    def _parse_lshistory(self, raw: str, element_path: str) -> list[CCVersion]:
        versions: list[CCVersion] = []
        for block in raw.split("---CCVER---"):
            block = block.strip()
            if not block:
                continue
            kv: dict[str, str] = {}
            for line in block.splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    kv[k.strip()] = v.strip()
            if "version" not in kv:
                continue
            ver_id = "/" + kv.get("version", "").lstrip("/")
            parts = ver_id.rsplit("/", 1)
            branch = parts[0] if len(parts) == 2 else "main"
            ver_num_str = parts[1] if len(parts) == 2 else "0"
            try:
                ver_num = int(ver_num_str)
            except ValueError:
                ver_num = 0

            labels_raw = kv.get("labels", "")
            labels = [l.strip() for l in labels_raw.split() if l.strip()]

            merges_raw = kv.get("merges", "")
            merge_sources = [m.strip() for m in merges_raw.split() if m.strip()]

            event_type = kv.get("event", "checkin")
            # rmname/rmelem events mean the file was deleted in this version
            is_deleted = event_type in ("rmname", "rmelem", "destroy version")

            cv = CCVersion(
                element_path=kv.get("element", element_path),
                version_id=ver_id,
                branch=branch,
                version_number=ver_num,
                created_by=kv.get("user", "unknown"),
                created_at=_parse_ts(kv.get("date", "19700101.000000")),
                comment=kv.get("comment", ""),
                labels=labels,
                merge_sources=merge_sources,
                is_deleted=is_deleted,
            )
            # skip version 0 on any branch (directory creation pseudo-version)
            if ver_num > 0 or is_deleted:
                versions.append(cv)
        return versions

    # ── VOB tree walk ─────────────────────────────────────────────────────────

    def find_elements(self, vob_path: str,
                       skip_derived: bool = True,
                       skip_laf: bool = False) -> list[str]:
        """
        Return all element paths under vob_path using 'cleartool find'.
        """
        args = ["find", vob_path, "-nxname", "-print"]
        if skip_derived:
            args += ["-type", "f,d,l"]   # files, dirs, symlinks — not derived
        out = _ct(*args, timeout=900)
        paths = []
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            if skip_laf and "lost+found" in line.lower():
                continue
            # Strip version extended name if present
            if "@@" in line:
                line = line.split("@@")[0]
            paths.append(line)
        return paths

    # ── file content extraction ───────────────────────────────────────────────

    def get_version_content(self, element_path: str,
                             version_id: str) -> bytes:
        """
        Extract raw bytes of a specific version.
        Uses 'cleartool get' to a temp file to handle binary safely.
        """
        ext_path = f"{element_path}@@{version_id}"
        tmp = Path("/tmp") / f"cc_get_{abs(hash(ext_path))}"
        try:
            _ct("get", "-to", str(tmp), ext_path, timeout=60)
            return tmp.read_bytes()
        except Exception as exc:
            raise RuntimeError(f"Cannot get {ext_path}: {exc}")
        finally:
            if tmp.exists():
                tmp.unlink()

    def get_symlink_target(self, element_path: str,
                            version_id: str) -> str:
        """Return the symlink target for a symlink element version."""
        ext_path = f"{element_path}@@{version_id}"
        out = _ct("describe", "-fmt", r"%[slink_text]p", ext_path)
        return out.strip()

    def get_element_type(self, element_path: str) -> ElementType:
        try:
            out = _ct("describe", "-fmt", r"%[type]p", f"vob:{element_path}")
            t = out.strip().lower()
            if t in ("file element", "file"):
                return ElementType.FILE
            if t in ("directory element", "directory"):
                return ElementType.DIRECTORY
            if t in ("symbolic link", "symlink"):
                return ElementType.SYMLINK
            if "derived" in t:
                return ElementType.DERIVED
        except Exception:
            pass
        return ElementType.UNKNOWN

    def get_file_mode(self, element_path: str, version_id: str) -> int:
        """Return Unix file permission bits for a version."""
        ext_path = f"{element_path}@@{version_id}"
        out = _ct("describe", "-fmt", r"%[mode]p", ext_path)
        mode_str = out.strip()
        try:
            return int(mode_str, 8)
        except ValueError:
            return 0o644

    # ── UCM-specific ──────────────────────────────────────────────────────────

    def list_streams(self, vob_tag: str) -> list[str]:
        out = _ct("lsstream", "-short", f"vob:{vob_tag}")
        return [l.strip() for l in out.splitlines() if l.strip()]

    def list_baselines(self, stream_tag: str, vob_tag: str) -> list[str]:
        out = _ct("lsbaseline", "-short", "-stream", f"{stream_tag}@{vob_tag}")
        return [l.strip() for l in out.splitlines() if l.strip()]

    def list_activities(self, stream_tag: str, vob_tag: str) -> list[CCActivity]:
        out = _ct(
            "lsactivity", "-short",
            "-stream", f"{stream_tag}@{vob_tag}",
            timeout=300,
        )
        activities = []
        for act_id in out.splitlines():
            act_id = act_id.strip()
            if not act_id:
                continue
            try:
                act = self._describe_activity(act_id, vob_tag)
                activities.append(act)
            except Exception as exc:
                log.warning("Cannot describe activity %s: %s", act_id, exc)
        return activities

    def _describe_activity(self, act_id: str, vob_tag: str) -> CCActivity:
        out = _ct(
            "describe", "-long", "-fmt",
            r"headline:%[headline]p\nowner:%[owner]p\ndate:%Nd\nchangeset:%[versions]p\n",
            f"activity:{act_id}@{vob_tag}",
        )
        kv: dict[str, str] = {}
        for line in out.splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                kv[k.strip()] = v.strip()
        changeset = kv.get("changeset", "").split()
        return CCActivity(
            activity_id=act_id,
            headline=kv.get("headline", ""),
            owner=kv.get("owner", "unknown"),
            stream=vob_tag,
            created_at=_parse_ts(kv.get("date", "19700101.000000")),
            changeset=changeset,
        )

    # ── config spec helpers ───────────────────────────────────────────────────

    def build_branch_config_spec(self, branches: list[str],
                                  vob_tags: list[str]) -> str:
        """
        Build a config spec that selects the latest on each branch in order.
        Branches listed first take precedence.
        """
        lines = ["# Auto-generated config spec for migration"]
        for br in branches:
            lines.append(f"element * .../{br}/LATEST")
        lines.append("element * /main/LATEST")
        lines.append("element * /main/0")
        return "\n".join(lines) + "\n"
