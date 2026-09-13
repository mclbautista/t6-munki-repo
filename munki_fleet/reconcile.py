"""Remove served metadata the checkout no longer has — declared, and verified against the record.

Publishing pushes the checkout out and never deletes, which is the safe default but leaves the
served tree accumulating files the checkout has retired. Twice now that has meant a second pkginfo
for an item that still exists — the duplicate-name defect this project started with — so removal
needs to be possible, and it needs to be checkable rather than a hand-run `rm`.

Two rules make it checkable. Every removal is **declared**, and the declarations must match the
drift findings exactly, so a stale declaration cannot delete something unexpected and an
undeclared finding cannot be quietly skipped. And where the project recorded withdrawing the file,
the bytes on the target must **hash-match the record** before they are removed: the deletion then
proves it is removing the file that was withdrawn, not merely a file at that path.
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Sequence, Tuple

from .drift import DriftReport
from .promote import WITHDRAWALS_PATH


class ReconcileError(Exception):
    """A removal was asked for in a way that cannot be verified."""


def recorded_hashes(source_root: str) -> Dict[str, str]:
    """sha256 of every file this project has recorded removing, keyed by its path on the target."""
    path = os.path.join(source_root, WITHDRAWALS_PATH)
    if not os.path.isfile(path):
        return {}
    out: Dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            record = json.loads(line)
            out[record["source_path"]] = record["source_sha256"]
    return out


def plan_removals(report: DriftReport, declared: Sequence[str]) -> List[str]:
    """The paths to remove, or an error saying why the request does not line up with reality."""
    actual = set(report.only_on_target)
    wanted = {str(p) for p in declared}

    stale = sorted(wanted - actual)
    if stale:
        raise ReconcileError(
            "declared for removal but not a drift finding: " + ", ".join(stale)
            + " — nothing was removed; re-run the check, because the target is not what the "
              "declaration assumed"
        )
    undeclared = sorted(actual - wanted)
    if undeclared:
        raise ReconcileError(
            "drift on the target is undeclared: " + ", ".join(undeclared)
            + " — declare each one, or investigate it; an unexplained file is not removable by "
              "this command"
        )
    blocking = []
    if report.missing_on_target:
        blocking.append(f"missing on the target: {', '.join(report.missing_on_target)}")
    if report.differing:
        blocking.append(f"differing: {', '.join(report.differing)}")
    if report.unreadable:
        blocking.append(f"unreadable: {', '.join(report.unreadable)}")
    if blocking:
        raise ReconcileError(
            "only files present on the target alone may be removed; publish first — "
            + "; ".join(blocking)
        )
    return sorted(actual)


def apply_removals(target, paths: Sequence[str],
                   expected: Dict[str, str]) -> List[Tuple[str, str]]:
    """Remove each path, verifying the bytes first and the absence after.

    A path the record knows about must hash-match before it goes. A path with no record is removed
    on the strength of the declaration alone, and says so in the result.
    """
    results: List[Tuple[str, str]] = []
    for relpath in paths:
        stat = target.stat(relpath)
        if stat is None:
            results.append((relpath, "already absent"))
            continue
        digest = expected.get(relpath)
        if digest and stat.sha256 != digest:
            raise ReconcileError(
                f"{relpath} on the target hashes {stat.sha256[:16]}, but the record says the file "
                f"withdrawn from that path was {digest[:16]} — refusing to remove it: it is not the "
                f"file this project retired"
            )
        target.remove(relpath)
        if target.stat(relpath) is not None:
            raise ReconcileError(f"{relpath} is still present after removal")
        results.append((relpath, f"removed, matched the record ({digest[:16]})" if digest
                        else "removed, no record to verify against"))
    return results
