"""Suspending the forced core: reversible, recorded, and provably empty afterwards."""
import json
import os
import plistlib

import pytest

from munki_fleet.baseline import (SUSPENSION_RECORD, BaselineError, forced_installs,
                                  suspend_forced_installs)


def manifest(root, body):
    os.makedirs(os.path.join(root, "manifests"), exist_ok=True)
    with open(os.path.join(root, "manifests", "all"), "wb") as fh:
        plistlib.dump(body, fh, sort_keys=True)
    return root


def test_suspending_empties_the_forced_core_and_keeps_the_items_installable(tmp_path):
    root = manifest(str(tmp_path), {
        "catalogs": ["testing"], "display_name": "T6 All Macs",
        "included_manifests": ["site_default"],
        "managed_installs": ["TeamViewer", "AnyDesk"], "managed_updates": [],
    })
    record = suspend_forced_installs(root, approved_by="Cyril", reason="nothing forced for now",
                                     at="2026-09-13T20:00:00+08:00")

    body = plistlib.load(open(os.path.join(root, "manifests", "all"), "rb"))
    assert body["managed_installs"] == []
    assert body["optional_installs"] == ["TeamViewer", "AnyDesk"]
    assert body["catalogs"] == ["testing"], "nothing else may move"
    assert body["included_manifests"] == ["site_default"]
    assert body["display_name"] == "T6 All Macs"
    assert body["managed_updates"] == []

    assert record["items"] == ["TeamViewer", "AnyDesk"]
    assert record["item_count"] == 2
    stored = json.load(open(os.path.join(root, SUSPENSION_RECORD)))
    for field in ("at", "approved_by", "reason", "manifest", "items", "how_to_reverse"):
        assert field in stored, f"the record must carry {field}"


def test_existing_optional_items_are_not_lost_or_duplicated(tmp_path):
    root = manifest(str(tmp_path), {
        "managed_installs": ["TeamViewer"], "optional_installs": ["VLC", "TeamViewer"],
    })
    suspend_forced_installs(root, approved_by="Cyril", reason="x")
    body = plistlib.load(open(os.path.join(root, "manifests", "all"), "rb"))
    assert body["optional_installs"] == ["VLC", "TeamViewer"], "no duplicate entry"


def test_suspending_refuses_when_nothing_is_forced(tmp_path):
    root = manifest(str(tmp_path), {"managed_installs": [], "optional_installs": ["VLC"]})
    with pytest.raises(BaselineError) as excinfo:
        suspend_forced_installs(root, approved_by="Cyril", reason="x")
    assert "nothing to suspend" in str(excinfo.value)


def test_suspending_refuses_without_an_approver_or_a_reason(tmp_path):
    root = manifest(str(tmp_path), {"managed_installs": ["TeamViewer"]})
    with pytest.raises(BaselineError):
        suspend_forced_installs(root, approved_by="", reason="x")
    with pytest.raises(BaselineError):
        suspend_forced_installs(root, approved_by="Cyril", reason="  ")
    assert plistlib.load(open(os.path.join(root, "manifests", "all"), "rb"))[
        "managed_installs"] == ["TeamViewer"], "a refused suspension must change nothing"


def test_the_check_reports_every_remaining_forced_section(tmp_path):
    root = manifest(str(tmp_path), {"managed_installs": ["TeamViewer"]})
    assert forced_installs(root) == {"all.managed_installs": ["TeamViewer"]}
    suspend_forced_installs(root, approved_by="Cyril", reason="x")
    assert forced_installs(root) == {}
