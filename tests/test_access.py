"""The declared SSH access path, and the records that cannot be trusted.

Ticket 01. The collector used to derive a login path from the inventory address and get
`cyrilbautista@<address>` for a fleet whose machines answer to another account entirely. These tests
pin the rule that replaces it: a machine's transport is *declared*, used verbatim, or refused — the
code never invents one. Nothing here touches a live Mac: the map is a file and the runner is injected.
"""
import json
import os

import pytest

from munki_fleet.access import (ACCESS_SCHEMA_VERSION, NO_ACCESS_MAP, RECORD_DUPLICATE,
                                RECORD_MALFORMED, RECORD_SERIAL_MISMATCH, AccessMap)


def write_map(tmp_path, records, schema_version=ACCESS_SCHEMA_VERSION):
    path = os.path.join(str(tmp_path), "ssh-access.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"schema_version": schema_version, "machines": records}, fh)
    return path


def target(name="Sixto-5", serial="C07D317NPJJ7", address="192.168.88.151"):
    """A machine as the identity inventory describes it (data/machines.json's row shape)."""
    return {"host": name, "address": address, "serial": serial, "name": name}


# --- a declared destination is the one that is used -------------------------------------------------

def test_a_declared_record_resolves_to_its_ssh_destination(tmp_path):
    access = AccessMap.load(write_map(tmp_path, [
        {"name": "Sixto-5", "serial": "C07D317NPJJ7", "destination": "t6-mac-mini"},
    ]))
    resolution = access.resolve(target())
    assert resolution.destination == "t6-mac-mini"
    assert resolution.defect is None


@pytest.mark.parametrize("destination", ["t6-mac-mini", "t6@192.168.88.175", "192.168.88.175"])
def test_the_declared_destination_is_used_verbatim_never_synthesised(tmp_path, destination):
    """A bare address must not become `t6@<address>` and an alias must not become `t6@<alias>`."""
    access = AccessMap.load(write_map(tmp_path, [
        {"name": "202A-Mac-Mini-M4", "destination": destination},
    ]))
    resolution = access.resolve(target("202A-Mac-Mini-M4", serial="X904F44LHX"))
    assert resolution.destination == destination


# --- declarations that must not be used ------------------------------------------------------------

BLOCKING = {
    "no destination": {"name": "Sixto-5"},
    "a destination carrying a credential": {"name": "Sixto-5", "destination": "t6:hunter2@192.168.88.151"},
    "a destination carrying a port": {"name": "Sixto-5", "destination": "t6@192.168.88.151:2222"},
    "a destination with a space in it": {"name": "Sixto-5", "destination": "t6@192.168.88.151 -o ProxyCommand=x"},
    "a misspelled field": {"name": "Sixto-5", "destintion": "t6-mac-mini"},
}


@pytest.mark.parametrize("record", list(BLOCKING.values()), ids=list(BLOCKING))
def test_a_malformed_record_blocks_the_machine_it_names(tmp_path, record):
    access = AccessMap.load(write_map(tmp_path, [record]))
    resolution = access.resolve(target())
    assert resolution.destination is None, "a malformed declaration must not be used"
    assert resolution.defect.kind == RECORD_MALFORMED
    assert resolution.defect.blocks is True, "the probe must not fall back to the undeclared path"


def test_two_records_naming_one_machine_are_refused_as_ambiguous(tmp_path):
    access = AccessMap.load(write_map(tmp_path, [
        {"name": "Sixto-5", "destination": "t6-mac-mini"},
        {"name": "Sixto-5", "destination": "t6@192.168.88.151"},
    ]))
    resolution = access.resolve(target())
    assert resolution.destination is None
    assert resolution.defect.kind == RECORD_DUPLICATE and resolution.defect.blocks is True


def test_a_record_whose_serial_contradicts_the_machine_blocks_it(tmp_path):
    """The record says this name's serial is X, the machine's own inventory row says Y."""
    access = AccessMap.load(write_map(tmp_path, [
        {"name": "Sixto-5", "serial": "SN-OF-A-DIFFERENT-MACHINE", "destination": "t6-mac-mini"},
    ]))
    resolution = access.resolve(target(serial="C07D317NPJJ7"))
    assert resolution.destination is None
    assert resolution.defect.kind == RECORD_SERIAL_MISMATCH and resolution.defect.blocks is True
    assert "SN-OF-A-DIFFERENT-MACHINE" in resolution.defect.detail, "the defect names both serials"


def test_a_record_matching_on_name_alone_is_usable_when_the_serial_is_unknown(tmp_path):
    """A machine with no inventory serial (202B-Mac-Studio) can still have a declared path."""
    access = AccessMap.load(write_map(tmp_path, [
        {"name": "202B-Mac-Studio", "destination": "192.168.88.176"},
    ]))
    resolution = access.resolve(target("202B-Mac-Studio", serial=None, address="192.168.88.176"))
    assert resolution.destination == "192.168.88.176" and resolution.defect is None


@pytest.mark.parametrize("payload, ids", [
    (None, "the file is absent"),
    ("{not json", "the file is not JSON"),
    ({"schema_version": 99, "machines": []}, "the schema version is not ours"),
    ({"schema_version": 1, "machines": [], "machien": []}, "a top-level field is misspelled"),
    ({"schema_version": 1, "machines": [{"destination": "t6-mac-mini"}]}, "a row names no machine"),
], ids=lambda value: value if isinstance(value, str) else "")
def test_a_map_that_cannot_be_attributed_to_machines_is_unavailable(tmp_path, payload, ids):
    """A declaration nobody can attribute is not a declaration: the map is unusable, not guessed at."""
    path = os.path.join(str(tmp_path), "ssh-access.json")
    if payload is not None:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(payload if isinstance(payload, str) else json.dumps(payload))
    access = AccessMap.load(path)
    assert access.available is False and access.reason
    assert access.resolve(target()).defect.kind == NO_ACCESS_MAP
