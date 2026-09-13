"""Removal of served metadata: declared, verified, and all-or-nothing."""
import json
import os

import pytest

from munki_fleet.drift import DriftReport
from munki_fleet.reconcile import ReconcileError, apply_removals, plan_removals, recorded_hashes
from munki_fleet.targets import LocalDirTarget, sha256_bytes


def report(**kwargs):
    return DriftReport(**kwargs)


def test_plan_refuses_undeclared_drift():
    with pytest.raises(ReconcileError) as excinfo:
        plan_removals(report(only_on_target=["a", "b"]), declared=["a"])
    assert "undeclared" in str(excinfo.value) and "b" in str(excinfo.value)


def test_plan_refuses_a_declaration_that_is_not_drift():
    """A stale declaration is how a correct-looking command deletes the wrong thing."""
    with pytest.raises(ReconcileError) as excinfo:
        plan_removals(report(only_on_target=["a"]), declared=["a", "gone-already"])
    assert "not a drift finding" in str(excinfo.value)


def test_plan_refuses_when_anything_else_is_wrong_with_the_target():
    with pytest.raises(ReconcileError) as excinfo:
        plan_removals(report(only_on_target=["a"], differing=["pkgs/x"]), declared=["a"])
    assert "publish first" in str(excinfo.value)


def test_plan_returns_everything_when_it_lines_up():
    assert plan_removals(report(only_on_target=["b", "a"]), declared=["a", "b"]) == ["a", "b"]


def test_removal_verifies_the_bytes_against_the_record_before_deleting(tmp_path):
    target = LocalDirTarget(str(tmp_path / "served"))
    target.write_atomic("pkgsinfo/gone.pkginfo", b"the file we withdrew")
    good = sha256_bytes(b"the file we withdrew")

    # the target holds something else at the same path: refuse, and remove nothing
    target.write_atomic("pkgsinfo/gone.pkginfo", b"something else entirely")
    with pytest.raises(ReconcileError) as excinfo:
        apply_removals(target, ["pkgsinfo/gone.pkginfo"], {"pkgsinfo/gone.pkginfo": good})
    assert "not the file this project retired" in str(excinfo.value)
    assert target.stat("pkgsinfo/gone.pkginfo") is not None, "a refused removal must not delete"

    # put the right bytes back: it removes, and verifies absence
    target.write_atomic("pkgsinfo/gone.pkginfo", b"the file we withdrew")
    result = apply_removals(target, ["pkgsinfo/gone.pkginfo"], {"pkgsinfo/gone.pkginfo": good})
    assert target.stat("pkgsinfo/gone.pkginfo") is None
    assert result == [("pkgsinfo/gone.pkginfo", f"removed, matched the record ({good[:16]})")]


def test_removal_reports_a_path_that_is_already_gone(tmp_path):
    target = LocalDirTarget(str(tmp_path / "served"))
    result = apply_removals(target, ["pkgsinfo/never-there"], {})
    assert result == [("pkgsinfo/never-there", "already absent")]


def test_removal_without_a_record_says_so(tmp_path):
    target = LocalDirTarget(str(tmp_path / "served"))
    target.write_atomic("manifests/202-Mac-Pro-3", b"manifest")
    result = apply_removals(target, ["manifests/202-Mac-Pro-3"], {})
    assert "no record to verify against" in result[0][1]
    assert target.stat("manifests/202-Mac-Pro-3") is None


def test_a_declared_hash_is_enforced_like_a_recorded_one(tmp_path):
    """The renamed-file case: the bytes are known from the checkout's new path."""
    target = LocalDirTarget(str(tmp_path / "served"))
    target.write_atomic("pkgsinfo/apps/VLC/VLC.plist", b"the pre-rename copy")
    wrong = sha256_bytes(b"not it")
    with pytest.raises(ReconcileError):
        apply_removals(target, ["pkgsinfo/apps/VLC/VLC.plist"],
                       {"pkgsinfo/apps/VLC/VLC.plist": wrong})
    assert target.stat("pkgsinfo/apps/VLC/VLC.plist") is not None
    right = sha256_bytes(b"the pre-rename copy")
    assert apply_removals(target, ["pkgsinfo/apps/VLC/VLC.plist"],
                          {"pkgsinfo/apps/VLC/VLC.plist": right})


def test_recorded_hashes_reads_the_withdrawal_log(tmp_path):
    root = tmp_path / "repo"
    os.makedirs(root / "data")
    (root / "data" / "withdrawals.jsonl").write_text(json.dumps({
        "item": "Firefox", "kind": "pkginfo", "source_path": "pkgsinfo/apps/firefox/Firefox.plist",
        "source_sha256": "abc123"}) + "\n")
    assert recorded_hashes(str(root)) == {"pkgsinfo/apps/firefox/Firefox.plist": "abc123"}
