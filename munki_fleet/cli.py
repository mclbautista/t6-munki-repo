"""Command line for the repository metadata publish path (ticket 02).

Usage:
    python3 -m munki_fleet.cli files   --metadata-root .
    python3 -m munki_fleet.cli build   --metadata-root .
    python3 -m munki_fleet.cli publish --metadata-root . --target t6-nas:/share/ZFS23_DATA/Web/MunkiRepo \
                                       [--backup-dir DIR] [--allow-changes] [--dry-run]
    python3 -m munki_fleet.cli verify  --metadata-root . --target t6-nas:/share/ZFS23_DATA/Web/MunkiRepo \
                                       [--http-base http://192.168.88.188/MunkiRepo]

`publish` refuses to run when the built catalogs differ from what the target currently serves,
unless `--allow-changes` is passed — and it prints the diff either way, so the change that was
authorised is on the record.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import urllib.request

from .catalogs import CatalogError, build_catalogs
from .gate import evaluate_gate
from .publish import PublishError, publish, verify_served
from .targets import SshTarget, TargetError

METADATA_DIRS = ("pkgsinfo", "manifests", "icons")
GENERATED_DIRS = ("catalogs",)


def parse_target(spec: str):
    if ":" not in spec:
        raise SystemExit(f"--target must look like <ssh-host>:<absolute-path>, got {spec!r}")
    host, root = spec.split(":", 1)
    return SshTarget(host, root)


def tracked_paths(metadata_root: str, include_generated: bool = True) -> list:
    """Every file this project owns: the metadata tree, plus the generated catalogs."""
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


def http_sha256(url: str) -> str:
    with urllib.request.urlopen(url, timeout=30) as response:
        return hashlib.sha256(response.read()).hexdigest()


def cmd_files(args) -> int:
    for path in tracked_paths(args.metadata_root):
        print(path)
    return 0


def cmd_build(args) -> int:
    result = build_catalogs(args.metadata_root)
    for name in result.names:
        print(f"built catalogs/{name} ({len(result.catalogs[name])} bytes)")
    return 0


def parse_expectations(raw_values) -> set:
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


def cmd_publish(args) -> int:
    target = parse_target(args.target)
    result = build_catalogs(args.metadata_root)

    served = {}
    for name in result.names:
        try:
            served[name] = target.read(f"catalogs/{name}")
        except TargetError:
            pass  # absent on the target: the gate treats it as a new catalog

    decision = evaluate_gate(
        served, result.catalogs,
        expect_changes=parse_expectations(args.expect_change),
        expect_new_catalogs=set(args.expect_new_catalog or []),
        allow_duplicate_order_change=args.allow_duplicate_order_change,
    )
    print("== pre-publish gate ==")
    print(decision.describe())
    if not decision.allowed:
        print("refusing to publish.", file=sys.stderr)
        return 3

    paths = tracked_paths(args.metadata_root)
    if args.dry_run:
        print(f"dry run: {len(paths)} files would be published to {args.target}")
        return 0

    report = publish(args.metadata_root, target, paths, backup_dir=args.backup_dir)
    print(f"publish: {report.describe()}")
    for relpath in report.backed_up:
        print(f"  pre-image kept: {relpath}")
    served = verify_served(args.metadata_root, target, paths)
    print(f"filesystem verify: {served.describe()}")
    if not served.ok:
        print(f"  mismatching: {served.mismatching}")
        print(f"  missing: {served.missing}")
        return 1
    return 0


def cmd_verify(args) -> int:
    target = parse_target(args.target)
    paths = tracked_paths(args.metadata_root)
    served = verify_served(args.metadata_root, target, paths)
    print(f"filesystem verify: {served.describe()}")
    if served.mismatching:
        print(f"  mismatching: {served.mismatching}")
    if served.missing:
        print(f"  missing: {served.missing}")
    if args.http_base:
        bad = []
        for relpath in paths:
            with open(os.path.join(args.metadata_root, relpath), "rb") as fh:
                local = hashlib.sha256(fh.read()).hexdigest()
            url = f"{args.http_base.rstrip('/')}/{relpath}"
            try:
                remote = http_sha256(url)
            except Exception as exc:
                bad.append((relpath, f"unreachable: {exc}"))
                continue
            if remote != local:
                bad.append((relpath, "checksum differs from the checkout"))
        print(f"http verify against {args.http_base}: {len(paths) - len(bad)}/{len(paths)} match")
        for relpath, why in bad:
            print(f"  {relpath}: {why}")
        return 0 if (served.ok and not bad) else 1
    return 0 if served.ok else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="munki_fleet.cli", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p, with_target=False, with_http=False):
        p.add_argument("--metadata-root", default=".", help="the metadata checkout (default: .)")
        if with_target:
            p.add_argument("--target", required=True, help="<ssh-host>:<absolute-path>")
        if with_http:
            p.add_argument("--http-base", default=None, help="client endpoint, e.g. http://192.168.88.188/MunkiRepo")

    p = sub.add_parser("files"); common(p); p.set_defaults(func=cmd_files)
    p = sub.add_parser("build"); common(p); p.set_defaults(func=cmd_build)
    p = sub.add_parser("publish"); common(p, with_target=True)
    p.add_argument("--backup-dir", default=None, help="keep the target's pre-images here")
    p.add_argument("--expect-change", action="append", metavar="ITEM:KEY", default=[],
                   help="an item-level change this publish intends (repeatable; use Item:* for any key)")
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
        return args.func(args)
    except (PublishError, CatalogError, TargetError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
