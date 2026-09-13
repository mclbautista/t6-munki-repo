"""The publish path: plan, transfer to a temporary name, verify, rename atomically.

Invariants this module exists to hold:

- a client never sees a partially written file (write to a temp name, rename into place);
- a file is never reported as published unless its checksum was read back from the target;
- a publish that fails leaves the target exactly as it was;
- the pre-image of anything replaced can be kept, because the repository has no snapshot yet.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

from .targets import FileStat, LocalDirTarget, TargetError, sha256_bytes


class PublishError(Exception):
    """A publish could not be completed safely."""


@dataclass
class PublishReport:
    written: List[str] = field(default_factory=list)
    unchanged: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    backed_up: List[str] = field(default_factory=list)

    def describe(self) -> str:
        return (f"written {len(self.written)}, unchanged {len(self.unchanged)}, "
                f"skipped {len(self.skipped)}, backed up {len(self.backed_up)}")


@dataclass
class ServedCheck:
    matching: List[str] = field(default_factory=list)
    mismatching: List[str] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.mismatching or self.missing)

    def describe(self) -> str:
        return (f"matching {len(self.matching)}, mismatching {len(self.mismatching)}, "
                f"missing {len(self.missing)}")


def safe_relpath(relpath: str) -> str:
    """Reject anything that would write outside the repository root."""
    if os.path.isabs(relpath) or relpath.startswith("~"):
        raise PublishError(f"refusing absolute path: {relpath}")
    normalised = os.path.normpath(relpath)
    if normalised.startswith("..") or normalised in (".", ""):
        raise PublishError(f"refusing path outside the metadata root: {relpath}")
    return normalised


def _local_stat(source_root: str, relpath: str) -> Optional[FileStat]:
    full = os.path.join(source_root, relpath)
    if not os.path.isfile(full):
        return None
    with open(full, "rb") as fh:
        data = fh.read()
    return FileStat(sha256=sha256_bytes(data), size=len(data))


def publish(source_root: str, target, paths: List[str], backup_dir: Optional[str] = None) -> PublishReport:
    """Publish `paths` from the metadata checkout to `target`, verifying every write."""
    source_root = os.path.abspath(source_root)
    report = PublishReport()
    for relpath in sorted(paths):
        relpath = safe_relpath(relpath)
        local = _local_stat(source_root, relpath)
        if local is None:
            report.skipped.append(relpath)
            continue
        try:
            existing = target.stat(relpath)
        except TargetError as exc:
            raise PublishError(f"could not read {relpath} from the target: {exc}") from exc
        if existing is not None and existing.sha256 == local.sha256:
            report.unchanged.append(relpath)
            continue
        if existing is not None and backup_dir:
            backup_target = LocalDirTarget(backup_dir)
            backup_target.write_atomic(relpath, target.read(relpath))
            report.backed_up.append(relpath)
        with open(os.path.join(source_root, relpath), "rb") as fh:
            data = fh.read()
        try:
            target.write_atomic(relpath, data)
        except TargetError as exc:
            raise PublishError(f"publish failed for {relpath}: {exc}") from exc
        try:
            stored = target.stat(relpath)
        except TargetError as exc:
            raise PublishError(f"could not verify {relpath} after publishing: {exc}") from exc
        if stored is None or stored.sha256 != local.sha256:
            raise PublishError(
                f"{relpath} does not match the checkout after publishing "
                f"(target {stored.sha256 if stored else 'missing'}, checkout {local.sha256})"
            )
        report.written.append(relpath)
    return report


def verify_served(source_root: str, target, paths: List[str]) -> ServedCheck:
    """Compare what a target serves against the checkout, file by file."""
    source_root = os.path.abspath(source_root)
    result = ServedCheck()
    for relpath in sorted(paths):
        relpath = safe_relpath(relpath)
        local = _local_stat(source_root, relpath)
        if local is None:
            result.missing.append(relpath)
            continue
        try:
            served = target.stat(relpath)
        except TargetError:
            served = None
        if served is None:
            result.missing.append(relpath)
        elif served.sha256 == local.sha256:
            result.matching.append(relpath)
        else:
            result.mismatching.append(relpath)
    return result
