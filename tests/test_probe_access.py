"""What the probe does with a declared access path, and with a declaration it cannot trust.

The transport contract is one thing; a collector that ignores it is the defect the contract exists
to prevent. These tests drive `probe_run` through the resolved targets, with the runner injected, so
the assertion is about *where the collector tried to go*.
"""
import json
import os

from conftest import access_map

from munki_fleet.access import AccessMap, resolve_targets
from munki_fleet.probe import probe_run

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "probe", "healthy-envelope.txt")


def envelope_text():
    with open(FIXTURE, encoding="utf-8") as fh:
        return fh.read()


def inventory_target(name="Sixto-5", serial="C07D317NPJJ7", address="192.168.88.151"):
    return {"host": name, "address": address, "serial": serial, "name": name}


def recording_runner(envelope=None, returncode=0, stderr=b""):
    """A runner that keeps the address it was handed, so 'where did it go' is assertable."""
    calls = []

    def run(address, command, timeout=None):
        calls.append(address)
        if returncode:
            return returncode, b"", stderr
        return 0, (envelope or envelope_text()).encode(), b""

    run.calls = calls
    return run


def test_the_probe_travels_to_the_declared_destination_not_the_inventory_address(tmp_path):
    access = AccessMap.load(access_map(tmp_path, [
        {"name": "Sixto-5", "serial": "C07D317NPJJ7", "destination": "t6-mac-mini"},
    ]))
    targets, _ = resolve_targets([inventory_target()], access)
    runner = recording_runner()

    probe_run(targets, runner, store_path=None, observer="collector", now="2026-09-14T21:00:00+08:00")

    assert runner.calls == ["t6-mac-mini"], \
        "the declared destination is the transport; the inventory address is only where it was seen"


def test_a_blocked_target_is_recorded_unobserved_and_never_contacted(tmp_path):
    access = AccessMap.load(access_map(tmp_path, [
        {"name": "Sixto-5", "destination": "t6:hunter2@192.168.88.151"},
    ]))
    targets, defects = resolve_targets([inventory_target()], access)
    assert defects and defects[0].blocks is True

    runner = recording_runner()
    run, observations = probe_run(targets, runner, store_path=None, observer="collector",
                                  now="2026-09-14T21:00:00+08:00")

    assert runner.calls == [], "a record that cannot be trusted must not be used or replaced"
    assert json.loads(run.to_json())["unobserved"] == 1, "and it stays in the run's completeness"
    assert observations[0].outcome == "unobserved"
    assert observations[0].reason == "access-record-malformed"
    assert observations[0].state is None and observations[0].machine is None


def test_a_machine_with_no_access_record_is_probed_but_its_reading_says_so(tmp_path):
    """No declaration is not a defect — but the reading must not pass as a declared path."""
    access = AccessMap.load(access_map(tmp_path, [{"name": "Someone-Else",
                                                  "destination": "t6-mac-mini"}]))
    targets, defects = resolve_targets([inventory_target("202A-Mac-Mini-M4", "X904F44LHX")], access)
    assert [d.kind for d in defects] == ["no-access-record"] and defects[0].blocks is False

    runner = recording_runner()
    run, observations = probe_run(targets, runner, store_path=None, observer="collector",
                                  now="2026-09-14T21:00:00+08:00")

    assert runner.calls == ["192.168.88.151"], "it is still probed, by the inventory address"
    assert observations[0].outcome == "observed"
    assert "no-access-record" in observations[0].problems
    assert json.loads(run.to_json())["observed"] == 1


def test_the_address_the_transport_used_is_recorded_on_the_reading(tmp_path):
    """Provenance: which path produced this reading, so a later reader can tell."""
    access = AccessMap.load(access_map(tmp_path, [
        {"name": "Sixto-5", "serial": "C07D317NPJJ7", "destination": "t6-mac-mini"},
    ]))
    targets, _ = resolve_targets([inventory_target()], access)
    _, observations = probe_run(targets, recording_runner(), store_path=None, observer="collector",
                                now="2026-09-14T21:00:00+08:00")
    body = json.loads(observations[0].to_json())
    assert body["target"]["ssh_destination"] == "t6-mac-mini"
    assert body["target"]["address"] == "192.168.88.151"


def test_an_unreachable_machines_detail_does_not_quote_the_probe_script_back(tmp_path):
    """The transport's own message, not this probe's heredoc read back at the operator."""
    from munki_fleet.targets import TargetError

    def runner(address, command, timeout=None):
        raise TargetError(f"ssh timed out after 6s: {command}")

    _, observations = probe_run([inventory_target()], runner, store_path=None, observer="collector",
                                now="2026-09-14T21:00:00+08:00")
    detail = observations[0].detail
    assert detail.startswith("TargetError: ssh timed out after 6s")
    assert "#!/bin/sh" not in detail and "\n" not in detail
    assert observations[0].outcome == "unobserved"


def test_a_machine_probed_locally_needs_no_access_record(tmp_path):
    """`--local-host` is that transport's own declaration; a record about an ssh path does not apply."""
    access = AccessMap.load(access_map(tmp_path, [{"name": "Someone-Else", "destination": "here"}]))
    local = inventory_target("Cyrils-Mac-mini", "RWJ57V9PW4", address=None)

    targets, defects = resolve_targets([local], access, skip=lambda t: t["host"] == "Cyrils-Mac-mini")

    assert defects == [], "a transport that opens no ssh path cannot have an undeclared one"
    assert "access_defect" not in targets[0] and "ssh_destination" not in targets[0]
