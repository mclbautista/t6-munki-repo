"""Drift between the checkout and the target, and integrity of what a target serves.

Two questions, deliberately separate:

- **Drift:** does the target hold exactly the metadata this checkout describes? A file only on the
  target is the case the pre-publish gate cannot see, because the gate reasons about what is being
  changed rather than about what is already there.
- **Integrity:** if a Mac resolved its manifest today, could every item it is offered actually be
  installed? A catalog entry with no payload, an item a manifest references that no catalog serves,
  a catalog whose membership disagrees with what the pkginfos declare, and duplicate names are each
  a way the answer is "no" while everything looks fine.

Both are read-only and need no credentials: they read the checkout and the target.
"""
from __future__ import annotations

import os
import plistlib
import urllib.parse
from dataclasses import dataclass, field
from typing import Dict, List, Set

from .targets import LocalDirTarget, TargetError

DRIFT_DIRS = ("pkgsinfo", "manifests", "icons", "catalogs")
MANIFEST_SECTIONS = ("managed_installs", "optional_installs", "managed_updates",
                     "managed_uninstalls", "featured_items")


def repo_url(base: str, relpath: str) -> str:
    """The HTTP URL for a published file. Paths need encoding: a manifest is named `303B iMac`."""
    return f"{base.rstrip('/')}/{urllib.parse.quote(relpath)}"


@dataclass
class DriftReport:
    missing_on_target: List[str] = field(default_factory=list)
    missing_in_checkout: List[str] = field(default_factory=list)
    differing: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.missing_on_target or self.missing_in_checkout or self.differing)

    def describe(self) -> str:
        return (f"missing on the target {len(self.missing_on_target)}, "
                f"only on the target {len(self.missing_in_checkout)}, "
                f"differing {len(self.differing)}")


def _checkout_listing(source_root: str, dirs=DRIFT_DIRS) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for d in dirs:
        base = os.path.join(source_root, d)
        if not os.path.isdir(base):
            continue
        for dirpath, _, files in os.walk(base):
            for f in files:
                if f.startswith(".") or f.endswith(".tmp"):
                    continue
                full = os.path.join(dirpath, f)
                with open(full, "rb") as fh:
                    import hashlib
                    out[os.path.relpath(full, source_root)] = hashlib.sha256(fh.read()).hexdigest()
    return out


def drift(source_root: str, target, dirs=DRIFT_DIRS) -> DriftReport:
    """Compare the checkout against the target, in both directions."""
    source_root = os.path.abspath(source_root)
    local = _checkout_listing(source_root, dirs)
    if isinstance(target, LocalDirTarget):
        remote = {}
        for d in dirs:
            base = os.path.join(target.root, d)
            if not os.path.isdir(base):
                continue
            for dirpath, _, files in os.walk(base):
                for f in files:
                    if f.startswith(".") or f.endswith(".tmp"):
                        continue
                    full = os.path.join(dirpath, f)
                    with open(full, "rb") as fh:
                        import hashlib
                        remote[os.path.relpath(full, target.root)] = hashlib.sha256(fh.read()).hexdigest()
    else:
        remote = {}
        for relpath in target.list_files(dirs):
            info = target.stat(relpath)
            if info is not None:
                remote[relpath] = info.sha256

    report = DriftReport()
    report.missing_on_target = sorted(set(local) - set(remote))
    report.missing_in_checkout = sorted(set(remote) - set(local))
    report.differing = sorted(p for p in set(local) & set(remote) if local[p] != remote[p])
    return report


@dataclass
class Finding:
    kind: str
    subject: str
    detail: str
    manifests: List[str] = field(default_factory=list)


@dataclass
class IntegrityReport:
    findings: List[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.findings

    def kinds(self) -> Set[str]:
        return {f.kind for f in self.findings}

    def describe(self) -> str:
        if self.ok:
            return "no integrity findings"
        counts: Dict[str, int] = {}
        for f in self.findings:
            counts[f.kind] = counts.get(f.kind, 0) + 1
        return ", ".join(f"{kind} {count}" for kind, count in sorted(counts.items()))


def _read_plist(path: str):
    with open(path, "rb") as fh:
        return plistlib.load(fh)


def load_manifests(source_root: str) -> Dict[str, dict]:
    manifests_dir = os.path.join(source_root, "manifests")
    out: Dict[str, dict] = {}
    if not os.path.isdir(manifests_dir):
        return out
    for entry in sorted(os.listdir(manifests_dir)):
        path = os.path.join(manifests_dir, entry)
        if os.path.isfile(path) and not entry.startswith("."):
            try:
                out[entry] = _read_plist(path)
            except Exception:
                out[entry] = {}
    return out


@dataclass
class Chain:
    primary: str
    names: List[str] = field(default_factory=list)
    catalogs: List[str] = field(default_factory=list)
    items: Dict[str, List[str]] = field(default_factory=dict)   # item -> sections referencing it
    unresolved: List[str] = field(default_factory=list)


def resolve_chain(primary: str, manifests: Dict[str, dict]) -> Chain:
    """Follow `included_manifests` from a machine manifest, unioning the sections it reaches."""
    chain = Chain(primary=primary)
    seen: Set[str] = set()
    pending = [primary]
    while pending:
        name = pending.pop(0)
        if name in seen:
            continue
        seen.add(name)
        manifest = manifests.get(name)
        if manifest is None:
            chain.unresolved.append(name)
            continue
        chain.names.append(name)
        for catalog in manifest.get("catalogs") or []:
            if catalog not in chain.catalogs:
                chain.catalogs.append(catalog)
        for section in MANIFEST_SECTIONS:
            for entry in manifest.get(section) or []:
                chain.items.setdefault(entry, []).append(f"{name}:{section}")
        pending.extend(manifest.get("included_manifests") or [])
    return chain


def catalog_membership(source_root: str) -> Dict[str, Set[str]]:
    """Which pkginfos declare membership of which catalog, read from the checkout."""
    membership: Dict[str, Set[str]] = {}
    pkgsinfo = os.path.join(source_root, "pkgsinfo")
    for dirpath, _, files in os.walk(pkgsinfo):
        for f in files:
            if f.startswith("."):
                continue
            if not f.endswith((".pkginfo", ".plist")):
                continue
            try:
                pkginfo = _read_plist(os.path.join(dirpath, f))
            except Exception:
                continue
            name = pkginfo.get("name")
            for catalog in pkginfo.get("catalogs") or []:
                membership.setdefault(catalog, set()).add(name)
    return membership


def item_locations(source_root: str) -> Dict[str, str]:
    """Item name -> installer item location, from the checkout's pkginfos."""
    out: Dict[str, str] = {}
    pkgsinfo = os.path.join(source_root, "pkgsinfo")
    for dirpath, _, files in os.walk(pkgsinfo):
        for f in files:
            if f.startswith(".") or not f.endswith((".pkginfo", ".plist")):
                continue
            try:
                pkginfo = _read_plist(os.path.join(dirpath, f))
            except Exception:
                continue
            name = pkginfo.get("name")
            if name:
                out.setdefault(name, pkginfo.get("installer_item_location"))
    return out


def integrity(source_root: str, target, catalogs_dir: str = "catalogs") -> IntegrityReport:
    """Can every item a machine manifest offers actually be installed from this target?"""
    source_root = os.path.abspath(source_root)
    report = IntegrityReport()
    manifests = load_manifests(source_root)
    membership = catalog_membership(source_root)
    locations = item_locations(source_root)

    # 1. catalog membership: what each catalog serves vs what the pkginfos declare
    catalogs_path = os.path.join(source_root, catalogs_dir)
    served_items: Dict[str, Set[str]] = {}
    if os.path.isdir(catalogs_path):
        for name in sorted(os.listdir(catalogs_path)):
            path = os.path.join(catalogs_path, name)
            if not os.path.isfile(path) or name.startswith("."):
                continue
            try:
                data = plistlib.loads(open(path, "rb").read())
            except Exception:
                continue
            entries = data if isinstance(data, list) else data.get("items", [])
            served_items[name] = {e.get("name") for e in entries if e.get("name")}
            seen = {}
            for e in entries:
                seen.setdefault(e.get("name"), []).append(e)
            for item_name, duplicates in seen.items():
                if len(duplicates) > 1:
                    report.findings.append(Finding(
                        kind="duplicate_name", subject=item_name,
                        detail=f"{len(duplicates)} entries share this name in catalogs/{name}; "
                               f"Munki takes the first, so which installer a client receives "
                               f"depends on build order",
                    ))
    for catalog, declared in sorted(membership.items()):
        served = served_items.get(catalog, set())
        for item_name in sorted(declared - served):
            report.findings.append(Finding(
                kind="catalog_membership_mismatch", subject=item_name,
                detail=f"declares catalogs/{catalog} but is not in it"))
        for item_name in sorted(served - declared):
            if item_name not in locations:
                continue          # a stale entry for an item the checkout no longer describes
            report.findings.append(Finding(
                kind="catalog_membership_mismatch", subject=item_name,
                detail=f"is in catalogs/{catalog} but does not declare it"))

    # 2. every item any machine manifest reaches must exist in its chain's catalogs, with a payload
    # A machine manifest is a manifest nothing else includes: it is the entry point a client
    # resolves. Identifying them by shape instead would miss a chain whose root is included by
    # nothing yet happens to declare no catalogs of its own.
    included_by_another = {included for body in manifests.values()
                            for included in (body.get("included_manifests") or [])}
    machine_manifests = sorted(set(manifests) - included_by_another)
    for name in machine_manifests:
        chain = resolve_chain(name, manifests)
        for missing in chain.unresolved:
            report.findings.append(Finding(
                kind="manifest_unresolved", subject=missing,
                detail=f"included manifest not found in the repository (reached from {name})",
                manifests=[name]))
        for item_name, sections in sorted(chain.items.items()):
            served_by = {c for c in chain.catalogs if item_name in served_items.get(c, set())}
            if not served_by:
                report.findings.append(Finding(
                    kind="item_not_in_catalog", subject=item_name,
                    detail=f"referenced but no catalog in this chain serves it "
                           f"({', '.join(chain.catalogs)})",
                    manifests=[name]))
                continue
            location = locations.get(item_name)
            if location is None:
                continue          # no pkginfo in the checkout: reported above when it matters
            payload = f"pkgs/{location}"
            if not target.exists(payload):
                report.findings.append(Finding(
                    kind="payload_missing", subject=item_name,
                    detail=f"payload not present on the target: {payload}",
                    manifests=[name]))
    return report


def check(source_root: str, target, dirs=DRIFT_DIRS) -> tuple:
    """Both checks, in the order a reader wants them."""
    return drift(source_root, target, dirs), integrity(source_root, target)
