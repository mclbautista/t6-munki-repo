"""Command line for the repository metadata publish path (ticket 02, ADR 0009).

Usage:
    python3 -m munki_fleet.cli files   --metadata-root .
    python3 -m munki_fleet.cli build   --metadata-root .
    python3 -m munki_fleet.cli publish --metadata-root . --target t6-nas:/share/ZFS23_DATA/Web/MunkiRepo \
                                       --expect-change ITEM:KEY [--expect-add ITEM] [--expect-remove ITEM] \
                                       [--expect-file PATH] [--backup-dir DIR] [--dry-run]
    python3 -m munki_fleet.cli verify  --metadata-root . --target t6-nas:/share/ZFS23_DATA/Web/MunkiRepo \
                                       [--http-base http://192.168.88.188/MunkiRepo]

There is no "publish anyway" flag. `publish` requires the caller to declare what it expects to
change — item keys, item membership, whole files — and refuses anything else, including a
same-name duplicate entry reordering and a target it cannot read. The declaration is the record of
what was authorised, so it is never bypassed silently.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import os
import sys
import urllib.request
from typing import Callable, Dict, List, Optional, Set, Tuple

from .catalogs import CatalogError, build_catalogs
from .gate import evaluate_gate
from .publish import PublishAborted, PublishError, publish, verify_served
from .targets import SshTarget, TargetError

METADATA_DIRS = ("pkgsinfo", "manifests", "icons")
GENERATED_DIRS = ("catalogs",)


def parse_target(spec: str) -> SshTarget:
    if ":" not in spec:
        raise SystemExit(f"--target must look like <ssh-host>:<absolute-path>, got {spec!r}")
    host, root = spec.split(":", 1)
    return SshTarget(host, root)


@dataclasses.dataclass
class Deps:
    """Injection seams for tests: the target, and the catalog builder's runner."""
    target_factory: Callable[[str], object] = parse_target
    catalog_runner: Optional[Callable] = None


def tracked_paths(metadata_root: str, include_generated: bool = True) -> List[str]:
    """Every file this project owns: the metadata tree, plus the generated catalogs.

    A file that exists on the target but not here is out of scope — detecting that is the drift
    and integrity check's job (ticket 03), because it needs the published tree's full listing.
    """
    dirs = METADATA_DIRS + (GENERATED_DIRS if include_generated else ())
    out = []
    for d in dirs:
        base = os.path.join(metadata_root, d)
        if not os.path.isdir(base):
            continue
        for dirpath, _, files in os.walk(base):
            for f in files:
                if f.startswith(".") or f.endswith(".tmp"):
                    continue
                out.append(os.path.relpath(os.path.join(dirpath, f), metadata_root))
    return sorted(out)


def parse_expectations(raw_values) -> Set[Tuple[str, Optional[str]]]:
    """Parse `--expect-change Item:key` (or `Item:*`) into (item, key|None) expectations."""
    expectations = set()
    for raw in raw_values or []:
        if ":" not in raw:
            raise SystemExit(f"--expect-change must look like <Item>:<key>, got {raw!r}")
        item, key = raw.split(":", 1)
        if not item:
            raise SystemExit(f"--expect-change needs an item name, got {raw!r}")
        expectations.add((item, None if key in ("", "*") else key))
    return expectations


def file_changes(metadata_root: str, target, paths: List[str]) -> Dict[str, str]:
    """Which tracked non-catalog files differ from the target, and how.

    Catalogs are excluded because the item-level diff describes them better. An unreadable target
    file is reported as unreadable rather than absent, so a transient failure cannot be mistaken
    for an empty target.
    """
    changes: Dict[str, str] = {}
    for relpath in paths:
        if relpath.startswith("catalogs/"):
            continue
        with open(os.path.join(metadata_root, relpath), "rb") as fh:
            local = hashlib.sha256(fh.read()).hexdigest()
        try:
            served = target.stat(relpath)
        except TargetError:
            changes[relpath] = "unreadable"
            continue
        if served is None:
            changes[relpath] = "added"
        elif served.sha256 != local:
            changes[relpath] = "changed"
    return changes


def http_sha256(url: str) -> str:
    with urllib.request.urlopen(url, timeout=30) as response:
        return hashlib.sha256(response.read()).hexdigest()


def cmd_files(args, deps) -> int:
    for path in tracked_paths(args.metadata_root):
        print(path)
    return 0


def cmd_build(args, deps) -> int:
    result = build_catalogs(args.metadata_root, runner=deps.catalog_runner)
    for name in result.names:
        print(f"built catalogs/{name} ({len(result.catalogs[name])} bytes)")
    return 0


def cmd_publish(args, deps) -> int:
    target = deps.target_factory(args.target)
    result = build_catalogs(args.metadata_root, runner=deps.catalog_runner)

    served: Dict[str, bytes] = {}
    for name in result.names:
        relpath = f"catalogs/{name}"
        try:
            info = target.stat(relpath)
        except TargetError as exc:
            print(f"refusing to publish: could not read {relpath} from the target: {exc}",
                  file=sys.stderr)
            return 3
        if info is not None:
            served[name] = target.read(relpath)

    paths = tracked_paths(args.metadata_root)
    decision = evaluate_gate(
        served, result.catalogs,
        expect_changes=parse_expectations(args.expect_change),
        expect_new_catalogs=set(args.expect_new_catalog or []),
        expect_additions=set(args.expect_add or []),
        expect_removals=set(args.expect_remove or []),
        expect_duplicates_resolved=set(args.expect_duplicate_resolved or []),
        file_changes=file_changes(args.metadata_root, target, paths),
        expect_files=set(args.expect_file or []),
        allow_duplicate_order_change=args.allow_duplicate_order_change,
    )
    print("== pre-publish gate ==")
    print(decision.describe())
    if not decision.allowed:
        print("refusing to publish.", file=sys.stderr)
        return 3

    if args.dry_run:
        print(f"dry run: {len(paths)} files would be published to {args.target}")
        return 0

    report = publish(args.metadata_root, target, paths, backup_dir=args.backup_dir)
    print(f"publish: {report.describe()}")
    for relpath in report.backed_up:
        print(f"  pre-image kept: {relpath}")
    served_check = verify_served(args.metadata_root, target, paths)
    print(f"filesystem verify: {served_check.describe()}")
    if not served_check.ok:
        print(f"  mismatching: {served_check.mismatching}")
        print(f"  missing: {served_check.missing}")
        return 1
    return 0


def cmd_verify(args, deps) -> int:
    target = deps.target_factory(args.target)
    paths = tracked_paths(args.metadata_root)
    served_check = verify_served(args.metadata_root, target, paths)
    print(f"filesystem verify: {served_check.describe()}")
    if served_check.mismatching:
        print(f"  mismatching: {served_check.mismatching}")
    if served_check.missing:
        print(f"  missing: {served_check.missing}")
    if args.http_base:
        bad = []
        for relpath in paths:
            with open(os.path.join(args.metadata_root, relpath), "rb") as fh:
                local = hashlib.sha256(fh.read()).hexdigest()
            try:
                remote = http_sha256(f"{args.http_base.rstrip('/')}/{relpath}")
            except Exception as exc:
                bad.append((relpath, f"unreachable: {exc}"))
                continue
            if remote != local:
                bad.append((relpath, "checksum differs from the checkout"))
        print(f"http verify against {args.http_base}: {len(paths) - len(bad)}/{len(paths)} match")
        for relpath, why in bad:
            print(f"  {relpath}: {why}")
        return 0 if (served_check.ok and not bad) else 1
    return 0 if served_check.ok else 1


def main(argv=None, deps: Optional[Deps] = None) -> int:
    deps = deps or Deps()
    parser = argparse.ArgumentParser(prog="munki_fleet.cli", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p, with_target=False, with_http=False):
        p.add_argument("--metadata-root", default=".", help="the metadata checkout (default: .)")
        if with_target:
            p.add_argument("--target", required=True, help="<ssh-host>:<absolute-path>")
        if with_http:
            p.add_argument("--http-base", default=None,
                           help="client endpoint, e.g. http://192.168.88.188/MunkiRepo")

    p = sub.add_parser("files"); common(p); p.set_defaults(func=cmd_files)
    p = sub.add_parser("build"); common(p); p.set_defaults(func=cmd_build)
    p = sub.add_parser("publish"); common(p, with_target=True)
    p.add_argument("--backup-dir", default=None, help="keep the target's pre-images here")
    p.add_argument("--expect-change", action="append", metavar="ITEM:KEY", default=[],
                   help="an item-level change this publish intends (repeatable; ITEM:* for any key)")
    p.add_argument("--expect-add", action="append", metavar="ITEM", default=[],
                   help="an item this publish intends to add to the catalog (repeatable)")
    p.add_argument("--expect-remove", action="append", metavar="ITEM", default=[],
                   help="an item this publish intends to remove from the catalog (repeatable)")
    p.add_argument("--expect-duplicate-resolved", action="append", metavar="ITEM", default=[],
                   help="a same-name duplicate entry this publish retires (repeatable)")
    p.add_argument("--expect-file", action="append", metavar="PATH", default=[],
                   help="a non-catalog file this publish intends to change (repeatable)")
    p.add_argument("--expect-new-catalog", action="append", metavar="NAME", default=[],
                   help="a catalog that does not exist on the target yet (repeatable)")
    p.add_argument("--allow-duplicate-order-change", action="store_true",
                   help="accept a reordering of same-name entries, which changes client behaviour")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_publish)
    p = sub.add_parser("verify"); common(p, with_target=True, with_http=True)
    p.set_defaults(func=cmd_verify)

    args = parser.parse_args(argv)
    try:
        return args.func(args, deps)
    except PublishAborted as exc:
        print(f"error: {exc}", file=sys.stderr)
        print(f"rollback: {exc.report.describe()}", file=sys.stderr)
        if exc.report.rollback_errors:
            for problem in exc.report.rollback_errors:
                print(f"  ROLLBACK FAILED: {problem}", file=sys.stderr)
        return 4
    except (PublishError, CatalogError, TargetError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
