"""The publish command line: the gate is wired in, and refusing means refusing.

These tests exist because the module-level gate tests can pass while the wiring is wrong — a
refusal that still publishes, or a missing declaration that slips through.
"""
import json
import os

import pytest

from conftest import access_map, catalog_array, catalog_runner, item, write_file
from munki_fleet.cli import Deps, main, parse_expectations
from munki_fleet.targets import LocalDirTarget


def make_tree(root, catalog_items, manifest=b"manifest"):
    """A minimal but *valid* metadata checkout: real pkginfos, a manifest, catalogs, an icon file."""
    import plistlib
    root = str(root)
    for entry in catalog_items:
        pkginfo = dict(entry)
        pkginfo.setdefault("installer_item_location", f"{entry['name']}.dmg")
        write_file(root, f"pkgsinfo/{entry['name']}.pkginfo", plistlib.dumps(pkginfo))
    write_file(root, "manifests/site_default", manifest)
    write_file(root, "catalogs/all", catalog_array(catalog_items))
    write_file(root, "catalogs/testing", catalog_array(catalog_items))
    write_file(root, "icons/_icon_hashes.plist", plistlib.dumps({}))
    return root


def seeded_target(source_root, target_root, catalog_items):
    """A target already holding the same tree plus the served catalogs."""
    for dirpath, _, files in os.walk(source_root):
        for f in files:
            full = os.path.join(dirpath, f)
            rel = os.path.relpath(full, source_root)
            with open(full, "rb") as fh:
                write_file(target_root, rel, fh.read())
    write_file(str(target_root), "catalogs/all", catalog_array(catalog_items))
    write_file(str(target_root), "catalogs/testing", catalog_array(catalog_items))
    return LocalDirTarget(str(target_root))


def test_parse_expectations_accepts_a_key_and_a_wildcard():
    assert parse_expectations(["A:display_name"]) == {("A", "display_name")}
    assert parse_expectations(["A:*"]) == {("A", None)}
    with pytest.raises(SystemExit):
        parse_expectations(["A"])


def test_an_undeclared_change_is_refused_and_nothing_is_published(tmp_path):
    source = make_tree(tmp_path / "src", [item("A", display_name="A")])
    target = seeded_target(source, tmp_path / "tgt", [item("A", display_name="A")])
    runner = catalog_runner({"all": [item("A", display_name="A (T6)")],
                             "testing": [item("A", display_name="A (T6)")]})
    deps = Deps(target_factory=lambda spec: target, catalog_runner=runner)

    code = main(["publish", "--metadata-root", source, "--target", "fake:/repo"], deps=deps)

    assert code == 3, "an undeclared change must refuse"
    assert target.read("catalogs/all") == catalog_array([item("A", display_name="A")]), \
        "a refusal must not publish"


def test_a_declared_change_publishes_and_verifies(tmp_path):
    source = make_tree(tmp_path / "src", [item("A", display_name="A")])
    target = seeded_target(source, tmp_path / "tgt", [item("A", display_name="A")])
    built = [item("A", display_name="A (T6)")]
    deps = Deps(target_factory=lambda spec: target,
                catalog_runner=catalog_runner({"all": built, "testing": built}))

    code = main(["publish", "--metadata-root", source, "--target", "fake:/repo",
                 "--expect-change", "A:display_name"], deps=deps)

    assert code == 0
    assert target.read("catalogs/all") == catalog_array(built)


def test_a_declared_file_change_is_required_for_a_manifest_edit(tmp_path):
    source = make_tree(tmp_path / "src", [item("A")], manifest=b"original manifest")
    target = seeded_target(source, tmp_path / "tgt", [item("A")])
    write_file(source, "manifests/site_default", b"changed manifest")
    deps = Deps(target_factory=lambda spec: target,
                catalog_runner=catalog_runner({"all": [item("A")], "testing": [item("A")]}))

    refused = main(["publish", "--metadata-root", source, "--target", "fake:/repo"], deps=deps)
    assert refused == 3

    allowed = main(["publish", "--metadata-root", source, "--target", "fake:/repo",
                    "--expect-file", "manifests/site_default"], deps=deps)
    assert allowed == 0
    assert target.read("manifests/site_default") == b"changed manifest"


def test_an_unreadable_target_is_refused(tmp_path):
    source = make_tree(tmp_path / "src", [item("A")])
    target = seeded_target(source, tmp_path / "tgt", [item("A")])

    def exploding_runner(command, stdin=None):
        raise AssertionError("the target should not be used")

    class Unreadable(LocalDirTarget):
        def stat(self, relpath):
            from munki_fleet.targets import TargetError
            if relpath.startswith("catalogs/"):
                raise TargetError("simulated read failure")
            return super().stat(relpath)

    deps = Deps(target_factory=lambda spec: Unreadable(target.root),
                catalog_runner=catalog_runner({"all": [item("A")], "testing": [item("A")]}))
    code = main(["publish", "--metadata-root", source, "--target", "fake:/repo"], deps=deps)
    assert code == 3


def test_check_reports_findings_and_exits_non_zero(tmp_path, capsys):
    """`check` is the drift+integrity entry point; a renamed field once crashed it unnoticed."""
    source = make_tree(tmp_path / "src", [item("A")])
    target = seeded_target(source, tmp_path / "tgt", [item("A")])
    write_file(target.root, "manifests/extra", b"published but not in the checkout")
    deps = Deps(target_factory=lambda spec: target,
                catalog_runner=catalog_runner({"all": [item("A")], "testing": [item("A")]}))

    code = main(["check", "--metadata-root", source, "--target", "fake:/repo"], deps=deps)

    out = capsys.readouterr().out
    assert code == 1, out
    assert "only on the target: manifests/extra" in out
    assert "drift:" in out and "integrity:" in out


def test_check_reports_clean_on_a_consistent_tree(tmp_path, capsys):
    source = make_tree(tmp_path / "src", [item("A")])
    target = seeded_target(source, tmp_path / "tgt", [item("A")])
    write_file(target.root, "pkgs/A.dmg", b"payload")
    deps = Deps(target_factory=lambda spec: target,
                catalog_runner=catalog_runner({"all": [item("A")], "testing": [item("A")]}))

    code = main(["check", "--metadata-root", source, "--target", "fake:/repo"], deps=deps)

    captured = capsys.readouterr()
    assert code == 0, captured.out + captured.err
    assert "no integrity findings" in captured.out


def test_dry_run_reports_without_publishing(tmp_path):
    source = make_tree(tmp_path / "src", [item("A", display_name="A")])
    target = seeded_target(source, tmp_path / "tgt", [item("A", display_name="A")])
    built = [item("A", display_name="A (T6)")]
    deps = Deps(target_factory=lambda spec: target,
                catalog_runner=catalog_runner({"all": built, "testing": built}))

    code = main(["publish", "--metadata-root", source, "--target", "fake:/repo",
                 "--expect-change", "A:display_name", "--dry-run"], deps=deps)

    assert code == 0
    assert target.read("catalogs/all") == catalog_array([item("A", display_name="A")])


# --- the probe command and the declared access path (ticket 01 of fleet-ssh-access) ---------------

PROBE_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "probe", "healthy-envelope.txt")


def test_the_probe_command_uses_the_declared_destination_from_the_map(tmp_path, capsys):
    store = str(tmp_path / "observations.jsonl")
    map_path = access_map(tmp_path, [{"name": "Sixto-5", "destination": "t6-mac-mini"}])
    with open(PROBE_FIXTURE, encoding="utf-8") as fh:
        envelope = fh.read().encode()
    calls = []

    def runner(address, command, timeout=None):
        calls.append(address)
        return 0, envelope, b""

    code = main(["probe", "--store", store, "--access-map", map_path,
                 "--machine", "192.168.88.151@Sixto-5"], deps=Deps(probe_runner=runner))

    assert code == 0, capsys.readouterr().out
    assert calls == ["t6-mac-mini"], "the map's destination is the transport"
    with open(store, encoding="utf-8") as fh:
        records = [json.loads(line) for line in fh if line.strip()]
    observation = next(r for r in records if r["kind"] == "observation")
    assert observation["target"]["ssh_destination"] == "t6-mac-mini"
    assert observation["observed_at"] and observation["machine"]["serial"]


def test_the_probe_command_drives_the_inventory_and_the_access_map(tmp_path, capsys):
    """The `--from-inventory` path, which no test had ever driven.

    `cmd_probe` read `args.limit` while the parser defined no such option, so the documented command
    raised `AttributeError: 'Namespace' object has no attribute 'limit'` before it probed anything —
    every module-seam test for the probe was green while the inventory path could not run at all.
    """
    store = str(tmp_path / "observations.jsonl")
    inventory = os.path.join(str(tmp_path), "machines.json")
    with open(inventory, "w", encoding="utf-8") as fh:
        json.dump({"machines": [{"munki_name": "202A-Mac-Mini-M4", "unix_hostname": "202A-Mac-Mini-M4",
                                 "primary_ip": "192.168.88.175", "serial": "X904F44LHX",
                                 "computer_name": "202A Mac Mini M4"}],
                   "known_absent": []}, fh)
    map_path = access_map(tmp_path, [{"name": "202A-Mac-Mini-M4", "destination": "202a-mini"}])
    with open(PROBE_FIXTURE, encoding="utf-8") as fh:
        envelope = fh.read().encode()
    calls = []

    def runner(address, command, timeout=None):
        calls.append(address)
        return 0, envelope, b""

    code = main(["probe", "--store", store, "--access-map", map_path,
                 "--from-inventory", inventory], deps=Deps(probe_runner=runner))

    assert code == 0, capsys.readouterr().out
    assert calls == ["202a-mini"], "the inventory machine travels to its declared destination"
    with open(store, encoding="utf-8") as fh:
        records = [json.loads(line) for line in fh if line.strip()]
    run = next(r for r in records if r["kind"] == "run")
    assert run["targeted"] == 1 and run["observed"] == 1


def test_the_probe_command_refuses_an_unusable_access_map(tmp_path, capsys):
    """A map you passed and that cannot be read is a caller error, not something to read around."""
    store = str(tmp_path / "observations.jsonl")
    path = os.path.join(str(tmp_path), "ssh-access.json")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("{not json")

    def runner(address, command, timeout=None):
        raise AssertionError("nothing may be contacted when the map is unusable")

    code = main(["probe", "--store", store, "--access-map", path,
                 "--machine", "192.168.88.151@Sixto-5"], deps=Deps(probe_runner=runner))

    assert code == 2
    assert "access-map" in capsys.readouterr().err
    assert not os.path.exists(store), "nothing may be written when the run was refused"


def test_an_absent_default_map_is_reported_and_the_readings_say_the_path_was_undeclared(
        tmp_path, capsys, monkeypatch):
    """A map that is not there yet is not a refusal: it is reported, and every reading says so."""
    monkeypatch.chdir(tmp_path)                     # no data/ssh-access.json here
    store = str(tmp_path / "observations.jsonl")
    with open(PROBE_FIXTURE, encoding="utf-8") as fh:
        envelope = fh.read().encode()

    def runner(address, command, timeout=None):
        return 0, envelope, b""

    code = main(["probe", "--store", store, "--machine", "192.168.88.151@Sixto-5"],
                deps=Deps(probe_runner=runner))

    out = capsys.readouterr().out
    assert code == 0, out
    assert "no-access-map" in out and "0 of 1 ssh target(s)" in out
    with open(store, encoding="utf-8") as fh:
        records = [json.loads(line) for line in fh if line.strip()]
    observation = next(r for r in records if r["kind"] == "observation")
    assert observation["problems"] == ["no-access-map"]


def test_the_operator_view_shows_why_a_reading_is_not_a_declared_path(tmp_path, capsys):
    """The one place an operator can see the difference between a reading and a verified one."""
    store = str(tmp_path / "observations.jsonl")
    map_path = access_map(tmp_path, [{"name": "Somewhere-Else", "destination": "t6-mac-mini"}])
    with open(PROBE_FIXTURE, encoding="utf-8") as fh:
        envelope = fh.read().encode()

    def runner(address, command, timeout=None):
        return 0, envelope, b""

    main(["probe", "--store", store, "--access-map", map_path, "--machine", "192.168.88.151@Sixto-5"],
         deps=Deps(probe_runner=runner))
    capsys.readouterr()

    code = main(["observations", "--store", store, "--now", "2026-09-14T21:30:00+08:00"])

    out = capsys.readouterr().out
    assert code == 0
    assert "problems=no-access-record" in out, out


def test_the_committed_access_map_is_readable_and_carries_no_credential():
    """The declaration in this repository is the one the collector loads: it must stay usable."""
    import json as jsonlib
    from munki_fleet.access import DESTINATION, AccessMap
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "data", "ssh-access.json")
    access = AccessMap.load(path)
    assert access.available is True, access.reason
    with open(path, encoding="utf-8") as fh:
        raw = jsonlib.load(fh)
    assert raw["machines"], "a map with no records declares no access at all"
    for record in raw["machines"]:
        assert DESTINATION.match(record["destination"]), record["destination"]
        assert ":" not in record["destination"], "a destination may not carry a port or a password"
    assert "PRIVATE KEY" not in jsonlib.dumps(raw)
