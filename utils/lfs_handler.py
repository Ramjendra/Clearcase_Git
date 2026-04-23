"""
Git LFS pointer generation for large files detected during migration.
Git LFS objects must be uploaded separately; this module generates the
pointer files that go into the git history and records the blobs to upload.
"""
from __future__ import annotations
import hashlib
import struct
import logging
from pathlib import Path

log = logging.getLogger(__name__)

_LFS_POINTER_TEMPLATE = """\
version https://git-lfs.github.com/spec/v1
oid sha256:{sha256}
size {size}
"""


def lfs_pointer(data: bytes) -> bytes:
    """Return the LFS pointer file content for the given blob."""
    sha256 = hashlib.sha256(data).hexdigest()
    size = len(data)
    return _LFS_POINTER_TEMPLATE.format(sha256=sha256, size=size).encode()


def should_use_lfs(data: bytes, path: str, threshold_mb: float,
                    lfs_patterns: list[str]) -> bool:
    """Decide whether a file should be stored in LFS."""
    import fnmatch
    from pathlib import PurePosixPath
    name = PurePosixPath(path).name
    # Pattern match first
    for pat in lfs_patterns:
        if fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(path, pat):
            log.debug("LFS: %s matches pattern %s", path, pat)
            return True
    # Size threshold
    size_mb = len(data) / (1024 * 1024)
    if size_mb >= threshold_mb:
        log.debug("LFS: %s is %.1f MB (threshold %.1f MB)", path, size_mb, threshold_mb)
        return True
    return False


class LFSBlobStore:
    """
    Tracks LFS objects that need to be uploaded after the git push.
    Writes each blob to <store_dir>/objects/<sha256[:2]>/<sha256[2:4]>/<sha256>
    following the LFS object storage layout.
    """
    def __init__(self, store_dir: str):
        self.store_dir = Path(store_dir)
        self.objects: dict[str, Path] = {}  # sha256 → path

    def add(self, data: bytes) -> str:
        """Store blob data and return its sha256."""
        sha256 = hashlib.sha256(data).hexdigest()
        if sha256 in self.objects:
            return sha256
        obj_path = self.store_dir / "objects" / sha256[:2] / sha256[2:4] / sha256
        obj_path.parent.mkdir(parents=True, exist_ok=True)
        obj_path.write_bytes(data)
        self.objects[sha256] = obj_path
        log.debug("LFS stored %s (%d bytes)", sha256[:12], len(data))
        return sha256

    def generate_upload_script(self, output_path: str) -> None:
        """Write a shell script to push LFS objects to the remote."""
        lines = [
            "#!/bin/bash",
            "# Auto-generated LFS object upload script",
            "set -e",
            f"LFS_STORE={self.store_dir}",
        ]
        for sha256, obj_path in self.objects.items():
            lines.append(f"git lfs push --object-id {sha256}")
        lines.append("echo 'LFS upload complete'")
        Path(output_path).write_text("\n".join(lines) + "\n")
        log.info("LFS upload script written to %s (%d objects)", output_path, len(self.objects))
