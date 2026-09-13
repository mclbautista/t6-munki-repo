"""Payload cleanup: orphans are decidable, and a live payload is never removable."""
import json
import os

import pytest

from munki_fleet.payloads import (PAYLOAD_REMOVALS_PATH, PayloadError, list_payloads,
                                  orphan_payloads, referenced_locations, remove_payloads)
from munki_fleet.targets import LocalDirTarget


def tree(tmp_path, locations=("keep.dmg",)):
    """A checkout with pkginfos referencing `locations`, and a target holding those plus orphans."""
    import plistlib
    root = tmp_path / "repo"
    (root / "pkgsinfo").mkdir(parents=True)
    for idx, location in enumerate(locations):
        with open(root / "pkgsinfo" / f"Item{idx}.pkginfo", "wb") as fh:
            plistlib.dump({"name": f"Item{idx}", "version": "1.0",
                           "installer_item_location": location}, fh)
    target = LocalDirTarget(str(tmp_path / "served"))
    for path in tuple(locations) + ("orphan-1.pkg", "apps/orphan-2.dmg", "apps/nested/orphan-3.pkg"):
        target.write_atomic(f"pkgs/{path}", f"bytes of {path}".encode())
    return str(root), target


def test_orphans_are_the_payloads_no_pkginfo_references(tmp_path):
    root, target = tree(tmp_path)
    assert orphan_payloads(root, target) == [
        "pkgs/apps/nested/orphan-3.pkg", "pkgs/apps/orphan-2.dmg", "pkgs/orphan-1.pkg"]


def test_a_referenced_payload_is_never_an_orphan(tmp_path):
    root, target = tree(tmp_path, locations=("keep.dmg", "apps/nested/orphan-3.pkg"))
    assert "pkgs/keep.dmg" not in orphan_payloads(root, target)
    assert "pkgs/apps/nested/orphan-3.pkg" not in orphan_payloads(root, target)
    assert referenced_locations(root)["apps/nested/orphan-3.pkg"] == "Item1"


def test_listing_ignores_files_outside_the_payload_directories(tmp_path):
    root, target = tree(tmp_path)
    target.write_atomic("manifests/site_default", b"not a payload")
    assert all(p.startswith("pkgs/") for p in list_payloads(target))


def test_removal_refuses_a_declared_path_that_is_still_referenced(tmp_path):
    root, target = tree(tmp_path)
    orphans = orphan_payloads(root, target)
    with pytest.raises(PayloadError) as excinfo:
        remove_payloads(root, target, orphans, declared=["pkgs/keep.dmg"],
                        approved_by="Cyril", reason="cleanup")
    assert "still referenced" in str(excinfo.value)
    assert target.stat("pkgs/keep.dmg") is not None, "nothing may be removed on a refusal"


def test_removal_refuses_without_an_approver_or_a_reason(tmp_path):
    root, target = tree(tmp_path)
    orphans = orphan_payloads(root, target)
    with pytest.raises(PayloadError):
        remove_payloads(root, target, orphans, declared=orphans[:1], approved_by="", reason="x")
    with pytest.raises(PayloadError):
        remove_payloads(root, target, orphans, declared=orphans[:1],
                        approved_by="Cyril", reason="   ")


def test_removal_deletes_records_and_leaves_the_undeclared_orphans(tmp_path):
    root, target = tree(tmp_path)
    orphans = orphan_payloads(root, target)
    results = remove_payloads(root, target, orphans, declared=["pkgs/orphan-1.pkg"],
                              approved_by="Cyril", reason="nothing references it")
    assert target.stat("pkgs/orphan-1.pkg") is None
    assert target.stat("pkgs/apps/orphan-2.dmg") is not None, "an undeclared orphan stays"
    assert f"removed {len(b'bytes of orphan-1.pkg')} bytes" in results[0][1]
    stored = json.loads(open(os.path.join(root, PAYLOAD_REMOVALS_PATH)).read().splitlines()[0])
    for field in ("path", "bytes", "sha256", "at", "approved_by", "reason"):
        assert field in stored, f"the record must carry {field}"
    assert stored["bytes"] == len(b"bytes of orphan-1.pkg") and len(stored["sha256"]) == 64


def test_a_dry_run_removes_nothing_and_writes_no_record(tmp_path):
    root, target = tree(tmp_path)
    orphans = orphan_payloads(root, target)
    results = remove_payloads(root, target, orphans, declared=orphans, approved_by="Cyril",
                              reason="cleanup", dry_run=True)
    assert len(results) == len(orphans)
    assert all("would remove" in outcome for _, outcome in results)
    assert target.stat("pkgs/orphan-1.pkg") is not None
    assert not os.path.exists(os.path.join(root, PAYLOAD_REMOVALS_PATH))
