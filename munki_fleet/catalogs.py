"""Catalog building and the pre-publish diff guard.

`build_catalogs` shells out to the Munki `makecatalogs` tool against the metadata tree. Payload
existence is deliberately *not* checked here (`--skip-pkg-check`): the payloads live on the NAS,
not in the checkout, and verifying that every referenced item actually has a payload is the drift
and integrity check's job, against the published tree.
"""
from __future__ import annotations

import os
import plistlib
import subprocess
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

DEFAULT_MAKECATALOGS = "/usr/local/munki/makecatalogs"


class CatalogError(Exception):
    """Catalogs could not be built or read."""


@dataclass
class BuildResult:
    catalogs: Dict[str, bytes] = field(default_factory=dict)
    output: str = ""

    @property
    def names(self) -> List[str]:
        return sorted(self.catalogs)


def default_runner(metadata_root: str, skip_pkg_check: bool = True) -> int:
    """Run the real Munki `makecatalogs` against the metadata tree."""
    argv = [DEFAULT_MAKECATALOGS]
    if skip_pkg_check:
        argv.append("--skip-pkg-check")
    argv.append(metadata_root)
    completed = subprocess.run(argv, capture_output=True)
    print(completed.stdout.decode("utf-8", "replace"), end="")
    return completed.returncode


def build_catalogs(metadata_root: str, runner: Optional[Callable[..., int]] = None) -> BuildResult:
    """Build catalogs from the metadata tree and return them as bytes, keyed by catalog name."""
    runner = runner or default_runner
    metadata_root = os.path.abspath(metadata_root)
    returncode = runner(metadata_root, skip_pkg_check=True)
    if returncode != 0:
        raise CatalogError(f"makecatalogs exited {returncode} for {metadata_root}")
    catalogs_dir = os.path.join(metadata_root, "catalogs")
    if not os.path.isdir(catalogs_dir):
        raise CatalogError(f"makecatalogs produced no catalogs directory in {metadata_root}")
    result = BuildResult()
    for entry in sorted(os.listdir(catalogs_dir)):
        if entry.startswith("."):
            continue
        path = os.path.join(catalogs_dir, entry)
        if os.path.isfile(path):
            with open(path, "rb") as fh:
                result.catalogs[entry] = fh.read()
    if not result.catalogs:
        raise CatalogError(f"no catalogs found in {catalogs_dir} after a successful build")
    return result


@dataclass
class CatalogDiff:
    added: List[str] = field(default_factory=list)
    removed: List[str] = field(default_factory=list)
    changed: Dict[str, List[str]] = field(default_factory=dict)
    duplicate_names: List[str] = field(default_factory=list)
    duplicate_order_changed: List[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.changed or self.duplicate_names
                    or self.duplicate_order_changed)

    def has_item_changes(self) -> bool:
        return bool(self.added or self.removed or self.changed)

    def describe(self) -> str:
        if self.is_empty():
            return "no item-level changes"
        parts = []
        if self.added:
            parts.append(f"added: {', '.join(self.added)}")
        if self.removed:
            parts.append(f"removed: {', '.join(self.removed)}")
        if self.changed:
            parts.append("changed: " + "; ".join(
                f"{name} ({', '.join(keys)})" for name, keys in sorted(self.changed.items())
            ))
        if self.duplicate_names:
            parts.append(f"duplicate names: {', '.join(self.duplicate_names)}")
        if self.duplicate_order_changed:
            parts.append(f"duplicate-name order changed: {', '.join(self.duplicate_order_changed)}")
        return " | ".join(parts)


def _load_items(catalog_bytes: bytes):
    """Return the item list from a catalog.

    `makecatalogs` writes the items as a top-level array; the dict-with-`items` shape also occurs
    in the wild, so both are accepted. Anything else is not a catalog.
    """
    try:
        catalog = plistlib.loads(catalog_bytes)
    except Exception as exc:  # a catalog that cannot be parsed is not a catalog
        raise CatalogError(f"catalog is not a readable plist: {exc}") from exc
    if isinstance(catalog, list):
        return catalog
    if isinstance(catalog, dict):
        items = catalog.get("items", [])
        if isinstance(items, list):
            return items
    raise CatalogError(f"catalog has an unexpected shape: {type(catalog).__name__}")


def _items_by_name(catalog_bytes: bytes) -> Dict[str, dict]:
    items = _load_items(catalog_bytes)
    by_name: Dict[str, dict] = {}
    for item in items:
        name = item.get("name")
        if name in by_name:
            # Keep the first, but remember the collision: the live repository carries two
            # pkginfos for the same name+version and a diff must not silently hide that.
            by_name.setdefault("__dupes__", []).append(name)
            continue
        if name:
            by_name[name] = item
    return by_name


def _entries_by_name(catalog_bytes: bytes) -> Dict[str, List[dict]]:
    by_name: Dict[str, List[dict]] = {}
    for entry in _load_items(catalog_bytes):
        name = entry.get("name")
        if name:
            by_name.setdefault(name, []).append(entry)
    return by_name


def _canon(entry: dict) -> tuple:
    return tuple(sorted((k, repr(v)) for k, v in entry.items()))


def compare_catalogs(old_bytes: bytes, new_bytes: bytes) -> CatalogDiff:
    """Item-level diff between two catalogs, used to gate a publish.

    Two entries can share one name in this repository (the Firefox and GoogleChrome pkginfos). For
    those, a *reordering* is not a key change but is still meaningful: Munki takes the first entry
    matching a name, so an order swap changes which installer a client receives. Reordering and
    real change are therefore reported separately.
    """
    old = _entries_by_name(old_bytes)
    new = _entries_by_name(new_bytes)

    diff = CatalogDiff(duplicate_names=sorted(
        name for name in set(old) | set(new) if len(old.get(name, [])) > 1 or len(new.get(name, [])) > 1
    ))
    diff.added = sorted(set(new) - set(old))
    diff.removed = sorted(set(old) - set(new))

    for name in sorted(set(old) & set(new)):
        old_entries, new_entries = old[name], new[name]
        if len(old_entries) == 1 and len(new_entries) == 1:
            keys = sorted({k for k in set(old_entries[0]) | set(new_entries[0])
                           if old_entries[0].get(k) != new_entries[0].get(k)})
        else:
            # Per-key multiset comparison, so reordering alone never shows up as a key change.
            all_keys = set().union(*[set(e) for e in old_entries + new_entries])
            keys = sorted(
                k for k in all_keys
                if sorted(repr(e.get(k)) for e in old_entries) != sorted(repr(e.get(k)) for e in new_entries)
            )
        if keys:
            diff.changed[name] = keys
        old_seq = [_canon(e) for e in old_entries]
        new_seq = [_canon(e) for e in new_entries]
        if not keys and sorted(old_seq) == sorted(new_seq) and old_seq != new_seq:
            diff.duplicate_order_changed.append(name)
    return diff
