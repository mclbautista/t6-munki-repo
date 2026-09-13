"""Promotion from `testing` to `production`: the one event that makes an item fleet-wide.

The ring is only real if promotion is refused without evidence and recorded with enough detail to
answer "who let this onto the fleet, on what proof, and when" (ADR 0003). This module owns that
record; the pkginfo's own `catalogs` array stays the state, and `data/promotions.jsonl` is the
history of how it got there.

None of this publishes: it edits the checkout. Getting the result in front of clients is the publish
path's job, and the pre-publish gate still has to pass (ADR 0009).
"""
from __future__ import annotations

import hashlib
import json
import os
import plistlib
import re
from datetime import datetime
from dataclasses import asdict, dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .drift import ITEM_EXTENSIONS, _iter_pkginfos, load_manifests

TESTING = "testing"
PRODUCTION = "production"
PROMOTIONS_PATH = os.path.join("data", "promotions.jsonl")
MANIFEST_IDENTIFIERS = ("hostname", "display_name")


class PromotionError(Exception):
    """A promotion or demotion could not be made safely."""


@dataclass
class PromotionRecord:
    item: str
    version: str
    action: str                      # promote | demote
    from_catalogs: List[str]
    to_catalogs: List[str]
    at: str
    approved_by: str
    evidence: List[str] = field(default_factory=list)
    reason: str = ""
    pkginfo_path: str = ""
    pkginfo_sha256: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)

    @classmethod
    def from_json(cls, line: str) -> "PromotionRecord":
        return cls(**json.loads(line))


def _now() -> str:
    """The promotion's own timestamp, in the facility's timezone."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def sha256_file(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def find_pkginfo(source_root: str, name: str, version: str) -> Tuple[str, dict]:
    """Locate the pkginfo for an item, whatever its extension or nesting."""
    seen = []
    for path, pkginfo in _iter_pkginfos(source_root):
        if pkginfo.get("name") == name:
            seen.append((path, pkginfo))
            if str(pkginfo.get("version")) == str(version):
                return path, pkginfo
    if seen:
        raise PromotionError(
            f"{name} exists but not at version {version}; found "
            + ", ".join(sorted(str(p.get('version')) for _, p in seen))
        )
    raise PromotionError(f"no pkginfo for item {name!r} in the checkout")


def write_pkginfo_catalogs(path: str, catalogs: Sequence[str]) -> None:
    with open(path, "rb") as fh:
        pkginfo = plistlib.load(fh)
    pkginfo["catalogs"] = list(catalogs)
    with open(path, "wb") as fh:
        plistlib.dump(pkginfo, fh, sort_keys=True)


def set_manifest_catalogs(path: str, catalogs: Sequence[str]) -> None:
    """Replace a manifest's catalog list in place, leaving the rest of the file byte-identical.

    A text edit rather than a re-serialisation: these files are published, and rewriting the plist
    would change formatting across all of them for no reason. Refuses loudly if the expected
    structure is not there.
    """
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    values = "".join(f"\t\t<string>{c}</string>\n" for c in catalogs)
    pattern = re.compile(r"(<key>catalogs</key>\s*<array>\n)(.*?)(\t</array>)", re.S)
    if not pattern.search(text):
        raise PromotionError(f"{path} has no catalogs array to edit")
    replacement = pattern.sub(lambda m: m.group(1) + values + m.group(3), text, count=1)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(replacement)


def _append_record(source_root: str, record: PromotionRecord) -> None:
    path = os.path.join(source_root, PROMOTIONS_PATH)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(record.to_json() + "\n")


def load_history(source_root: str) -> List[PromotionRecord]:
    path = os.path.join(source_root, PROMOTIONS_PATH)
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8") as fh:
        return [PromotionRecord.from_json(line) for line in fh if line.strip()]


def _record(source_root: str, item: str, version: str, action: str, from_catalogs: List[str],
            to_catalogs: List[str], at: str, approved_by: str, evidence: List[str] = (),
            reason: str = "", path: str = "") -> PromotionRecord:
    record = PromotionRecord(item=item, version=str(version), action=action,
                             from_catalogs=from_catalogs, to_catalogs=to_catalogs, at=at,
                             approved_by=approved_by, evidence=list(evidence), reason=reason,
                             pkginfo_path=os.path.relpath(path, source_root),
                             pkginfo_sha256=sha256_file(path))
    _append_record(source_root, record)
    return record


def promote(source_root: str, name: str, version: str, approved_by: str,
            evidence: Sequence[str], at: Optional[str] = None) -> PromotionRecord:
    """Move one item from `testing` to `production`, with the proof on the record."""
    at = at or _now()
    if not approved_by:
        raise PromotionError("a promotion must record who approved it")
    proof = [e for e in (evidence or []) if str(e).strip()]
    if not proof:
        raise PromotionError(
            "a promotion must record the pilot verification evidence; none was given, so there is "
            "nothing to say an item was tested before it reached the fleet"
        )
    path, pkginfo = find_pkginfo(source_root, name, version)
    current = list(pkginfo.get("catalogs") or [])
    if current == [PRODUCTION]:
        raise PromotionError(f"{name} {version} is already in production")
    if TESTING not in current:
        raise PromotionError(
            f"{name} {version} declares catalogs {current}, which does not include {TESTING}; "
            f"only an item in the testing ring can be promoted"
        )
    write_pkginfo_catalogs(path, [PRODUCTION])
    return _record(source_root, name, version, "promote", current, [PRODUCTION], at,
                   approved_by, proof, path=path)


def demote(source_root: str, name: str, version: str, approved_by: str, reason: str,
           at: Optional[str] = None) -> PromotionRecord:
    """Put an item back in `testing`. This is the rollback path, so it needs a reason, not proof."""
    at = at or _now()
    if not reason.strip():
        raise PromotionError("a demotion must record why")
    path, pkginfo = find_pkginfo(source_root, name, version)
    current = list(pkginfo.get("catalogs") or [])
    if current == [TESTING]:
        raise PromotionError(f"{name} {version} is already in {TESTING}")
    write_pkginfo_catalogs(path, [TESTING])
    return _record(source_root, name, version, "demote", current, [TESTING], at, approved_by,
                   [], reason, path)


RINGS_PATH = os.path.join("data", "rings.json")


def load_pilots(source_root: str) -> List[str]:
    """The declared pilot ring (ADR 0003), machine-readable in `data/rings.json`."""
    path = os.path.join(source_root, RINGS_PATH)
    if not os.path.isfile(path):
        raise PromotionError(
            f"{RINGS_PATH} is missing, so the pilot ring is undeclared; ADR 0003 names it, and a "
            f"promotion path cannot decide who tests first without it"
        )
    with open(path, "r", encoding="utf-8") as fh:
        rings = json.load(fh)
    pilots = [p["name"] for p in rings.get("pilots", [])]
    if not pilots:
        raise PromotionError(f"{RINGS_PATH} declares no pilots")
    return pilots


@dataclass
class PlannedPromotion:
    name: str
    version: str
    path: str


@dataclass
class InitialPromotionPlan:
    items: List[PlannedPromotion] = field(default_factory=list)
    manifest_changes: Dict[str, Tuple[List[str], List[str]]] = field(default_factory=dict)
    pilots: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    excluded: List[str] = field(default_factory=list)

    def describe(self) -> str:
        lines = [f"pilot ring: {', '.join(self.pilots) or 'NONE DECLARED'}"]
        if self.excluded:
            lines.append(f"{len(self.excluded)} item(s) deliberately left in {TESTING}: "
                         + ", ".join(sorted(self.excluded)))
        if self.blockers:
            lines.append(f"{len(self.blockers)} blocker(s) that must be cleared first:")
            lines += [f"  ! {b}" for b in self.blockers]
        lines.append(f"{len(self.items)} item(s) to promote to {PRODUCTION}:")
        lines += [f"  {i.name} {i.version}" for i in self.items]
        lines.append(f"{len(self.manifest_changes)} manifest(s) to repoint:")
        for name, (before, after) in sorted(self.manifest_changes.items()):
            lines.append(f"  {name}: {before} -> {after}")
        return "\n".join(lines)


def _is_machine_manifest(name: str, manifests: Dict[str, dict]) -> bool:
    included = {i for body in manifests.values() for i in (body.get("included_manifests") or [])}
    return name not in included


def initial_promotion_plan(source_root: str, pilots: Iterable[str],
                           exclude: Iterable[str] = ()) -> InitialPromotionPlan:
    """What the one-off event would do: every live item into production, every manifest repointed.

    Nothing may be lost in it — a client that reads `production` must still find everything the
    testing catalog was serving — which is why it is a single planned, approved event.

    `exclude` exists because "everything currently live" is not the same as "everything required":
    test artifacts and items awaiting a withdrawal decision are live today, and promoting them to
    production would carry the mess one ring over instead of fixing it. Who belongs in that list is
    a human decision (ADR 0008), so it is an input, not a policy this module invents.
    """
    pilots = set(pilots)
    exclude = {str(e) for e in exclude}
    plan = InitialPromotionPlan(pilots=sorted(pilots))
    manifests_present = set(load_manifests(source_root))
    for pilot in sorted(pilots):
        if pilot not in manifests_present:
            plan.blockers.append(
                f"pilot {pilot} has no manifest of its own, so it cannot read the testing catalog; "
                f"it resolves to site_default instead"
            )
    for path, pkginfo in _iter_pkginfos(source_root):
        if TESTING in (pkginfo.get("catalogs") or []) and pkginfo.get("name") not in exclude:
            plan.items.append(PlannedPromotion(name=pkginfo.get("name"),
                                               version=str(pkginfo.get("version")),
                                               path=os.path.relpath(path, source_root)))
    plan.excluded = sorted(exclude)
    plan.items.sort(key=lambda p: (p.name, p.version))

    manifests = load_manifests(source_root)
    for name, body in sorted(manifests.items()):
        before = list(body.get("catalogs") or [])
        desired = [TESTING, PRODUCTION] if (name in pilots and _is_machine_manifest(name, manifests)) \
            else [PRODUCTION]
        if before != desired:
            plan.manifest_changes[name] = (before, desired)
    return plan
