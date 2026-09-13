"""The fleet state probe and the observation store.

The point of this module is that a fleet statement is read from a record with a known age, and that
"we could not reach it" can never be written in a way that reads like "it is fine".
"""
import datetime
import json
import os
import plistlib

import pytest

from munki_fleet.probe import (Observation, ObservationStore, ProbeError, latest_per_machine,
                              parse_envelope, probe_run, staleness)

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "probe", "healthy-envelope.txt")


def fixture_text():
    with open(FIXTURE, encoding="utf-8") as fh:
        return fh.read()


def fixture_report():
    """The report section of the recorded envelope, parsed the same way the collector parses it."""
    section = fixture_text().split("<<<REPORT>>>\n", 1)[1].split("\n<<<LOG>>>", 1)[0]
    return plistlib.loads(section.encode("utf-8"))


def _jsonable(value):
    """A plist report contains datetimes; JSON cannot carry them, so they become the text form."""
    if isinstance(value, datetime.datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


def envelope(**overrides):
    """A minimal envelope, with the healthy fixture's report for the parts that matter.

    Emitted as JSON on purpose: the collector must accept both, the fixture exercises the real
    plist path, and these synthetic cases stay readable.
    """
    report = _jsonable(fixture_report())
    report.update(overrides.pop("report", {}))
    lines = ["munki-fleet-probe/1"]
    lines.append(f"munki_tools={overrides.pop('munki_tools', 'yes')}")
    lines.append(f"report_present={overrides.pop('report_present', 'yes')}")
    lines.append(f"report_mtime={overrides.pop('report_mtime', '1789298823')}")
    lines.append(f"log_present={overrides.pop('log_present', 'yes')}")
    lines.append(f"log_mtime={overrides.pop('log_mtime', '1789298823')}")
    lines.append("<<<REPORT>>>")
    lines.append(json.dumps(report) if report is not None else "")
    lines.append("<<<LOG>>>")
    lines.append(overrides.pop("log", "2026-09-13 19:26:23.317+08:00 ### Starting managedsoftwareupdate run: auto ###"))
    return "\n".join(lines) + "\n"


def target(host="Cyrils-Mac-mini", serial="RWJ57V9PW4"):
    return {"host": host, "serial": serial, "name": host}


def runner_returning(text):
    def run(host, command, timeout=None):
        return 0, text.encode(), b""
    return run


def runner_that_fails(message="ssh: connect to host: Operation timed out"):
    def run(host, command, timeout=None):
        return 255, b"", message.encode()
    return run


# --- what the probe records for a reachable machine ---------------------------------------------

def test_a_healthy_machine_records_every_field_the_ticket_names():
    payload = parse_envelope(fixture_text())
    assert payload.munki_tools is True
    observation = Observation.from_payload(target(), payload, observed_at="2026-09-13T20:00:00+08:00",
                                           observer="munki-fleet-collector")
    state = observation.state
    assert state["munki_version"] == "7.3.0.5808"
    assert state["manifest_name"] == "site_default"
    assert state["pending_count"] == 0
    assert state["last_check"]["timestamp"], "the source's own timestamp is required"
    assert state["architecture_rejections"], "the fixture carries a real rejection"
    assert "IBMAsperaConnect" in json.dumps(state["architecture_rejections"])
    assert "arch" in json.dumps(state["architecture_rejections"]).lower()
    assert isinstance(state["warnings"], list)


def test_an_observation_carries_provenance_and_identity_never_a_name_alone():
    payload = parse_envelope(fixture_text())
    observation = Observation.from_payload(target(), payload, observed_at="2026-09-13T20:00:00+08:00",
                                           observer="munki-fleet-collector")
    body = json.loads(observation.to_json())
    assert body["machine"]["serial"] == "RWJ57V9PW4"
    assert body["observed_at"] == "2026-09-13T20:00:00+08:00"
    assert body["observer"] == "munki-fleet-collector"
    assert body["source"]["timestamp"], "the source's own timestamp"
    assert body["source"]["age_seconds"] is not None, "age, so staleness is computable"
    assert body["target"]["host"] == "Cyrils-Mac-mini"


def test_the_resolved_manifest_is_read_from_the_report_not_guessed_from_the_log():
    payload = parse_envelope(fixture_text())
    observation = Observation.from_payload(target(), payload, observed_at="2026-09-13T20:00:00+08:00",
                                           observer="x")
    assert observation.state["manifest_name"] == "site_default"
    assert observation.state["manifest_lookups"] and \
        any("not found" in line for line in observation.state["manifest_lookups"])


# --- the states that must never look healthy ----------------------------------------------------

def test_a_machine_that_cannot_be_reached_is_unobserved_with_no_state():
    observation = probe_run([target()], runner_that_fails(), store_path=None,
                            observer="collector", now="2026-09-13T20:00:00+08:00")[1][0]
    assert observation.outcome == "unobserved"
    assert observation.reason == "unreachable"
    assert observation.state is None
    body = json.loads(observation.to_json())
    assert body["state"] is None
    assert body["machine"] is None, "no state may be invented for a machine we did not reach"


def test_a_machine_without_munki_tools_is_partial_not_healthy():
    payload = parse_envelope(envelope(munki_tools="no", report_present="no"))
    observation = Observation.from_payload(target(), payload, observed_at="T", observer="x")
    assert observation.outcome == "partial"
    assert observation.reason == "no-munki-tools"
    assert observation.state is None


def test_an_unreadable_report_is_partial_and_says_why():
    broken = envelope().split("<<<REPORT>>>")[0] + "<<<REPORT>>>\n{not json\n<<<LOG>>>\n"
    payload = parse_envelope(broken)
    observation = Observation.from_payload(target(), payload, observed_at="T", observer="x")
    assert observation.outcome == "partial"
    assert observation.reason in ("unreadable-report", "no-report")
    assert observation.state is None


def test_an_empty_but_present_report_is_partial():
    payload = parse_envelope(envelope().split("<<<REPORT>>>")[0] + "<<<REPORT>>>\n\n<<<LOG>>>\n")
    observation = Observation.from_payload(target(), payload, observed_at="T", observer="x")
    assert observation.outcome == "partial"


def test_an_envelope_from_something_that_is_not_the_probe_is_rejected():
    with pytest.raises(ProbeError):
        parse_envelope("total nonsense\n")


# --- the store ------------------------------------------------------------------------------------

def test_the_store_is_append_only_and_a_second_run_cannot_rewrite_the_first(tmp_path):
    store = ObservationStore(str(tmp_path / "observations.jsonl"))
    targets = [target(), target("202-TOC-M4-Max", "RW3HL9FL4M")]
    probe_run(targets, runner_returning("bogus"), store_path=store.path, observer="collector",
              now="2026-09-13T20:00:00+08:00", run_id="run-1")
    after_first = open(store.path, encoding="utf-8").read()

    probe_run(targets, runner_returning("bogus"), store_path=store.path, observer="collector",
              now="2026-09-13T21:00:00+08:00", run_id="run-2")
    after_second = open(store.path, encoding="utf-8").read()
    assert after_second.startswith(after_first), "the first run's bytes are untouched"
    assert len(store.read()) == 2 * (1 + 2), "both runs are still there"

    ids = [r["run_id"] for r in store.read() if r["kind"] == "run"]
    assert set(ids) == {"run-1", "run-2"}, "each run has its own id"


def test_replaying_the_same_run_writes_nothing_new(tmp_path):
    """Idempotent per run (ADR 0004): a retry must not double-count itself."""
    store = ObservationStore(str(tmp_path / "observations.jsonl"))
    targets = [target()]
    run, observations = probe_run(targets, runner_returning(fixture_text()), store_path=store.path,
                                  observer="collector", now="2026-09-13T20:00:00+08:00",
                                  run_id="run-1")
    before = open(store.path, encoding="utf-8").read()
    assert store.append([run] + observations) == 0, "nothing new to write"
    assert open(store.path, encoding="utf-8").read() == before
    assert len(store.runs()) == 1


def test_a_machine_reporting_another_serial_is_flagged_not_merged(tmp_path):
    store = ObservationStore(str(tmp_path / "observations.jsonl"))
    run, observations = probe_run([target(serial="SOMETHING-ELSE")],
                                  runner_returning(fixture_text()), store_path=store.path,
                                  observer="collector", now="2026-09-13T20:00:00+08:00")
    assert observations[0].problems == ["identity-mismatch"]
    readings = latest_per_machine(store.read(), now="2026-09-13T20:00:00+08:00")
    assert list(readings) == ["RWJ57V9PW4"], "keyed by the machine's own serial, not the guess"


def test_a_run_records_its_own_completeness(tmp_path):
    store = ObservationStore(str(tmp_path / "observations.jsonl"))
    targets = [target(), target("202-TOC-M4-Max", "RW3HL9FL4M"), target("Sixto-5", "C07D317NPJJ7")]

    def runner(host, command, timeout=None):
        if host == "202-TOC-M4-Max":
            return 255, b"", b"timeout"
        if host == "Sixto-5":
            return 0, envelope(munki_tools="no", report_present="no").encode(), b""
        return 0, fixture_text().encode(), b""

    run, observations = probe_run(targets, runner, store_path=store.path, observer="collector",
                                  now="2026-09-13T20:00:00+08:00")
    body = json.loads(run.to_json())
    assert body["targeted"] == 3
    assert body["observed"] == 1 and body["partial"] == 1 and body["unobserved"] == 1
    assert body["reached"] == 2
    assert body["complete"] is False, "three targets, one unobserved: the run is not complete"
    assert body["kind"] == "run" and body["run_id"]
    assert {o.outcome for o in observations} == {"observed", "partial", "unobserved"}


def test_a_run_that_reaches_everything_is_complete(tmp_path):
    run, _ = probe_run([target()], runner_returning(fixture_text()), store_path=None,
                       observer="collector", now="2026-09-13T20:00:00+08:00")
    assert json.loads(run.to_json())["complete"] is True


# --- staleness -------------------------------------------------------------------------------------

def test_staleness_is_computed_per_machine_and_a_stale_reading_is_flagged():
    now = "2026-09-13T20:00:00+00:00"
    fresh = Observation.from_payload(target(), parse_envelope(fixture_text()),
                                     observed_at="2026-09-13T19:55:00+00:00", observer="c")
    # the second machine reports its own serial, as a real machine does
    other = envelope(report={"MachineInfo": dict(fixture_report()["MachineInfo"],
                                                 serial_number="RW3HL9FL4M")})
    old = Observation.from_payload(target("202-TOC-M4-Max", "RW3HL9FL4M"),
                                   parse_envelope(other),
                                   observed_at="2026-09-13T09:00:00+00:00", observer="c")
    assert staleness(fresh, now) == 300
    assert staleness(old, now) == 39600

    readings = latest_per_machine([fresh.to_json(), old.to_json()], now=now, max_age=3600)
    assert readings["RWJ57V9PW4"]["stale"] is False
    assert readings["RW3HL9FL4M"]["stale"] is True
    assert readings["RW3HL9FL4M"]["age_seconds"] == 39600


def test_the_latest_reading_wins_per_machine():
    older = Observation.from_payload(target(), parse_envelope(fixture_text()),
                                     observed_at="2026-09-13T18:00:00+00:00", observer="c")
    newer = Observation.from_payload(target(), parse_envelope(envelope(report={"ManifestName": "202-TOC-M4-Max"})),
                                     observed_at="2026-09-13T19:00:00+00:00", observer="c")
    readings = latest_per_machine([older.to_json(), newer.to_json()],
                                 now="2026-09-13T19:10:00+00:00", max_age=3600)
    assert readings["RWJ57V9PW4"]["observation"]["state"]["manifest_name"] == "202-TOC-M4-Max"


def test_an_unobserved_target_still_gets_a_reading_and_it_is_stale_when_old():
    unobserved = probe_run([target()], runner_that_fails(), store_path=None, observer="c",
                           now="2026-09-13T09:00:00+00:00")[1][0]
    readings = latest_per_machine([unobserved.to_json()], now="2026-09-13T20:00:00+00:00",
                                 max_age=3600)
    entry = readings["RWJ57V9PW4"]
    assert entry["stale"] is True
    assert entry["observation"]["outcome"] == "unobserved", \
        "staleness must not turn an unobserved machine into a healthy one"
