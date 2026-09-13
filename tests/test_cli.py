"""The publish command line: the gate is wired in, and refusing means refusing.

These tests exist because the module-level gate tests can pass while the wiring is wrong — a
refusal that still publishes, or a missing declaration that slips through.
"""
import os

import pytest

from conftest import catalog_array, catalog_runner, item, write_file
from munki_fleet.cli import Deps, main, parse_expectations
from munki_fleet.targets import LocalDirTarget


def make_tree(root, catalog_items, manifest=b"manifest"):
    """A minimal metadata checkout: one pkginfo, one manifest, one icon hash file."""
    root = str(root)
    write_file(root, "pkgsinfo/A-1.0.pkginfo", b"<plist/>")
    write_file(root, "manifests/site_default", manifest)
    write_file(root, "icons/_icon_hashes.plist", b"<plist/>")
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
