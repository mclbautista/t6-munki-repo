"""The defects the two-axis review found, each pinned by a test that would have caught it.

Every test here corresponds to something that was actually wrong in the committed implementation:
the observers were null, the local runner never fired, a target was silently dropped, an
observation without a serial crashed the command that printed it, and a torn line could wedge the
store permanently.
"""
import json
import os

import pytest

from munki_fleet import probe
from munki_fleet.cli import _inventory_targets, main
from munki_fleet.probe import (DEFAULT_OBSERVER, PROBE_VERSION, ObservationStore, ProbeError,
                               latest, parse_envelope)

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "probe")
HEALTHY = os.path.join(FIXTURE, "healthy-envelope.txt")
RECORDED = os.path.join(FIXTURE, "recorded-run-records.jsonl")


def healthy_text():
    with open(HEALTHY, encoding="utf-8") as fh:
        return fh.read()


def envelope_without_serial():
    text = healthy_text()
    head, _, rest = text.partition("<<<REPORT>>>")
    report = rest.split("\n<<<LOG>>>", 1)[0]
    stripped = "\n".join(line for line in report.splitlines()
                         if "serial_number" not in line and "<string>RWJ57V9PW4</string>" not in line)
    return head + "<<<REPORT>>>" + stripped + "\n<<<LOG>>>" + text.split("<<<LOG>>>", 1)[1]


# --- the observer was null on the default path ---------------------------------------------------

def test_a_probe_run_always_records_an_observer(tmp_path, monkeypatch):
    monkeypatch.setattr(probe, "default_runner",
                        lambda host, command, timeout=None: (0, healthy_text().encode(), b""))
    store = str(tmp_path / "observations.jsonl")
    assert main(["probe", "--store", store, "--machine",
                 "127.0.0.1@Cyrils-Mac-mini:RWJ57V9PW4"]) == 0
    observations = [r for r in ObservationStore(store).read() if r["kind"] == "observation"]
    assert observations, "the run wrote nothing"
    for record in observations:
        assert record["observer"], "every observation carries the observer identity"
    assert observations[0]["observer"] == DEFAULT_OBSERVER


# --- the local machine was silently probed over ssh ----------------------------------------------

def test_a_local_target_is_matched_on_its_address_too(tmp_path, monkeypatch, capsys):
    """The runner is handed the address, so matching only the name sent the local machine over ssh."""
    calls = []
    monkeypatch.setattr(probe, "default_runner",
                        lambda host, command, timeout=None: calls.append(host) or (0, b"", b""))

    def fake_local(host, command, timeout=None):
        calls.append(f"local:{host}")
        return 0, healthy_text().encode(), b""

    monkeypatch.setattr("munki_fleet.cli.local_runner", fake_local)
    store = str(tmp_path / "observations.jsonl")
    assert main(["probe", "--store", store, "--machine",
                 "192.168.88.202@Cyrils-Mac-mini:RWJ57V9PW4", "--local-host", "Cyrils-Mac-mini"]) == 0
    assert calls == ["local:192.168.88.202"], f"expected a local run, got {calls}"


# --- a machine the export has no row for was dropped from the fleet run --------------------------

def test_the_inventory_includes_machines_the_export_has_no_row_for(tmp_path):
    inventory = tmp_path / "machines.json"
    inventory.write_text(json.dumps({
        "machines": [{"computer_name": "202 TOC M4 Max", "munki_name": "202-TOC-M4-Max",
                      "unix_hostname": "202-TOC-M4-Max", "serial": "RW3HL9FL4M",
                      "primary_ip": "192.168.88.182"}],
        "known_absent": [{"name": "Cyrils-Mac-mini", "probe_hostname": "Cyrils-Mac-mini",
                          "serial": "RWJ57V9PW4", "primary_ip": None}],
    }), encoding="utf-8")
    targets = _inventory_targets(str(inventory))
    hosts = [t["host"] for t in targets]
    assert "Cyrils-Mac-mini" in hosts, "a known machine with no export row is still a target"
    assert targets[1]["address"] is None, "and it has no address, so it must be probed by name"


# --- an observation with no serial crashed the command that printed it ---------------------------

def test_a_report_without_a_serial_is_partial_not_observed():
    payload = parse_envelope(envelope_without_serial())
    assert payload.report is not None, "the report must still parse"
    assert "serial_number" not in json.dumps(payload.report.get("MachineInfo") or {})
    observation = probe.Observation.from_payload({"host": "h", "serial": "S"}, payload,
                                                observed_at="2026-09-13T20:00:00+08:00",
                                                observer="o")
    assert observation.outcome == "partial"
    assert observation.reason == "no-serial"
    assert observation.state is not None, "the state is real and worth keeping"


def test_the_cli_prints_a_serial_less_observation_without_crashing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(probe, "default_runner",
                        lambda host, command, timeout=None: (0, envelope_without_serial().encode(), b""))
    store = str(tmp_path / "observations.jsonl")
    assert main(["probe", "--store", store, "--machine", "127.0.0.1@h:S"]) == 0
    printed = capsys.readouterr().out
    assert "PARTIAL" in printed and "no-serial" in printed


def test_the_stored_run_record_is_exactly_what_its_json_says(tmp_path):
    """One serialisation path: what the store holds is what `to_json` produced."""
    store = ObservationStore(str(tmp_path / "observations.jsonl"))
    run, observations = probe.probe_run([{"host": "h", "serial": "S"}],
                                        lambda host, command, timeout=None: (255, b"", b"nope"),
                                        store_path=store.path, observer="o",
                                        now="2026-09-13T20:00:00+08:00", run_id="r1")
    stored = [r for r in store.read() if r["kind"] == "run"][0]
    assert stored == json.loads(run.to_json())
    assert "reached" in stored, "the computed count belongs in the record, not only in the object"


# --- a torn line could wedge the store forever ---------------------------------------------------

def test_a_torn_line_is_loud_on_read_and_does_not_wedge_the_store(tmp_path):
    store = ObservationStore(str(tmp_path / "observations.jsonl"))
    store.append([{"kind": "run", "run_id": "r1", "observed_at": "T", "observer": "o",
                   "targeted": 1, "observed": 1, "partial": 0, "unobserved": 0, "complete": True}])
    with open(store.path, "a", encoding="utf-8") as fh:
        fh.write('{"kind": "observation", "run_id": "r1", "targ')      # a torn write

    with pytest.raises(ProbeError) as excinfo:
        store.read()
    assert "line 2" in str(excinfo.value), "corruption is named, not hidden"

    written = store.append([{"kind": "observation", "run_id": "r2", "observed_at": "T",
                             "observer": "o", "target": {"host": "h", "serial": "S"},
                             "outcome": "unobserved", "reason": "unreachable"}])
    assert written == 1, "a torn line must not stop the collector recording anything ever again"


# --- the last check had a time but no result -----------------------------------------------------

def test_the_last_check_carries_a_result_and_not_a_duplicate_timestamp():
    payload = parse_envelope(healthy_text())
    observation = probe.Observation.from_payload({"host": "h", "serial": "RWJ57V9PW4"}, payload,
                                                observed_at="2026-09-13T20:00:00+08:00", observer="o")
    last = observation.state["last_check"]
    assert last["result"] in ("clean", "warnings", "failed")
    assert last["result"] == "warnings", "the fixture run carries a warning and no errors"
    assert "report_mtime" not in last, "the source block owns the mtime"


def test_a_malformed_observation_timestamp_is_tolerated_not_fatal():
    """`observed_at` comes from a caller; the summariser must not raise on a bad one."""
    payload = parse_envelope(healthy_text())
    observation = probe.Observation.from_payload({"host": "h", "serial": "RWJ57V9PW4"}, payload,
                                                observed_at="not-a-timestamp", observer="o")
    assert observation.outcome == "observed"
    assert observation.state["source_age_seconds"] is None
    assert probe.staleness(observation, now="2026-09-13T20:00:00+08:00") is None


# --- the two recorded states the ticket asks for, replayed rather than invented ------------------

def test_the_recorded_run_replays_as_a_reached_machine_and_an_unreachable_one():
    """Replayed from the verbatim store, so a machine that was not reached stays that way."""
    records = [json.loads(line) for line in open(RECORDED, encoding="utf-8") if line.strip()]
    runs = [r for r in records if r["kind"] == "run"]
    observations = [r for r in records if r["kind"] == "observation"]
    assert len(runs) == 1, "the fixture is the store of one run"
    run = runs[0]
    assert len(observations) == run["targeted"], "one record per targeted machine"
    assert run["complete"] is False, "the recorded run did not reach everything"
    assert run["unobserved"] >= 1 and run["observed"] >= 1

    reached = [r for r in observations if r["outcome"] == "observed"]
    unreachable = [r for r in observations if r["outcome"] == "unobserved"]
    assert reached and unreachable
    for record in reached:
        assert record["machine"]["serial"] == "RWJ57V9PW4"
        assert record["observer"], "every observation carries its observer"
    for record in unreachable:
        assert record["state"] is None, "no state may be written for a machine we did not reach"
        assert record["machine"] is None
        assert "Permission denied" in (record.get("detail") or ""), \
            "the transport's own message is recorded, not paraphrased"


def test_the_recorded_run_is_stale_when_read_later_and_stays_unobserved():
    records = open(RECORDED, encoding="utf-8").read()
    entry = latest("Cyrils-Mac-mini", records=[json.loads(l) for l in records.splitlines() if l],
                   now="2026-09-13T23:00:00+08:00", max_age=3600)
    assert entry is not None and entry["stale"] is True
    later = latest("202-TOC-M4-Max", records=[json.loads(l) for l in records.splitlines() if l],
                   now="2026-09-13T23:00:00+08:00", max_age=3600)
    assert later["observation"]["outcome"] == "unobserved", \
        "age must not turn an unreachable machine into a healthy one"


def test_latest_says_nothing_observed_rather_than_reachable():
    assert latest("not-a-machine", records=[json.loads(l) for l in
                                            open(RECORDED, encoding="utf-8") if l.strip()],
                  now="2026-09-13T23:00:00+08:00") is None


# --- the script and the collector must not drift apart -------------------------------------------

def test_the_client_script_declares_the_version_the_collector_requires():
    with open(probe.CLIENT_SCRIPT, encoding="utf-8") as fh:
        script = fh.read()
    assert PROBE_VERSION in script, \
        f"probe_client.sh must declare {PROBE_VERSION}; the literal is duplicated, so it drifts"
