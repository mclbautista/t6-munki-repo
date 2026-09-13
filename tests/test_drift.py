"""Drift between the checkout and the target, and integrity of what the target would serve.

Fixtures only: nothing here touches the NAS or a Mac. The target is a local directory or the fake
SSH shell, and the metadata tree is built in a temp directory.
"""
import plistlib

import pytest

from conftest import FakeSsh, catalog_array, item, write_file
from munki_fleet.drift import drift, integrity, item_locations, repo_url
from munki_fleet.targets import LocalDirTarget, SshTarget


def metadata_tree(root, catalogs=("testing",), manifests=None, items=None, payloads=True):
    """A minimal but complete metadata checkout, plus the payloads a target would hold."""
    root = str(root)
    items = items if items is not None else [item("A"), item("B")]
    for idx, entry in enumerate(items):
        pkginfo = dict(entry)
        pkginfo.setdefault("installer_item_location", f"A{idx}.dmg")
        write_file(root, f"pkgsinfo/{entry['name']}-{idx}.pkginfo", plistlib.dumps(pkginfo))
    for name in catalogs:
        write_file(root, f"catalogs/{name}", catalog_array(items))
    manifests = manifests if manifests is not None else {
        "site_default": {"catalogs": ["testing"]},
        "all": {"catalogs": ["testing"], "included_manifests": ["site_default"],
                "managed_installs": ["A"]},
        "202-TOC-M4-Max": {"catalogs": ["testing"], "included_manifests": ["all"]},
    }
    for name, body in manifests.items():
        write_file(root, f"manifests/{name}", plistlib.dumps(body))
    return root


def seed_target(source_root, target_root, with_payloads=True, extra=None):
    """Copy the checkout to the target, and give it the payloads the pkginfos name."""
    import os
    for dirpath, _, files in os.walk(source_root):
        for f in files:
            full = os.path.join(dirpath, f)
            rel = os.path.relpath(full, source_root)
            with open(full, "rb") as fh:
                write_file(target_root, rel, fh.read())
    if with_payloads:
        for name, location in item_locations(source_root).items():
            if location:
                write_file(target_root, f"pkgs/{location}", b"payload")
    for rel, content in (extra or {}).items():
        write_file(target_root, rel, content)
    return LocalDirTarget(str(target_root))


def test_a_clean_tree_reports_no_drift(tmp_path):
    source = metadata_tree(tmp_path / "src")
    target = seed_target(source, tmp_path / "tgt")
    report = drift(source, target)
    assert report.ok is True, report.describe()
    assert report.missing_in_checkout == [] and report.missing_on_target == []


def test_a_file_only_on_the_target_is_reported(tmp_path):
    """The case the gate cannot see: something published that the checkout does not describe."""
    source = metadata_tree(tmp_path / "src")
    target = seed_target(source, tmp_path / "tgt",
                         extra={"pkgsinfo/apps/firefox/Firefox-155.0.1.plist": b"<plist/>"})
    report = drift(source, target)
    assert report.ok is False
    assert report.missing_in_checkout == ["pkgsinfo/apps/firefox/Firefox-155.0.1.plist"]


def test_a_file_only_in_the_checkout_is_reported(tmp_path):
    source = metadata_tree(tmp_path / "src")
    target = seed_target(source, tmp_path / "tgt")
    LocalDirTarget(str(tmp_path / "tgt")).remove("manifests/all")
    report = drift(source, target)
    assert report.missing_on_target == ["manifests/all"]


def test_a_differing_file_is_reported(tmp_path):
    source = metadata_tree(tmp_path / "src")
    target = seed_target(source, tmp_path / "tgt")
    write_file(str(tmp_path / "tgt"), "manifests/all", b"tampered")
    report = drift(source, target)
    assert report.differing == ["manifests/all"]


def test_drift_reads_the_target_through_the_ssh_seam(tmp_path):
    source = metadata_tree(tmp_path / "src")
    shell = FakeSsh()
    shell.files["/repo/manifests/extra"] = b"x"
    report = drift(source, SshTarget("t6-nas", "/repo", runner=shell))
    assert "manifests/extra" in report.missing_in_checkout
    assert set(report.missing_on_target) >= {"manifests/all", "catalogs/testing"}


def test_every_referenced_item_is_checked_for_a_payload(tmp_path):
    """A manifest referencing an item whose payload is not on the target must be reported."""
    source = metadata_tree(tmp_path / "src")
    target = seed_target(source, tmp_path / "tgt", with_payloads=False)
    report = integrity(source, target)
    payload_findings = [f for f in report.findings if f.kind == "payload_missing"]
    assert payload_findings, report.describe()
    # Only "A" is referenced by a manifest in this fixture; "B" is merely in the catalog.
    assert {f.subject for f in payload_findings} == {"A"}
    assert all(f.manifests for f in payload_findings), "each finding names the manifest that wants it"


def test_a_manifest_referencing_an_item_no_catalog_serves_is_reported(tmp_path):
    source = metadata_tree(
        tmp_path / "src",
        manifests={"site_default": {"catalogs": ["testing"]},
                   "all": {"catalogs": ["testing"], "included_manifests": ["site_default"],
                           "managed_installs": ["A"]},
                   "202-TOC-M4-Max": {"catalogs": ["testing"], "included_manifests": ["all"],
                                      "optional_installs": ["GHOST"]}},
    )
    target = seed_target(source, tmp_path / "tgt")
    report = integrity(source, target)
    findings = [f for f in report.findings if f.kind == "item_not_in_catalog"]
    assert [f.subject for f in findings] == ["GHOST"]
    assert findings[0].manifests == ["202-TOC-M4-Max"], "the referencing manifest must be named"


def test_catalog_membership_is_checked_against_declared_membership(tmp_path):
    """An item in a catalog that does not declare that catalog is a mismatch."""
    source = metadata_tree(tmp_path / "src",
                           items=[item("A"), item("B", catalogs=["production"])])
    target = seed_target(source, tmp_path / "tgt")
    report = integrity(source, target)
    assert "B" in {f.subject for f in report.findings if f.kind == "catalog_membership_mismatch"}


def test_duplicate_name_entries_are_reported_as_a_defect(tmp_path):
    source = metadata_tree(tmp_path / "src",
                           items=[item("Firefox"), item("Firefox", installer_item_location="F.pkg")])
    target = seed_target(source, tmp_path / "tgt", with_payloads=False)
    report = integrity(source, target)
    assert "Firefox" in {f.subject for f in report.findings if f.kind == "duplicate_name"}


def test_an_unresolvable_included_manifest_is_reported(tmp_path):
    source = metadata_tree(tmp_path / "src",
                           manifests={"site_default": {"catalogs": ["testing"]},
                                      "all": {"included_manifests": ["missing-group"]},
                                      "202-TOC-M4-Max": {"included_manifests": ["all"]}})
    target = seed_target(source, tmp_path / "tgt")
    report = integrity(source, target)
    kinds = {f.kind for f in report.findings}
    assert "manifest_unresolved" in kinds, report.describe()


def test_a_clean_repository_reports_no_findings(tmp_path):
    source = metadata_tree(tmp_path / "src")
    target = seed_target(source, tmp_path / "tgt")
    report = integrity(source, target)
    assert report.ok is True, report.describe()


def test_checking_for_a_payload_does_not_hash_it(tmp_path):
    """A payload can be gigabytes; existence is the question, and hashing it is not the answer."""
    source = metadata_tree(tmp_path / "src")
    shell = FakeSsh()
    for rel in ["/repo/pkgs/A.dmg", "/repo/pkgs/B.dmg"]:
        shell.files[rel] = b"payload"
    SshTarget("t6-nas", "/repo", runner=shell).list_files(("pkgs",))
    shell.commands.clear()
    integrity(source, SshTarget("t6-nas", "/repo", runner=shell))
    hashed = [c for c, _ in shell.commands if "sha256sum" in c and "pkgs/" in c]
    assert hashed == [], f"payload checks must not hash: {hashed[:2]}"


def test_repo_url_percent_encodes_paths_with_spaces():
    """A published manifest is named `303B iMac`; a raw space is not a legal URL."""
    url = repo_url("http://192.168.88.188/MunkiRepo", "manifests/303B iMac")
    assert url == "http://192.168.88.188/MunkiRepo/manifests/303B%20iMac"
