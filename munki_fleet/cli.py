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
import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime
from typing import Callable, Dict, List, Optional, Set, Tuple

from .catalogs import CatalogError, build_catalogs
from .drift import DriftReport, integrity, repo_url
from .drift import drift as drift_report
from .gate import evaluate_gate
from .promote import (PROMOTIONS_PATH, PromotionError, declared_exclusions, demote,
                      initial_promotion_plan, load_history, load_pilots, promote)
from . import probe, toolchain
from .payloads import PayloadError, orphan_payloads, remove_payloads
from .reconcile import ReconcileError, apply_removals, plan_removals, recorded_hashes
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


def cmd_check(args, deps) -> int:
    """Drift and integrity in one pass: is the target what the checkout says, and would an
    install from it work? Read-only, no credentials, non-zero exit on any finding."""
    target = deps.target_factory(args.target)
    drift = drift_report(args.metadata_root, target)
    print(f"drift: {drift.describe()}")
    for label, entries in (("only on the target", drift.only_on_target),
                           ("missing on the target", drift.missing_on_target),
                           ("differing", drift.differing),
                           ("unreadable", drift.unreadable)):
        for entry in entries[: args.max_list]:
            print(f"  {label}: {entry}")
        if len(entries) > args.max_list:
            print(f"  {label}: … and {len(entries) - args.max_list} more")

    report = integrity(args.metadata_root, target)
    print(f"integrity: {report.describe()}")
    by_kind = {}
    for finding in report.findings:
        by_kind.setdefault(finding.kind, []).append(finding)
    for kind, findings in sorted(by_kind.items()):
        print(f"  {kind} ({len(findings)}):")
        for finding in findings[: args.max_list]:
            where = f" [wanted by {', '.join(finding.manifests)}]" if finding.manifests else ""
            print(f"    {finding.subject}: {finding.detail}{where}")
        if len(findings) > args.max_list:
            print(f"    … and {len(findings) - args.max_list} more")
    return 0 if (drift.ok and report.ok) else 1


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
                remote = http_sha256(repo_url(args.http_base, relpath))
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


def _declared_hashes(pairs) -> Dict[str, str]:
    """`PATH=SHA256` declarations, for files whose expected bytes are known some other way."""
    out: Dict[str, str] = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise ReconcileError(f"--expect-remove-hash wants PATH=SHA256, got {pair!r}")
        path, digest = pair.rsplit("=", 1)
        out[path.strip()] = digest.strip()
    return out


def _inventory_targets(path: str, limit: Optional[int] = None) -> List[dict]:
    """The machines to probe, taken from the identity inventory rather than typed by hand."""
    with open(path, encoding="utf-8") as fh:
        inventory = json.load(fh)
    targets = []
    for row in inventory.get("machines", []):
        host = row.get("munki_name") or row.get("unix_hostname")
        if not host:
            continue
        # The transport needs something that resolves: bare short hostnames are mDNS names on this
        # network and `ssh 202-TOC-M4-Max` fails DNS outright. The inventory carries the address the
        # machine was last seen at, so the record keeps the name and the probe travels by address.
        targets.append({"host": host, "address": row.get("primary_ip"), "serial": row.get("serial"),
                        "name": row.get("computer_name")})
    for entry in inventory.get("known_absent") or []:
        if not isinstance(entry, dict):
            continue
        host = entry.get("probe_hostname") or entry.get("name")
        if not host:
            continue
        # A machine the export has no row for is still a machine to probe: it is how the pilot
        # ring's second member gets observed at all.
        targets.append({"host": host, "address": entry.get("primary_ip"),
                        "serial": entry.get("serial"), "name": entry.get("name")})
    targets.sort(key=lambda t: t["host"])
    return targets[:limit] if limit else targets


def _split_machine(spec: str) -> dict:
    """`HOST[:SERIAL[:NAME]]`, or `ADDRESS@HOST[:SERIAL[:NAME]]` to separate the two."""
    parts = spec.split(":")
    address, _, host = parts[0].partition("@")
    return {"host": host or address, "address": address, "serial": parts[1] if len(parts) > 1 else None,
            "name": parts[2] if len(parts) > 2 else (host or address)}


def local_runner(host: str, command: str, timeout: Optional[int] = None):
    """Run the probe on the machine the collector is running on."""
    completed = subprocess.run(["sh", "-c", command], capture_output=True, timeout=timeout)
    return completed.returncode, completed.stdout, completed.stderr


def _read_build_versions(host: str, timeout: Optional[int]) -> List:
    """Tool versions on a build host, read by running the tools there. Never guessed."""
    if host in ("local", "localhost", ""):
        return toolchain.read_versions(lambda h, c, t: local_runner(h, c, t), "local")
    return toolchain.read_versions(probe.default_runner, host)


def cmd_toolchain(args, deps: Deps) -> int:
    """The version relationship between the tools that build catalogs and the clients that read them."""
    builders = []
    for host in (args.build_host or ["local"]):
        builders += _read_build_versions(host, args.timeout)
    clients = toolchain.client_versions(args.store)
    relationship = toolchain.relationship(builders, clients)

    print("build hosts:")
    for version in builders:
        print(f"  {version.host:16} {version.tool:24} {version.version}")
    print(f"clients observed: {len(clients)}")
    for client in clients:
        print(f"  {client['serial']:14} {client.get('host') or '?':18} "
              f"{client['munki_version']:14} observed {client['observed_at']}")
    if not clients:
        print("  (no client version is available until a probe run reaches one: see ticket 05)")
    print()
    if relationship.findings:
        for finding in relationship.findings:
            print(f"  FINDING: {finding}")
    else:
        print("  aligned: the catalog builder and every observed client are on the same major version")

    if args.record:
        payload = {"recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                   "relationship": relationship.to_json(),
                   "versions": [v.to_json() for v in builders]}
        with open(args.record, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
        print(f"\nrecorded in {args.record}")
    return 0 if relationship.aligned else 1


def cmd_catalog_compare(args, deps: Deps) -> int:
    """Byte-compare a fresh build against a pre-image, and explain every difference by item."""
    if bool(args.before) == bool(args.before_target):
        print("error: pass exactly one of --before DIR or --before-target SPEC", file=sys.stderr)
        return 2

    if args.before:
        base = args.before
        if not os.path.isdir(base):
            print(f"error: {base} is not a directory of catalogs", file=sys.stderr)
            return 2
        names = sorted(os.listdir(base))

        def before_callable(name):
            path = os.path.join(base, name)
            if not os.path.isfile(path):
                return None
            with open(path, "rb") as fh:
                return fh.read()
    else:
        target = deps.target_factory(args.before_target)
        names = sorted({os.path.basename(p) for p in target.list_files(["."])})

        def before_callable(name):
            if name not in names:
                return None
            return target.read(name)

    build = build_catalogs(args.metadata_root, runner=deps.catalog_runner)
    results = toolchain.compare_build_to(before_callable, build, sorted(set(names) | set(build.catalogs)))

    differing = []
    for name, entry in sorted(results.items()):
        head = "identical" if entry["identical"] else "BYTES DIFFER"
        print(f"  catalogs/{name}: {head}")
        if entry["identical"]:
            continue
        differing.append(name)
        print(f"    before {entry['before_sha256'][:16] if entry['before_sha256'] else 'absent'}"
              f"   after {entry['after_sha256'][:16] if entry['after_sha256'] else 'absent'}")
        if entry["item_diff"]:
            print(f"    item-level: {entry['item_diff']}")
        print(f"    {entry['explanation']}")
    print(f"\n{len(results) - len(differing)}/{len(results)} catalog(s) identical")
    return 0 if not differing else 1


def cmd_probe(args, deps: Deps) -> int:
    """Probe machines and append the run to the observation store."""
    targets = [_split_machine(spec) for spec in args.machine]
    if args.from_inventory:
        targets += _inventory_targets(args.from_inventory, args.limit)
    if not targets:
        print("error: no targets; pass --machine HOST[:SERIAL] or --from-inventory", file=sys.stderr)
        return 2

    # A local target is matched on its name *or* its address, because the runner is handed the
    # address: matching only the name silently sent the local machine over ssh.
    local_addresses = set()
    for candidate in targets:
        if args.local_host in (candidate.get("host"), candidate.get("address")):
            local_addresses |= {candidate.get("host"), candidate.get("address")}

    def runner(address, command, timeout=None):
        if address and address in local_addresses:
            return local_runner(address, command, timeout or args.timeout)
        return probe.default_runner(address, command, timeout or args.timeout)

    run, observations = probe.probe_run(targets, runner, store_path=args.store,
                                        observer=args.observer or probe.DEFAULT_OBSERVER,
                                        timeout=args.timeout)
    print(f"run {run.run_id}")
    print(f"  targeted {run.targeted}, reached {run.reached} "
          f"(observed {run.observed}, partial {run.partial}), unobserved {run.unobserved}")
    print(f"  complete: {run.complete}" if run.complete else
          "  INCOMPLETE: some targets were not observed")
    for observation in observations:
        host = observation.target["host"]
        state = observation.state
        if observation.outcome == "observed":
            serial = (observation.machine or {}).get("serial", "?")
            print(f"    {host:28} {serial:14} manifest={state['manifest_name']} "
                  f"pending={state['pending_count']} "
                  f"rejections={len(state['architecture_rejections'])}")
        elif state is not None:
            print(f"    {host:28} {'PARTIAL':12} {observation.reason} "
                  f"(state read: manifest={state['manifest_name']}, "
                  f"pending={state['pending_count']})")
        else:
            print(f"    {host:28} {'UNOBSERVED':12} {observation.reason}: "
                  f"{observation.detail or ''}")
    print(f"  appended to {args.store}")
    return 0


def cmd_observations(args, deps: Deps) -> int:
    """The latest reading per machine, with its age (read-only)."""
    store = probe.ObservationStore(args.store)
    records = store.read()
    if not records:
        print(f"{args.store} holds no observations")
        return 0
    now = args.now or datetime.now().astimezone().isoformat(timespec="seconds")
    readings = probe.latest_per_machine(records, now=now, max_age=args.max_age)
    runs = store.runs()
    print(f"{len(records)} records, {len(runs)} run(s); latest observed {runs[-1]['observed_at']}"
          if runs else f"{len(records)} records")
    print(f"max age {args.max_age}s; now {now}")
    for key, entry in sorted(readings.items()):
        observation = entry["observation"]
        age = entry["age_seconds"]
        verdict = "STALE" if entry["stale"] else "current"
        if observation["outcome"] == "observed":
            state = observation["state"]
            print(f"  {key:14} {verdict:8} age={age:>7}s  {observation['target']['host']:26} "
                  f"manifest={state['manifest_name']} pending={state['pending_count']}")
        else:
            print(f"  {key:14} {verdict:8} age={age:>7}s  {observation['target']['host']:26} "
                  f"{observation['outcome']}: {observation.get('reason')}")
    return 0


def cmd_payload_orphans(args, deps: Deps) -> int:
    """Payloads on the target that no pkginfo in the checkout references (read-only)."""
    target = deps.target_factory(args.target)
    orphans = orphan_payloads(args.metadata_root, target)
    total = 0
    print(f"{len(orphans)} payload(s) referenced by no pkginfo:")
    for path in orphans:
        stat = target.stat(path)
        size = stat.size if stat else 0
        total += size
        print(f"  {path}  {size/1e6:.1f} MB  {stat.sha256[:16] if stat else ''}")
    print(f"total {total/1e6:.1f} MB")
    return 0


def cmd_payload_remove(args, deps: Deps) -> int:
    target = deps.target_factory(args.target)
    orphans = orphan_payloads(args.metadata_root, target)
    results = remove_payloads(args.metadata_root, target, orphans,
                              declared=args.expect_remove_payload, approved_by=args.approved_by,
                              reason=args.reason, dry_run=args.dry_run)
    print(f"{len(results)} of {len(orphans)} orphan(s) addressed:")
    for path, outcome in results:
        print(f"  {path}: {outcome}")
    remaining = orphan_payloads(args.metadata_root, target)
    print(f"orphans remaining: {len(remaining)}")
    return 0 if not remaining or results else 1


def cmd_reconcile(args, deps: Deps) -> int:
    """Remove metadata the checkout has retired, with every removal declared and verified."""
    target = deps.target_factory(args.target)
    report = drift_report(args.metadata_root, target)
    paths = plan_removals(report, args.expect_remove_file)
    expected = recorded_hashes(args.metadata_root)
    expected.update(_declared_hashes(args.expect_remove_hash))

    if args.dry_run:
        print(f"target: {report.describe()}")
        print(f"would remove {len(paths)} file(s) present only on the target:")
        for path in paths:
            stat = target.stat(path)
            digest = expected.get(path)
            if digest:
                verdict = "matches the record" if stat and stat.sha256 == digest \
                    else "DOES NOT MATCH THE RECORD — removal would be refused"
            else:
                verdict = "no record to verify against"
            print(f"  - {path}  {stat.size if stat else 0} bytes  {stat.sha256[:16] if stat else ''}"
                  f"  ({verdict})")
        return 0
    print(f"removing {len(paths)} file(s) the checkout no longer has:")
    for path, outcome in apply_removals(target, paths, expected):
        print(f"  {path}: {outcome}")
    after = drift_report(args.metadata_root, target)
    print(f"after: {after.describe()}")
    return 0 if after.ok else 1


def cmd_promote(args, deps: Deps) -> int:
    record = promote(args.metadata_root, args.item, args.version, args.approved_by, args.evidence)
    print(f"promoted {record.item} {record.version}: "
          f"{' + '.join(record.from_catalogs)} -> {' + '.join(record.to_catalogs)}")
    print(f"  approved by {record.approved_by} at {record.at}")
    for item in record.evidence:
        print(f"  evidence: {item}")
    print(f"  recorded in {PROMOTIONS_PATH} (pkginfo {record.pkginfo_path}, {record.pkginfo_sha256[:16]})")
    print("  the checkout changed; nothing is live until it is published (ADR 0009)")
    return 0


def cmd_demote(args, deps: Deps) -> int:
    record = demote(args.metadata_root, args.item, args.version, args.approved_by, args.reason)
    print(f"demoted {record.item} {record.version}: "
          f"{' + '.join(record.from_catalogs)} -> {' + '.join(record.to_catalogs)}")
    print(f"  reason: {record.reason}")
    print(f"  recorded in {PROMOTIONS_PATH}; publish to take it off the fleet")
    return 0


def cmd_promotion_plan(args, deps: Deps) -> int:
    pilots = args.pilot or load_pilots(args.metadata_root)
    exclusions = sorted(set(declared_exclusions(args.metadata_root)) | set(args.exclude))
    plan = initial_promotion_plan(args.metadata_root, pilots, exclude=exclusions)
    print(plan.describe())
    print(f"\n{len(load_history(args.metadata_root))} promotion(s) already on record")
    return 0


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
    p = sub.add_parser("promote", help="move an item testing -> production, on the record")
    common(p)
    p.add_argument("--item", required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--approved-by", required=True, help="who approved this reaching the fleet")
    p.add_argument("--evidence", action="append", default=[], required=True,
                   help="pilot verification evidence (repeatable; at least one is required)")
    p.set_defaults(func=cmd_promote)
    p = sub.add_parser("demote", help="move an item production -> testing, with a reason")
    common(p)
    p.add_argument("--item", required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--approved-by", required=True)
    p.add_argument("--reason", required=True)
    p.set_defaults(func=cmd_demote)
    p = sub.add_parser("promotion-plan",
                       help="what the one-off initial promotion would do (read-only)")
    common(p)
    p.add_argument("--pilot", action="append", default=[],
                   help="override the declared pilot ring (repeatable)")
    p.add_argument("--exclude", action="append", default=[], metavar="ITEM",
                   help="an item to leave in testing rather than promote (repeatable)")
    p.set_defaults(func=cmd_promotion_plan)
    p = sub.add_parser("toolchain",
                       help="the version relationship between catalog builders and clients")
    p.add_argument("--store", default=None,
                   help="the observation store to read client versions from (ticket 05)")
    p.add_argument("--build-host", action="append", default=[],
                   help="a machine that builds catalogs (repeatable; 'local' for this machine)")
    p.add_argument("--record", default=None, metavar="PATH",
                   help="also write the relationship as JSON here")
    p.add_argument("--timeout", type=int, default=30)
    p.set_defaults(func=cmd_toolchain)
    p = sub.add_parser("catalog-compare",
                       help="byte-compare a fresh build against a pre-image, explained per item")
    p.add_argument("--before", default=None, metavar="DIR",
                   help="a local directory of catalogs to compare against")
    p.add_argument("--before-target", default=None, metavar="SPEC",
                   help="a target directory to read the pre-image catalogs from")
    common(p)
    p.set_defaults(func=cmd_catalog_compare)
    p = sub.add_parser("probe", help="probe machines and append to the observation store")
    p.add_argument("--store", required=True,
                   help="the observation store to append to (required: fleet state is never "
                        "written somewhere unintended)")
    p.add_argument("--machine", action="append", default=[],
                   metavar="ADDRESS@HOST[:SERIAL[:NAME]]",
                   help="a machine to probe (repeatable); put the resolvable address first, e.g. "
                        "192.168.88.182@202-TOC-M4-Max:RW3HL9FL4M")
    p.add_argument("--from-inventory", default=None, metavar="PATH",
                   help="probe the machines in an identity inventory, e.g. data/machines.json")
    p.add_argument("--observer", default=None,
                   help=f"who is observing (default: {probe.DEFAULT_OBSERVER})")
    p.add_argument("--local-host", default=None, metavar="HOST",
                   help="probe this target by running locally instead of over ssh")
    p.add_argument("--timeout", type=int, default=None)
    p.set_defaults(func=cmd_probe)
    p = sub.add_parser("observations", help="latest reading per machine, with age (read-only)")
    p.add_argument("--store", required=True)
    p.add_argument("--max-age", type=int, default=3600, help="seconds before a reading is stale")
    p.add_argument("--now", default=None, help="treat this as now (for tests and replays)")
    p.set_defaults(func=cmd_observations)
    p = sub.add_parser("payload-orphans",
                       help="payloads no pkginfo references any more (read-only)")
    common(p, with_target=True)
    p.set_defaults(func=cmd_payload_orphans)
    p = sub.add_parser("payload-remove", help="remove declared orphan payloads")
    common(p, with_target=True)
    p.add_argument("--expect-remove-payload", action="append", default=[], metavar="PATH",
                   help="a payload to remove (repeatable; each must actually be an orphan)")
    p.add_argument("--approved-by", required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_payload_remove)
    p = sub.add_parser("reconcile",
                       help="remove target-only metadata the checkout has retired (declared)")
    common(p, with_target=True)
    p.add_argument("--expect-remove-file", action="append", default=[], metavar="PATH",
                   help="a path to remove from the target (repeatable; each must be a drift finding)")
    p.add_argument("--expect-remove-hash", action="append", default=[], metavar="PATH=SHA256",
                   help="the bytes expected at a removal path, where the withdrawal log has none")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_reconcile)
    p = sub.add_parser("check", help="drift and integrity against a target (read-only)")
    common(p, with_target=True)
    p.add_argument("--max-list", type=int, default=25, help="entries to print per category")
    p.set_defaults(func=cmd_check)

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
    except (ReconcileError, PayloadError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    except PromotionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    except (PublishError, CatalogError, TargetError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
