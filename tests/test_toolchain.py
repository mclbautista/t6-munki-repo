"""The version relationship, and the before/after harness that makes a tool change checkable."""
import json
import os

import pytest

from munki_fleet.toolchain import (TOOLS, ToolVersion, client_versions, compare_build_to, major,
                                   read_versions, relationship)


def runner_saying(text, returncode=0):
    def run(host, command, timeout=None):
        return returncode, text.encode(), b""
    return run


def test_versions_are_read_by_running_the_tool_on_the_machine_that_holds_it():
    versions = read_versions(runner_saying("makecatalogs=7.3.0.5808\nmunkiimport=7.3.0.5808\n"),
                             "Cyrils-Mac-mini")
    assert [v.tool for v in versions] == ["makecatalogs", "munkiimport"]
    assert versions[0].version == "7.3.0.5808"
    assert versions[0].command == "/usr/local/munki/makecatalogs --version"
    assert versions[0].host == "Cyrils-Mac-mini"


def test_all_three_tools_are_asked_for():
    seen = {}

    def run(host, command, timeout=None):
        seen["command"] = command
        return 0, b"makecatalogs=7.3.0\n", b""

    read_versions(run, "h")
    for tool in TOOLS:
        assert tool in seen["command"], f"{tool} must be asked for"


def test_a_machine_without_the_tools_is_an_error_not_an_empty_answer():
    with pytest.raises(RuntimeError):
        read_versions(runner_saying("", returncode=0), "h")
    with pytest.raises(RuntimeError):
        read_versions(runner_saying("", returncode=1), "h")


def test_a_builder_behind_a_client_is_the_defect_that_was_actually_present():
    out = relationship([ToolVersion("admin", "makecatalogs", "6.6.0.4686", "c")],
                       [{"serial": "RW3HL9FL4M", "munki_version": "7.3.0.5808"}])
    assert out.aligned is False
    assert any("behind a client" in f for f in out.findings)
    assert any("reorder" in f for f in out.findings), "the finding says why it matters"


def test_aligned_versions_are_reported_as_aligned():
    out = relationship([ToolVersion("build", "makecatalogs", "7.3.0.5808", "c")],
                       [{"serial": "A", "munki_version": "7.3.0.5808"},
                        {"serial": "B", "munki_version": "7.3.1"}])
    assert out.aligned is True and out.findings == []


def test_a_builder_newer_than_every_client_is_flagged_too():
    out = relationship([ToolVersion("build", "makecatalogs", "8.0", "c")],
                       [{"serial": "A", "munki_version": "7.3.0.5808"}])
    assert out.aligned is False
    assert any("newer than every client" in f for f in out.findings)


def test_the_relationship_says_what_it_cannot_state_instead_of_passing():
    assert relationship([], [{"serial": "A", "munki_version": "7.3"}]).aligned is False
    out = relationship([ToolVersion("b", "makecatalogs", "7.3", "c")], [])
    assert out.aligned is False
    assert any("no client version observed" in f for f in out.findings)


def test_major_parsing_refuses_to_guess():
    assert major("7.3.0.5808") == 7
    assert major("unversioned") is None and major("") is None


def test_client_versions_come_from_the_observation_store():
    records = [
        {"kind": "run", "run_id": "r", "targeted": 1},
        {"kind": "observation", "observed_at": "2026-09-13T19:00:00+08:00", "outcome": "observed",
         "target": {"host": "Cyrils-Mac-mini"}, "machine": {"serial": "RWJ57V9PW4"},
         "state": {"munki_version": "7.3.0.5808"}},
        {"kind": "observation", "observed_at": "2026-09-13T19:00:00+08:00", "outcome": "unobserved",
         "target": {"host": "Away"}, "machine": None, "state": None},
        {"kind": "observation", "observed_at": "2026-09-13T18:00:00+08:00", "outcome": "observed",
         "target": {"host": "Cyrils-Mac-mini"}, "machine": {"serial": "RWJ57V9PW4"},
         "state": {"munki_version": "7.3.0.0000"}},
    ]
    clients = client_versions(None, records=records)
    assert clients == [{"serial": "RWJ57V9PW4", "host": "Cyrils-Mac-mini",
                        "munki_version": "7.3.0.5808", "observed_at": "2026-09-13T19:00:00+08:00"}], \
        "the newest observation wins, and an unobserved machine contributes no version"


# --- the before/after harness --------------------------------------------------------------------

class Build:
    def __init__(self, catalogs):
        self.catalogs = catalogs


def catalog(entries):
    """Real catalog bytes, because the differ parses them as a plist."""
    import plistlib
    return plistlib.dumps([{"name": name, "version": version, "catalogs": ["testing"]}
                           for name, version in entries])


def test_identical_bytes_are_reported_as_identical():
    same = catalog([("A", "1.0")])
    results = compare_build_to(lambda name: same, Build({"all": same}), ["all"])
    assert results["all"]["identical"] is True
    assert results["all"]["explanation"] == "identical bytes"
    assert results["all"]["has_item_changes"] is False


def test_an_explained_difference_names_the_items():
    before = catalog([("A", "1.0"), ("B", "2.0")])
    after = catalog([("A", "1.0")])
    entry = compare_build_to(lambda name: before, Build({"all": after}), ["all"])["all"]
    assert entry["identical"] is False and entry["has_item_changes"] is True
    assert "B" in entry["item_diff"] and "removed" in entry["item_diff"]
    assert entry["explanation"] == "every difference is explained by the item-level diff"


def test_a_difference_with_no_item_change_is_called_a_serialisation_difference():
    """A tool version can reorder entries without changing any of them."""
    before = catalog([("A", "1.0"), ("C", "2.0")])
    after = catalog([("C", "2.0"), ("A", "1.0")])
    entry = compare_build_to(lambda name: before, Build({"all": after}), ["all"])["all"]
    assert entry["identical"] is False
    assert entry["has_item_changes"] is False
    assert "serialised or ordered differently" in entry["explanation"]


def test_a_catalog_on_only_one_side_is_not_called_a_rebuild_difference():
    entry = compare_build_to(lambda name: None, Build({"all": catalog([("A", "1.0")])}),
                             ["all"])["all"]
    assert entry["identical"] is False
    assert "only on one side" in entry["explanation"]
    entry = compare_build_to(lambda name: catalog([("A", "1.0")]), Build({}), ["all"])["all"]
    assert "only on one side" in entry["explanation"]


def test_an_unreadable_pre_image_is_explained_rather_than_crashing_the_harness():
    """The harness compares old artifacts; an old artifact can be unreadable."""
    entry = compare_build_to(lambda name: b"not a plist at all", Build({"all": catalog([("A", "1.0")])}),
                             ["all"])["all"]
    assert entry["identical"] is False
    assert entry["has_item_changes"] is None
    assert "cannot be explained item by item" in entry["explanation"]
