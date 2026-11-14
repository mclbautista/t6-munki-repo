"""Drift between the checkout and the target, and integrity of what a target serves.

Two questions, deliberately separate:

- **Drift:** does the target hold exactly the metadata this checkout describes? A file only on the
  target is the case the pre-publish gate cannot see, because the gate reasons about what is being
  changed rather than about what is already published.
- **Integrity:** if a Mac resolved its manifest today, could every item it is offered actually be
  installed? An item a manifest references that no catalog serves, an item with no pkginfo at all, a
  catalog entry whose payload is not on the target, a catalog whose membership disagrees with what
  the pkginfos declare, and duplicate names are each a way the answer is "no" while everything looks
  fine.

Both are read-only and need no interactive credential: they read the checkout and the target.

Reading the target costs one multiplexed SSH round trip per file, which is why drift covers the
metadata tree (~100 small files) and not the payloads: payload existence is integrity's question
and is answered without reading the file.
"""
from __future__ import annotations

import hashlib
import os
import plistlib
import urllib.parse
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Set, Tuple

from .catalogs import CatalogError, _load_items, compare_catalogs
from .targets import TargetError

DRIFT_DIRS = ("pkgsinfo", "manifests", "icons", "catalogs")
# Every section a manifest can reference an item from. `conditional_items` is a list of dicts and
# is handled separately.
MANIFEST_SECTIONS = ("managed_installs", "optional_installs", "managed_updates",
                     "managed_uninstalls", "forced_installs", "default_installs")
ITEM_EXTENSIONS = (".pkginfo", ".plist")


def repo_url(base: str, relpath: str) -> str:
    """The HTTP URL for a published file. Paths need encoding: a manifest is named `303B iMac`."""
    return f"{base.rstrip('/')}/{urllib.parse.quote(relpath)}"


def _sha256_file(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _is_metadata_file(name: str) -> bool:
    return not name.startswith(".") and not name.endswith(".tmp")


@dataclass
class DriftReport:
    missing_on_target: List[str] = field(default_factory=list)
    only_on_target: List[str] = field(default_factory=list)
    differing: List[str] = field(default_factory=list)
    unreadable: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.missing_on_target or self.only_on_target or self.differing
                    or self.unreadable)

    def describe(self) -> str:
        return (f"missing on the target {len(self.missing_on_target)}, "
                f"only on the target {len(self.only_on_target)}, "
                f"differing {len(self.differing)}, "
                f"unreadable {len(self.unreadable)}")


def _checkout_hashes(source_root: str, dirs) -> Dict[str, str]:
    """Hash every metadata file in the checkout."""
    out: Dict[str, str] = {}
    for d in dirs:
        base = os.path.join(source_root, d)
        if not os.path.isdir(base):
            continue
        for dirpath, _, files in os.walk(base):
            for name in files:
                if not _is_metadata_file(name):
                    continue
                full = os.path.join(dirpath, name)
                out[os.path.relpath(full, source_root)] = _sha256_file(full)
    return out


def drift(source_root: str, target, dirs=DRIFT_DIRS) -> DriftReport:
    """Compare the checkout against the target, in both directions.

    The target is only ever read through its own interface, so the same code covers a local
    directory and the NAS. A file the target cannot be read for is reported as unreadable rather
    than as absent — a failed read must not look like an empty target.
    """
    source_root = os.path.abspath(source_root)
    local = _checkout_hashes(source_root, dirs)

    remote: Dict[str, str] = {}
    unreadable: List[str] = []
    for relpath in target.list_files(dirs):
        if not _is_metadata_file(os.path.basename(relpath)):
            continue
        try:
            info = target.stat(relpath)
        except TargetError:
            unreadable.append(relpath)
            continue
        if info is not None:
            remote[relpath] = info.sha256

    report = DriftReport()
    report.missing_on_target = sorted(set(local) - set(remote))
    report.only_on_target = sorted(set(remote) - set(local))
    report.differing = sorted(p for p in set(local) & set(remote) if local[p] != remote[p])
    report.unreadable = sorted(unreadable)
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
    membership_source: str = "unknown"

    @property
    def ok(self) -> bool:
        return not self.findings

    def kinds(self) -> Set[str]:
        return {f.kind for f in self.findings}

    def describe(self) -> str:
        if self.ok:
            return f"no integrity findings (membership checked against {self.membership_source})"
        counts: Dict[str, int] = {}
        for f in self.findings:
            counts[f.kind] = counts.get(f.kind, 0) + 1
        return (", ".join(f"{kind} {count}" for kind, count in sorted(counts.items()))
                + f" (membership checked against {self.membership_source})")


def _read_plist(path: str):
    with open(path, "rb") as fh:
        return plistlib.load(fh)


def _iter_pkginfos(source_root: str) -> Iterable[Tuple[str, dict]]:
    """Every pkginfo in the checkout, whatever its extension or nesting.

    `makecatalogs` walks nested directories and ignores the extension, and so does this: an item can
    be live while being invisible to anyone reading only the top level of `pkgsinfo/`.
    """
    pkgsinfo = os.path.join(source_root, "pkgsinfo")
    for dirpath, _, files in os.walk(pkgsinfo):
        for name in sorted(files):
            if name.startswith(".") or not name.endswith(ITEM_EXTENSIONS):
                continue
            path = os.path.join(dirpath, name)
            try:
                yield path, _read_plist(path)
            except Exception:
                continue


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


def _items_from_conditional(entry: dict) -> List[str]:
    names: List[str] = []
    for section in MANIFEST_SECTIONS:
        names.extend(entry.get(section) or [])
    return names


def resolve_chain(primary: str, manifests: Dict[str, dict]) -> Chain:
    """Follow `included_manifests` from a machine manifest, unioning every section it reaches.

    Conditional items are followed too: an item offered behind a condition is still an item the
    client may be asked to install, so it must resolve like any other.
    """
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
        for index, conditional in enumerate(manifest.get("conditional_items") or []):
            if not isinstance(conditional, dict):
                continue
            label = conditional.get("condition", f"#{index}")
            for item_name in _items_from_conditional(conditional):
                chain.items.setdefault(item_name, []).append(f"{name}:conditional({label})")
        pending.extend(manifest.get("included_manifests") or [])
    return chain


def catalog_membership(source_root: str) -> Dict[str, Set[str]]:
    """Which pkginfos declare membership of which catalog, read from the checkout."""
    membership: Dict[str, Set[str]] = {}
    for _, pkginfo in _iter_pkginfos(source_root):
        name = pkginfo.get("name")
        for catalog in pkginfo.get("catalogs") or []:
            membership.setdefault(catalog, set()).add(name)
    return membership


def item_locations(source_root: str) -> Dict[str, List[str]]:
    """Item name -> every installer item location the checkout declares for it.

    A list, not a single location: the repository carried two pkginfos for Firefox and two for
    GoogleChrome, and checking only one of them would report coverage that does not exist.
    """
    out: Dict[str, List[str]] = {}
    for _, pkginfo in _iter_pkginfos(source_root):
        name = pkginfo.get("name")
        location = pkginfo.get("installer_item_location")
        if name and location and location not in out.setdefault(name, []):
            out[name].append(location)
    for locations in out.values():
        locations.sort()
    return out


def _catalog_items(catalog_bytes: bytes) -> Dict[str, List[dict]]:
    by_name: Dict[str, List[dict]] = {}
    for entry in _load_items(catalog_bytes):
        if entry.get("name"):
            by_name.setdefault(entry["name"], []).append(entry)
    return by_name


def _served_catalogs(source_root: str, target, names: List[str]):
    """Read the catalogs the target serves, falling back to the checkout's build.

    Membership is a statement about what a client receives, so the served catalog is the honest
    source; when the target has none yet the build is used and the report says so.
    """
    served: Dict[str, bytes] = {}
    for name in names:
        try:
            data = target.read(f"catalogs/{name}")
        except TargetError:
            continue
        if data:
            served[name] = data
    if served:
        return served, "the served catalogs"
    built: Dict[str, bytes] = {}
    for name in names:
        path = os.path.join(source_root, "catalogs", name)
        if os.path.isfile(path):
            with open(path, "rb") as fh:
                built[name] = fh.read()
    return built, "the checkout's built catalogs (the target has none to read)"


def integrity(source_root: str, target) -> IntegrityReport:
    """Can every item a machine manifest offers actually be installed from this target?"""
    source_root = os.path.abspath(source_root)
    report = IntegrityReport()
    manifests = load_manifests(source_root)
    membership = catalog_membership(source_root)
    locations = item_locations(source_root)

    catalog_names = sorted(set(membership) | {n for n in os.listdir(os.path.join(source_root, "catalogs"))
                                              if os.path.isfile(os.path.join(source_root, "catalogs", n))}
                           if os.path.isdir(os.path.join(source_root, "catalogs")) else set(membership))
    served, report.membership_source = _served_catalogs(source_root, target, catalog_names)

    served_items: Dict[str, Set[str]] = {}
    for name in sorted(served):
        try:
            entries = _catalog_items(served[name])
        except CatalogError as exc:
            report.findings.append(Finding(kind="catalog_unreadable", subject=f"catalogs/{name}",
                                           detail=str(exc)))
            continue
        served_items[name] = set(entries)
        # Reuse the diff's duplicate detection rather than a second implementation of it.
        for duplicate in compare_catalogs(served[name], served[name]).duplicate_names:
            report.findings.append(Finding(
                kind="duplicate_name", subject=duplicate,
                detail=f"{len(entries[duplicate])} entries share this name in catalogs/{name}; "
                       f"Munki takes the first, so which installer a client receives depends on "
                       f"build order"))

    for catalog, declared in sorted(membership.items()):
        if catalog not in served_items:
            continue
        for item_name in sorted(declared - served_items[catalog]):
            report.findings.append(Finding(
                kind="catalog_membership_mismatch", subject=item_name,
                detail=f"declares catalogs/{catalog} but is not in it"))
        for item_name in sorted(served_items[catalog] - declared):
            if item_name not in locations:
                report.findings.append(Finding(
                    kind="catalog_entry_without_pkginfo", subject=item_name,
                    detail=f"is in catalogs/{catalog} but the checkout has no pkginfo for it"))
            else:
                report.findings.append(Finding(
                    kind="catalog_membership_mismatch", subject=item_name,
                    detail=f"is in catalogs/{catalog} but does not declare it"))

    # A machine manifest is a manifest nothing else includes: the entry point a client resolves.
    # Identifying them by shape instead would miss a chain whose root declares no catalogs.
    included_by_another = {included for body in manifests.values()
                           for included in (body.get("included_manifests") or [])}
    for name in sorted(set(manifests) - included_by_another):
        chain = resolve_chain(name, manifests)
        for missing in chain.unresolved:
            report.findings.append(Finding(
                kind="manifest_unresolved", subject=missing,
                detail=f"included manifest not found in the repository (reached from {name})",
                manifests=[name]))
        for item_name, sections in sorted(chain.items.items()):
            served_by = [c for c in chain.catalogs if item_name in served_items.get(c, set())]
            if not served_by:
                report.findings.append(Finding(
                    kind="item_not_in_catalog", subject=item_name,
                    detail=f"referenced but no catalog in this chain serves it "
                           f"({', '.join(chain.catalogs) or 'no catalogs'})",
                    manifests=[name]))
                continue
            item_locations_for = locations.get(item_name)
            if not item_locations_for:
                report.findings.append(Finding(
                    kind="pkginfo_missing", subject=item_name,
                    detail="referenced and served, but the checkout has no pkginfo for it",
                    manifests=[name]))
                continue
            for location in item_locations_for:
                payload = f"pkgs/{location}"
                if not target.exists(payload):
                    report.findings.append(Finding(
                        kind="payload_missing", subject=item_name,
                        detail=f"payload not present on the target: {payload}",
                        manifests=[name]))
    return report


def check(source_root: str, target, dirs=DRIFT_DIRS):
    """Both checks, in the order a reader wants them."""
    return drift(source_root, target, dirs), integrity(source_root, target)
