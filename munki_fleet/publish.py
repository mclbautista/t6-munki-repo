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


class PublishAborted(PublishError):
    """A publish failed after it had already written something.

    Carries the report so the caller can see exactly what was rolled back — a failure must never be
    reported as a bare error with the target in an unknown state.
    """

    def __init__(self, message: str, report: "PublishReport") -> None:
        super().__init__(message)
        self.report = report


@dataclass
class PublishReport:
    written: List[str] = field(default_factory=list)
    unchanged: List[str] = field(default_factory=list)
    backed_up: List[str] = field(default_factory=list)
    rolled_back: List[str] = field(default_factory=list)
    rollback_errors: List[str] = field(default_factory=list)

    def describe(self) -> str:
        parts = [f"written {len(self.written)}", f"unchanged {len(self.unchanged)}",
                 f"backed up {len(self.backed_up)}"]
        if self.rolled_back:
            parts.append(f"rolled back {len(self.rolled_back)}")
        if self.rollback_errors:
            parts.append(f"ROLLBACK FAILED for {len(self.rollback_errors)}")
        return ", ".join(parts)


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


def _rollback(target, done: List[tuple], report: PublishReport) -> None:
    """Undo the writes this publish already made, so a failure is never a partial publish.

    Each entry is (relpath, pre-image bytes or None). A file that existed is restored to its bytes;
    a file that did not exist is removed, because leaving it would be the partial publish this
    exists to prevent.
    """
    for relpath, pre_image in reversed(done):
        try:
            if pre_image is None:
                target.remove(relpath)
            else:
                target.write_atomic(relpath, pre_image)
            report.rolled_back.append(relpath)
        except TargetError as exc:
            report.rollback_errors.append(f"{relpath}: {exc}")


def publish(source_root: str, target, paths: List[str], backup_dir: Optional[str] = None) -> PublishReport:
    """Publish `paths` from the metadata checkout to `target`, verifying every write.

    Fails before writing anything when the checkout is incomplete, and rolls back the writes it has
    already made if a later one fails — the spec's invariant is that a partial publish never
    happens, not merely that a partial file never appears.
    """
    source_root = os.path.abspath(source_root)
    safe_paths = [safe_relpath(p) for p in paths]

    missing = [p for p in safe_paths if _local_stat(source_root, p) is None]
    if missing:
        raise PublishError(
            "refusing to publish an incomplete checkout; missing from the source: "
            + ", ".join(sorted(missing)[:10]) + ("…" if len(missing) > 10 else "")
        )

    report = PublishReport()
    done: List[tuple] = []
    for relpath in sorted(safe_paths):
        local = _local_stat(source_root, relpath)
        try:
            existing = target.stat(relpath)
        except TargetError as exc:
            _rollback(target, done, report)
            raise PublishAborted(
                f"could not read {relpath} from the target: {exc}", report) from exc
        if existing is not None and existing.sha256 == local.sha256:
            report.unchanged.append(relpath)
            continue
        pre_image: Optional[bytes] = None
        if existing is not None:
            try:
                pre_image = target.read(relpath)
            except TargetError as exc:
                _rollback(target, done, report)
                raise PublishAborted(
                    f"could not capture the pre-image of {relpath}: {exc}", report) from exc
            if backup_dir:
                LocalDirTarget(backup_dir).write_atomic(relpath, pre_image)
                report.backed_up.append(relpath)
        with open(os.path.join(source_root, relpath), "rb") as fh:
            data = fh.read()
        try:
            target.write_atomic(relpath, data)
            stored = target.stat(relpath)
        except TargetError as exc:
            _rollback(target, done, report)
            raise PublishAborted(f"publish failed for {relpath}: {exc}", report) from exc
        if stored is None or stored.sha256 != local.sha256:
            _rollback(target, done, report)
            raise PublishAborted(
                f"{relpath} does not match the checkout after publishing "
                f"(target {stored.sha256 if stored else 'missing'}, checkout {local.sha256})",
                report)
        done.append((relpath, pre_image))
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
