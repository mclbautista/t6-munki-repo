"""Payloads: large, NAS-only, and left behind when the item that needed them is withdrawn.

A payload is referenced by exactly one thing — a pkginfo's `installer_item_location` — so "nothing
references this any more" is a decidable question, and an orphan is hundreds of megabytes of vendor
installer sitting in the served tree. Removal is a deletion on the NAS, so it is declared: every
declared path must actually be an orphan, so a typo cannot delete a payload the fleet needs, and the
bytes are recorded as they are removed.
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, Sequence, Tuple

from .drift import _iter_pkginfos
from .promote import _now

PAYLOAD_REMOVALS_PATH = os.path.join("data", "payload-removals.jsonl")
PAYLOAD_DIRS = ("pkgs",)


class PayloadError(Exception):
    """A payload removal was asked for in a way that cannot be verified."""


def referenced_locations(source_root: str) -> Dict[str, str]:
    """`installer_item_location` -> item name, for every pkginfo in the checkout."""
    refs: Dict[str, str] = {}
    for _, pkginfo in _iter_pkginfos(source_root):
        location = pkginfo.get("installer_item_location")
        if location:
            refs[str(location).lstrip("./")] = pkginfo.get("name")
    return refs


def list_payloads(target, dirs: Sequence[str] = PAYLOAD_DIRS) -> List[str]:
    wanted = tuple(dirs)
    return [p for p in target.list_files(wanted)
            if p.split("/", 1)[0] in wanted]


def orphan_payloads(source_root: str, target,
                    dirs: Sequence[str] = PAYLOAD_DIRS) -> List[str]:
    """Payloads on the target that no pkginfo in the checkout references."""
    refs = referenced_locations(source_root)
    out = []
    for relpath in list_payloads(target, dirs):
        location = relpath.split("/", 1)[1] if "/" in relpath else relpath
        if location not in refs:
            out.append(relpath)
    return sorted(out)


def remove_payloads(source_root: str, target, orphans: Sequence[str], declared: Sequence[str],
                    approved_by: str, reason: str, at: Optional[str] = None,
                    dry_run: bool = False) -> List[Tuple[str, str]]:
    """Remove the declared orphans, refusing anything that is not one.

    `orphans` is what the check just found. A declared path that is not in it is either a typo or an
    item whose pkginfo came back — either way the removal is wrong, and nothing is removed.
    """
    at = at or _now()
    if not approved_by:
        raise PayloadError("a payload removal must record who approved it")
    if not reason.strip():
        raise PayloadError("a payload removal must record why")
    wanted = [str(p) for p in declared]
    if not wanted:
        raise PayloadError("nothing was declared; pass the paths to remove explicitly")
    not_orphans = sorted(set(wanted) - set(orphans))
    if not_orphans:
        raise PayloadError(
            "declared for removal but still referenced by a pkginfo in the checkout: "
            + ", ".join(not_orphans)
            + " — nothing was removed; a live payload is not removable by this command"
        )

    results: List[Tuple[str, str]] = []
    records = []
    for relpath in wanted:
        stat = target.stat(relpath)
        if stat is None:
            results.append((relpath, "already absent"))
            continue
        if dry_run:
            results.append((relpath, f"would remove {stat.size} bytes ({stat.sha256[:16]})"))
            continue
        target.remove(relpath)
        if target.stat(relpath) is not None:
            raise PayloadError(f"{relpath} is still present after removal")
        records.append({"path": relpath, "bytes": stat.size, "sha256": stat.sha256,
                        "at": at, "approved_by": approved_by, "reason": reason})
        results.append((relpath, f"removed {stat.size} bytes, recorded as {stat.sha256[:16]}"))

    if records and not dry_run:
        path = os.path.join(source_root, PAYLOAD_REMOVALS_PATH)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            for record in records:
                fh.write(json.dumps(record, sort_keys=True) + "\n")
    return results
