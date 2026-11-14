"""Drift between the checkout and the target, and integrity of what a target serves.

Fixtures only: nothing here touches the NAS or a Mac. The target is a local directory or the fake
SSH shell, and the metadata tree is built in a temp directory.
"""
import os
import plistlib

import pytest

from conftest import FakeSsh, catalog_array, item, write_file
from munki_fleet.drift import drift, integrity, item_locations, repo_url
from munki_fleet.targets import LocalDirTarget, SshTarget, TargetError

DEFAULT_MANIFESTS = {
    "site_default": {"catalogs": ["testing"]},
    "all": {"catalogs": ["testing"], "included_manifests": ["site_default"],
            "managed_installs": ["A"]},
    "202-TOC-M4-Max": {"catalogs": ["testing"], "included_manifests": ["all"]},
}


def metadata_tree(root, catalogs=("testing",), manifests=None, items=None, payloads=None):
    """A minimal but complete metadata checkout."""
    root = str(root)
    items = items if items is not None else [item("A"), item("B")]
    for idx, entry in enumerate(items):
        pkginfo = dict(entry)
        pkginfo.setdefault("installer_item_location", f"payload-{idx}.dmg")
        write_file(root, f"pkgsinfo/{entry['name']}-{idx}.pkginfo", plistlib.dumps(pkginfo))
    for name in catalogs:
        write_file(root, f"catalogs/{name}", catalog_array(items))
    for name, body in (manifests if manifests is not None else DEFAULT_MANIFESTS).items():
        write_file(root, f"manifests/{name}", plistlib.dumps(body))
    return root


def seed_target(source_root, target_root, with_payloads=True, extra=None, drop=()):
    """Copy the checkout to the target, and give it the payloads the pkginfos name."""
    for dirpath, _, files in os.walk(source_root):
        for f in files:
            full = os.path.join(dirpath, f)
            rel = os.path.relpath(full, source_root)
            if rel in drop:
                continue
            with open(full, "rb") as fh:
                write_file(target_root, rel, fh.read())
    if with_payloads:
        for name, locations in item_locations(source_root).items():
            for location in locations:
                write_file(target_root, f"pkgs/{location}", b"payload")
    for rel, content in (extra or {}).items():
        write_file(target_root, rel, content)
    return LocalDirTarget(str(target_root))


# --- drift -------------------------------------------------------------------------------------

def test_a_clean_tree_reports_no_drift(tmp_path):
    source = metadata_tree(tmp_path / "src")
    report = drift(source, seed_target(source, tmp_path / "tgt"))
    assert report.ok is True, report.describe()


def test_a_file_only_on_the_target_is_reported(tmp_path):
    """The case the gate cannot see: something published that the checkout does not describe."""
    source = metadata_tree(tmp_path / "src")
    target = seed_target(source, tmp_path / "tgt",
                         extra={"pkgsinfo/apps/firefox/Firefox-155.0.1.plist": b"<plist/>"})
    report = drift(source, target)
    assert report.ok is False
    assert report.only_on_target == ["pkgsinfo/apps/firefox/Firefox-155.0.1.plist"]


def test_a_file_only_in_the_checkout_is_reported(tmp_path):
    source = metadata_tree(tmp_path / "src")
    report = drift(source, seed_target(source, tmp_path / "tgt", drop=["manifests/all"]))
    assert report.missing_on_target == ["manifests/all"]


def test_a_differing_file_is_reported(tmp_path):
    source = metadata_tree(tmp_path / "src")
    target = seed_target(source, tmp_path / "tgt")
    write_file(str(tmp_path / "tgt"), "manifests/all", b"tampered")
    assert drift(source, target).differing == ["manifests/all"]


def test_an_unreadable_file_is_not_reported_as_absent(tmp_path):
    """A failed read must not look like an empty target."""
    source = metadata_tree(tmp_path / "src")
    seed_target(source, tmp_path / "tgt")

    class Unreadable(LocalDirTarget):
        def stat(self, relpath):
            if relpath == "manifests/all":
                raise TargetError("simulated read failure")
            return super().stat(relpath)

    report = drift(source, Unreadable(str(tmp_path / "tgt")))
    assert report.unreadable == ["manifests/all"]
    assert "manifests/all" not in report.only_on_target
    assert report.ok is False


def test_drift_reads_the_target_through_the_ssh_seam(tmp_path):
    source = metadata_tree(tmp_path / "src")
    shell = FakeSsh()
    shell.files["/repo/manifests/extra"] = b"x"
    report = drift(source, SshTarget("t6-nas", "/repo", runner=shell))
    assert "manifests/extra" in report.only_on_target
    assert set(report.missing_on_target) >= {"manifests/all", "catalogs/testing"}


# --- integrity ---------------------------------------------------------------------------------

def test_a_clean_repository_reports_no_findings(tmp_path):
    source = metadata_tree(tmp_path / "src")
    report = integrity(source, seed_target(source, tmp_path / "tgt"))
    assert report.ok is True, report.describe()
    assert report.membership_source == "the served catalogs"


def test_every_referenced_item_is_checked_for_a_payload(tmp_path):
    source = metadata_tree(tmp_path / "src")
    report = integrity(source, seed_target(source, tmp_path / "tgt", with_payloads=False))
    findings = [f for f in report.findings if f.kind == "payload_missing"]
    assert {f.subject for f in findings} == {"A"}, report.describe()
    assert all(f.manifests for f in findings), "each finding names the manifest that wants it"


def test_an_item_with_no_pkginfo_at_all_is_reported(tmp_path):
    """The other half of 'an existing payload and an existing pkginfo' — the half that was missing.

    An item referenced by a manifest and served by a catalog, but with no pkginfo in the checkout,
    must be a finding. It was silently skipped before, and a fixture like this one returned clean.
    """
    source = metadata_tree(tmp_path / "src",
                           manifests={"site_default": {"catalogs": ["testing"]},
                                      "all": {"included_manifests": ["site_default"],
                                              "managed_installs": ["GHOST"]}},
                           items=[item("GHOST")])
    os.remove(os.path.join(source, "pkgsinfo", "GHOST-0.pkginfo"))
    target = seed_target(source, tmp_path / "tgt", with_payloads=False)
    report = integrity(source, target)
    fresh = [f for f in report.findings if f.kind == "pkginfo_missing"]
    assert [f.subject for f in fresh] == ["GHOST"]
    assert fresh[0].manifests == ["all"]


def test_duplicate_names_have_every_payload_checked(tmp_path):
    """Two pkginfos share one name in the live repository; checking one location proves nothing."""
    source = metadata_tree(tmp_path / "src",
                           items=[item("Firefox", installer_item_location="f.dmg"),
                                  item("Firefox", installer_item_location="f.pkg")],
                           manifests={"site_default": {"catalogs": ["testing"]},
                                      "all": {"included_manifests": ["site_default"],
                                              "managed_installs": ["Firefox"]}})
    target = seed_target(source, tmp_path / "tgt")
    target.remove("pkgs/f.pkg")
    report = integrity(source, target)
    missing = [f for f in report.findings if f.kind == "payload_missing"]
    assert [f.detail for f in missing] == ["payload not present on the target: pkgs/f.pkg"]


def test_default_installs_and_conditional_items_are_followed(tmp_path):
    """A manifest can reference an item from more places than managed/optional installs."""
    source = metadata_tree(tmp_path / "src",
                           manifests={"site_default": {"catalogs": ["testing"]},
                                      "all": {"included_manifests": ["site_default"],
                                              "default_installs": ["A"],
                                              "conditional_items": [
                                                  {"condition": "os_vers >= 26",
                                                   "managed_installs": ["B"]}]}})
    report = integrity(source, seed_target(source, tmp_path / "tgt", with_payloads=False))
    assert {f.subject for f in report.findings if f.kind == "payload_missing"} == {"A", "B"}


def test_a_manifest_referencing_an_item_no_catalog_serves_is_reported(tmp_path):
    source = metadata_tree(tmp_path / "src",
                           manifests={"site_default": {"catalogs": ["testing"]},
                                      "all": {"included_manifests": ["site_default"],
                                              "managed_installs": ["A"]},
                                      "202-TOC-M4-Max": {"catalogs": ["testing"],
                                                         "included_manifests": ["all"],
                                                         "optional_installs": ["GHOST"]}})
    report = integrity(source, seed_target(source, tmp_path / "tgt"))
    findings = [f for f in report.findings if f.kind == "item_not_in_catalog"]
    assert [f.subject for f in findings] == ["GHOST"]
    assert findings[0].manifests == ["202-TOC-M4-Max"]


def test_catalog_membership_is_checked_against_declared_membership(tmp_path):
    source = metadata_tree(tmp_path / "src",
                           items=[item("A"), item("B", catalogs=["production"])])
    report = integrity(source, seed_target(source, tmp_path / "tgt"))
    assert "B" in {f.subject for f in report.findings if f.kind == "catalog_membership_mismatch"}


def test_a_catalog_entry_with_no_pkginfo_is_reported(tmp_path):
    """A stale entry in a served catalog is a defect, not something to skip past."""
    source = metadata_tree(tmp_path / "src")
    target = seed_target(source, tmp_path / "tgt",
                         extra={"catalogs/testing": catalog_array([item("A"), item("STALE")])})
    report = integrity(source, target)
    stale = [f for f in report.findings if f.kind == "catalog_entry_without_pkginfo"]
    assert [f.subject for f in stale] == ["STALE"]


def test_an_unreadable_catalog_is_reported_not_skipped(tmp_path):
    source = metadata_tree(tmp_path / "src")
    target = seed_target(source, tmp_path / "tgt", extra={"catalogs/testing": b"not a plist"})
    report = integrity(source, target)
    assert "catalog_unreadable" in report.kinds(), report.describe()


def test_duplicate_name_entries_are_reported_as_a_defect(tmp_path):
    source = metadata_tree(tmp_path / "src",
                           items=[item("Firefox"), item("Firefox", installer_item_location="F.pkg")])
    report = integrity(source, seed_target(source, tmp_path / "tgt"))
    assert "Firefox" in {f.subject for f in report.findings if f.kind == "duplicate_name"}


def test_membership_falls_back_to_the_build_and_says_so(tmp_path):
    """With nothing served yet, the report must say which catalogs it judged."""
    source = metadata_tree(tmp_path / "src")
    report = integrity(source, LocalDirTarget(str(tmp_path / "empty")))
    assert report.membership_source.startswith("the checkout's built catalogs")


def test_an_unresolvable_included_manifest_is_reported(tmp_path):
    source = metadata_tree(tmp_path / "src",
                           manifests={"site_default": {"catalogs": ["testing"]},
                                      "all": {"included_manifests": ["missing-group"]},
                                      "202-TOC-M4-Max": {"included_manifests": ["all"]}})
    report = integrity(source, seed_target(source, tmp_path / "tgt"))
    assert "manifest_unresolved" in report.kinds(), report.describe()


def test_checking_for_a_payload_does_not_hash_it(tmp_path):
    """A payload can be gigabytes; existence is the question, and hashing it is not the answer."""
    source = metadata_tree(tmp_path / "src")
    shell = FakeSsh()
    for name, locations in item_locations(source).items():
        for location in locations:
            shell.files[f"/repo/pkgs/{location}"] = b"payload"
    target = SshTarget("t6-nas", "/repo", runner=shell)
    target.list_files(("pkgs",))
    shell.commands.clear()
    integrity(source, target)
    hashed = [c for c, _ in shell.commands if "sha256sum" in c and "pkgs/" in c]
    assert hashed == [], f"payload checks must not hash: {hashed[:2]}"


def test_repo_url_percent_encodes_paths_with_spaces():
    """A published manifest is named `303B iMac`; a raw space is not a legal URL."""
    assert repo_url("http://192.168.88.188/MunkiRepo", "manifests/303B iMac") == \
        "http://192.168.88.188/MunkiRepo/manifests/303B%20iMac"


def test_vendor_suite_items_are_checked_like_any_other_item(tmp_path):
    """The Oct 30 amendment brought Adobe, Avid, Resolve and NTFS into scope (no deferred list)."""
    suites = [item("davinci-resolve-studio"), item("Adobe Creative Cloud"),
              item("Avid Media Composer"), item("NTFS for Mac")]
    source = metadata_tree(tmp_path / "src", items=suites,
                           manifests={"m": {"catalogs": ["testing"],
                                      "optional_installs": [s["name"] for s in suites]}})
    clean = integrity(source, seed_target(source, tmp_path / "ok"))
    assert clean.ok is True, clean.describe()
    broken = integrity(source, seed_target(source, tmp_path / "bad", with_payloads=False))
    assert {f.subject for f in broken.findings if f.kind == "payload_missing"} == {
        s["name"] for s in suites}, broken.describe()
