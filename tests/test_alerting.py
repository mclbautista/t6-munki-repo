"""Alert decisions: what is actionable, what is checkable, and what stays silent.

Written before `munki_fleet/alerting.py` exists (ticket 15). The observation fixtures are the
**recorded store** from the live run of 2026-09-13 (`tests/fixtures/probe/recorded-run-records.jsonl`),
so the fleet conditions are derived from a real machine's answer rather than from a payload written
to match the parser.

The one reading that is *not* recorded is the healthy one: no machine in the fleet resolves its own
machine manifest yet (ticket 06), so a healthy reading cannot be captured until that lands. It is
built by copying the recorded observed record verbatim and changing the two fields that make it
healthy (the machine's name and its resolved `manifest_name`) — recorded here rather than silently
synthesised.
"""
import json
import os
import pathlib

import pytest

from munki_fleet import alerting
from munki_fleet.drift import DriftReport, Finding, IntegrityReport

RECORDED_STORE = pathlib.Path(__file__).parent / "fixtures/probe/recorded-run-records.jsonl"
INVENTORY = pathlib.Path(__file__).parent.parent / "data" / "machines.json"
OBSERVED_AT = "2026-09-13T19:39:19+08:00"
NOW = "2026-09-13T19:45:00+08:00"


# --- fixtures ------------------------------------------------------------------------------------

def recorded_records():
    return [json.loads(line) for line in RECORDED_STORE.read_text().splitlines() if line.strip()]


def reading(host, serial=None, outcome="observed", manifest=None, rejections=0, reason=None,
            address=None, observed_at=OBSERVED_AT, state=None):
    """One observation record, shaped from the recorded store rather than from memory."""
    base = next(r for r in recorded_records()
                if r.get("outcome") == "observed" and r.get("machine", {}).get("serial") == "RWJ57V9PW4")
    record = json.loads(json.dumps(base))
    record["observed_at"] = observed_at
    record["target"] = {"address": address or f"192.168.88.{abs(hash(host)) % 200 + 10}",
                        "host": host, "name": host, "serial": serial}
    record["outcome"] = outcome
    record["reason"] = reason
    if outcome != "observed":
        record["machine"] = None
        record["state"] = None
        record["source"] = None
        return record
    record["machine"] = {"arch": "arm64", "hostname": f"{host}.local", "model": "Mac16,10",
                         "munki_version": "7.3.0.5808", "os_build": "25G83", "os_vers": "26.6.2",
                         "serial": serial}
    if state is not None:
        record["state"] = state
    else:
        record["state"] = json.loads(json.dumps(base["state"]))
        record["state"]["manifest_name"] = manifest or host
        record["state"]["architecture_rejections"] = (
            record["state"]["architecture_rejections"][:rejections])
    return record


def clean_reports():
    return DriftReport(), IntegrityReport()


# --- repository conditions -----------------------------------------------------------------------

def test_a_clean_repository_and_a_fresh_fleet_are_silent():
    """Every expected machine observed, fresh, resolving its own manifest: nothing to say."""
    expected = alerting.load_inventory(str(INVENTORY))
    records = [reading(machine.name, serial=machine.serial, manifest=machine.manifest)
               for machine in expected]
    conditions = alerting.conditions(drift_report=DriftReport(), integrity_report=IntegrityReport(),
                                     records=records, expected=expected, now=NOW, max_age=3600,
                                     store_path="/tmp/observations.jsonl")
    assert conditions == []


def test_drift_categories_are_red_and_each_names_a_checkable_source():
    report = DriftReport(only_on_target=["catalogs/all"], missing_on_target=["manifests/all"],
                         differing=["pkgsinfo/X-1.0.pkginfo"], unreadable=["icons/_icon_hashes.plist"])
    conditions = alerting.drift_conditions(report, http_base="http://192.168.88.188/MunkiRepo")
    keys = {c.key for c in conditions}
    assert keys == {"drift:only_on_target", "drift:missing_on_target", "drift:differing",
                    "drift:unreadable"}
    assert all(c.severity == alerting.SEVERITY_RED for c in conditions)
    assert all(c.references for c in conditions)
    differing = next(c for c in conditions if c.key == "drift:differing")
    assert "http://192.168.88.188/MunkiRepo/pkgsinfo/X-1.0.pkginfo" in differing.references


def test_references_are_paths_when_no_http_base_is_known():
    report = DriftReport(differing=["pkgsinfo/X-1.0.pkginfo"])
    condition = alerting.drift_conditions(report)[0]
    assert condition.references == ("pkgsinfo/X-1.0.pkginfo",)


def test_integrity_findings_are_graded_by_whether_an_install_would_fail():
    red = {"payload_missing", "pkginfo_missing", "item_not_in_catalog", "manifest_unresolved",
           "catalog_unreadable"}
    orange = {"duplicate_name", "catalog_membership_mismatch", "catalog_entry_without_pkginfo"}
    report = IntegrityReport(findings=[
        Finding(kind=kind, subject="X", detail="d", manifests=["m"])
        for kind in sorted(red | orange)])
    conditions = {c.key: c for c in alerting.integrity_conditions(report)}
    for kind in red:
        assert conditions[f"integrity:{kind}"].severity == alerting.SEVERITY_RED, kind
    for kind in orange:
        assert conditions[f"integrity:{kind}"].severity == alerting.SEVERITY_ORANGE, kind
    assert all(c.references for c in conditions.values())


def test_a_payload_finding_points_at_the_payload_the_detail_names():
    report = IntegrityReport(findings=[Finding(kind="payload_missing", subject="X",
                                              detail="payload not present on the target: pkgs/X.dmg",
                                              manifests=["202-TOC-M4-Max"])])
    condition = alerting.integrity_conditions(report, http_base="http://nas/MunkiRepo")[0]
    assert "http://nas/MunkiRepo/pkgs/X.dmg" in condition.references
    assert "202-TOC-M4-Max" in condition.detail


# --- fleet conditions ----------------------------------------------------------------------------

def test_the_inventory_is_the_expected_fleet_and_includes_the_known_absent_row():
    expected = alerting.load_inventory(str(INVENTORY))
    names = {m.name for m in expected}
    assert len(expected) == 17          # 16 inventory rows + the known-absent row
    assert "Cyrils-Mac-mini" in names   # known_absent: a fleet member with no ARD row
    assert "202-TOC-M4-Max" in names


def test_a_machine_that_falls_back_to_site_default_is_actionable():
    conditions = alerting.observation_conditions(
        [reading("Cyrils-Mac-mini", serial="RWJ57V9PW4", manifest="site_default")],
        expected=alerting.load_inventory(str(INVENTORY)), now=NOW, max_age=3600,
        store_path="/tmp/observations.jsonl")
    condition = next(c for c in conditions if c.key == "fleet:manifest-unexpected:RWJ57V9PW4")
    assert condition.severity == alerting.SEVERITY_ORANGE
    assert "site_default" in condition.detail
    assert "Cyrils-Mac-mini" in condition.detail
    # Two sources: the reading that says what it resolved, and the inventory row that says what it
    # was supposed to resolve.
    assert condition.references == ("/tmp/observations.jsonl "
                                    f"(run {OBSERVED_AT}/4299990c)",
                                    f"{INVENTORY}#known_absent[0]")


def test_an_unreachable_machine_is_actionable_and_names_the_transport_reason():
    records = [r for r in recorded_records() if r.get("kind") != "run"]
    conditions = alerting.observation_conditions(records, expected=alerting.load_inventory(str(INVENTORY)),
                                                 now="2026-09-13T19:40:00+08:00", max_age=3600,
                                                 store_path="/tmp/observations.jsonl")
    condition = next(c for c in conditions if c.key == "fleet:not-reached:RW3HL9FL4M")
    assert "unreachable" in condition.detail
    assert "Permission denied" in condition.detail      # the transport's own words, quoted


def test_a_machine_that_has_never_been_probed_is_actionable():
    records = [reading("Cyrils-Mac-mini", serial="RWJ57V9PW4", manifest="Cyrils-Mac-mini")]
    conditions = alerting.observation_conditions(records, expected=alerting.load_inventory(str(INVENTORY)),
                                                 now=NOW, max_age=3600, store_path="/tmp/obs.jsonl")
    keys = {c.key for c in conditions}
    assert "fleet:unobserved:RW3HL9FL4M" in keys        # 202-TOC-M4-Max: never probed successfully
    assert not any(c.key.endswith("RWJ57V9PW4") for c in conditions)


def test_a_stale_reading_reports_staleness_and_not_its_state_as_current():
    records = [reading("Cyrils-Mac-mini", serial="RWJ57V9PW4", manifest="site_default", rejections=2,
                       observed_at="2026-09-13T15:00:00+08:00")]
    conditions = alerting.observation_conditions(records, expected=alerting.load_inventory(str(INVENTORY)),
                                                 now=NOW, max_age=3600, store_path="/tmp/obs.jsonl")
    stale = next(c for c in conditions if c.key == "fleet:stale:RWJ57V9PW4")
    assert "stale" in stale.title
    assert "age 17100s" in stale.detail    # 19:45:00 - 15:00:00, the age and not an adjective
    # The stale reading's own state is not reported as current fact, which is the invariant
    # the ticket's notes state: a stale observation is never alerted on as if it were current.
    assert not any(c.key in ("fleet:manifest-unexpected:RWJ57V9PW4", "fleet:rejection:RWJ57V9PW4")
                   for c in conditions)


def test_an_architecture_rejection_is_actionable_per_machine():
    records = [reading("202-TOC-M4-Max", serial="RW3HL9FL4M", rejections=2)]
    conditions = alerting.observation_conditions(records, expected=alerting.load_inventory(str(INVENTORY)),
                                                 now=NOW, max_age=3600, store_path="/tmp/obs.jsonl")
    condition = next(c for c in conditions if c.key == "fleet:rejection:RW3HL9FL4M")
    assert "IBMAsperaConnect" in condition.detail
    assert "arm64" in condition.detail


def test_a_reading_with_no_inventory_row_is_actionable():
    records = [reading("Ghost-Mac-9", serial="ZZZZZZZZZZ")]
    conditions = alerting.observation_conditions(records, expected=alerting.load_inventory(str(INVENTORY)),
                                                 now=NOW, max_age=3600, store_path="/tmp/obs.jsonl")
    assert any(c.key == "fleet:uninventoried:ZZZZZZZZZZ" for c in conditions)


def test_condition_keys_are_stable_across_runs():
    records = [reading("Cyrils-Mac-mini", serial="RWJ57V9PW4", manifest="site_default")]
    first = alerting.observation_conditions(records, expected=alerting.load_inventory(str(INVENTORY)),
                                            now=NOW, max_age=3600, store_path="/tmp/obs.jsonl")
    second = alerting.observation_conditions(records, expected=alerting.load_inventory(str(INVENTORY)),
                                            now=NOW, max_age=3600, store_path="/tmp/obs.jsonl")
    assert [c.key for c in first] == [c.key for c in second]
    assert {c.key for c in first} == {c.key for c in second}


# --- the message ---------------------------------------------------------------------------------

def red_condition(key="drift:differing", references=("pkgsinfo/X-1.0.pkginfo",)):
    return alerting.Condition(key=key, severity=alerting.SEVERITY_RED, title=f"{key} title",
                              detail="the bytes differ", references=tuple(references))


def orange_condition(key="fleet:stale:RWJ57V9PW4", references=("/tmp/obs.jsonl",)):
    return alerting.Condition(key=key, severity=alerting.SEVERITY_ORANGE, title=f"{key} title",
                              detail="age 17400s", references=tuple(references))


def test_the_message_carries_the_highest_severity_and_a_source_line_for_every_condition():
    message = alerting.render([orange_condition(), red_condition()], created_at=NOW)
    assert message.severity == alerting.SEVERITY_RED
    assert message.body.count("source:") == 2
    assert "pkgsinfo/X-1.0.pkginfo" in message.body
    assert "/tmp/obs.jsonl" in message.body
    assert "🔴" in message.body and "🟠" in message.body


def test_a_message_lists_one_line_per_condition_and_says_what_it_dropped():
    conditions = [red_condition(key=f"drift:{n}", references=(f"pkgsinfo/{n}.pkginfo",))
                  for n in range(4)]
    message = alerting.render(conditions, created_at=NOW, max_conditions=2)
    assert message.body.count("source:") == 2
    assert "2 more" in message.body
    assert len(message.conditions) == 4          # the record keeps all of them


def test_a_long_reference_list_is_bounded_and_says_so():
    condition = red_condition(references=tuple(f"catalogs/{n}" for n in range(5)))
    message = alerting.render([condition], created_at=NOW, max_refs=2)
    assert message.body.count("source:") == 2
    assert "3 more" in message.body


def test_a_condition_without_a_source_is_refused():
    with pytest.raises(ValueError):
        alerting.Condition(key="x", severity=alerting.SEVERITY_RED, title="t", detail="d",
                           references=())


def test_an_empty_message_is_refused():
    with pytest.raises(ValueError):
        alerting.render([], created_at=NOW)


def test_the_message_never_reads_an_unobserved_machine_as_compliant():
    records = [r for r in recorded_records() if r.get("kind") != "run"]
    conditions = alerting.observation_conditions(records, expected=alerting.load_inventory(str(INVENTORY)),
                                                 now="2026-09-13T19:40:00+08:00", max_age=3600,
                                                 store_path="/tmp/obs.jsonl")
    body = alerting.render(conditions, created_at=NOW).body.lower()
    assert "unknown is not compliant" in body          # the honest claim
    for claim in ("is compliant", "healthy", "all good", "in sync", "up to date"):
        assert claim not in body                       # and no compliance claim anywhere
    assert "never been observed" in body


# --- the cycle: durable state, delivery, and silence ---------------------------------------------

def no_conditions():
    return []


def one_condition(severity=alerting.SEVERITY_RED):
    return [alerting.Condition(key="drift:differing", severity=severity, title="bytes differ",
                               detail="catalogs/all differs", references=("catalogs/all",))]


def run(tmp_path, conditions, now=NOW, outbox="outbox", state="state.json", **kwargs):
    return alerting.cycle(state_path=str(tmp_path / state), outbox=str(tmp_path / outbox),
                          conditions=conditions, now=now, **kwargs)


def receipt(tmp_path, message_id, delivered, outbox="outbox"):
    path = tmp_path / outbox / "receipts.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"message_id": message_id, "delivered": delivered,
                             "at": NOW, "detail": "" if delivered else "bot send failed"}) + "\n")


def test_a_healthy_run_emits_nothing_at_all(tmp_path):
    result = run(tmp_path, no_conditions())
    assert result.message is None
    assert result.ok
    assert not (tmp_path / "outbox").exists() or not os.listdir(tmp_path / "outbox")
    assert not (tmp_path / "outbox").exists() or list(pathlib.Path(tmp_path / "outbox").glob("*.json")) == []


def test_a_new_condition_becomes_exactly_one_message_carrying_every_source(tmp_path):
    result = run(tmp_path, one_condition() + [orange_condition()])
    assert result.message is not None
    message_files = list((tmp_path / "outbox").glob("alert-*.json"))
    assert len(message_files) == 1
    body = json.loads(message_files[0].read_text())
    assert body["severity"] == alerting.SEVERITY_RED
    assert {c["key"] for c in body["conditions"]} == {"drift:differing", "fleet:stale:RWJ57V9PW4"}
    assert body["body"].count("source:") == 2


def test_a_persisting_condition_is_not_messaged_again(tmp_path):
    first = run(tmp_path, one_condition())
    receipt(tmp_path, first.message.message_id, delivered=True)
    second = run(tmp_path, one_condition(), now="2026-09-13T20:00:00+08:00")
    assert second.message is None
    assert second.ok
    assert len(list((tmp_path / "outbox").glob("alert-*.json"))) == 1


def test_a_delivered_receipt_is_recorded_as_a_notification(tmp_path):
    first = run(tmp_path, one_condition())
    receipt(tmp_path, first.message.message_id, delivered=True)
    second = run(tmp_path, one_condition(), now="2026-09-13T20:00:00+08:00")
    assert [r["message_id"] for r in second.delivered] == [first.message.message_id]
    assert second.failed == []
    state = alerting.load_state(str(tmp_path / "state.json"))
    assert state["conditions"]["drift:differing"]["delivered_at"] == NOW
    assert state["messages"][first.message.message_id]["receipt"] == "delivered"


def test_a_failed_delivery_is_recorded_undelivered_and_the_run_does_not_succeed(tmp_path):
    first = run(tmp_path, one_condition())
    receipt(tmp_path, first.message.message_id, delivered=False)
    second = run(tmp_path, one_condition(), now="2026-09-13T20:00:00+08:00")
    assert not second.ok
    assert [r["message_id"] for r in second.failed] == [first.message.message_id]
    state = alerting.load_state(str(tmp_path / "state.json"))
    entry = state["conditions"]["drift:differing"]
    assert entry["delivered_at"] is None
    assert entry["failures"] == 1
    assert state["messages"][first.message.message_id]["receipt"] == "failed"


def test_a_condition_whose_delivery_failed_is_retried(tmp_path):
    first = run(tmp_path, one_condition())
    receipt(tmp_path, first.message.message_id, delivered=False)
    second = run(tmp_path, one_condition(), now="2026-09-13T20:00:00+08:00")
    assert second.message is not None
    assert second.message.message_id != first.message.message_id


def test_a_message_with_no_receipt_is_pending_within_its_ttl_and_undelivered_past_it(tmp_path):
    first = run(tmp_path, one_condition(), ack_ttl=900)
    pending = run(tmp_path, one_condition(), now="2026-09-13T19:50:00+08:00", ack_ttl=900)
    assert pending.ok
    assert pending.pending == [first.message.message_id]
    assert pending.message is None            # in flight: not sent a second time

    late = run(tmp_path, one_condition(), now="2026-09-13T20:30:00+08:00", ack_ttl=900)
    assert not late.ok
    assert late.undelivered == [first.message.message_id]
    state = alerting.load_state(str(tmp_path / "state.json"))
    entry = state["conditions"]["drift:differing"]
    assert entry["delivered_at"] is None and entry["failures"] == 1


def test_a_cleared_condition_that_returns_is_messaged_again(tmp_path):
    first = run(tmp_path, one_condition())
    receipt(tmp_path, first.message.message_id, delivered=True)
    cleared = run(tmp_path, no_conditions(), now="2026-09-13T20:00:00+08:00")
    assert cleared.message is None
    state = alerting.load_state(str(tmp_path / "state.json"))
    assert "drift:differing" not in state["conditions"]
    returned = run(tmp_path, one_condition(), now="2026-09-13T21:00:00+08:00")
    assert returned.message is not None


def test_a_severity_change_re_alerts_even_while_the_condition_persists(tmp_path):
    first = run(tmp_path, [orange_condition()])
    receipt(tmp_path, first.message.message_id, delivered=True)
    worse = run(tmp_path, [alerting.Condition(key="fleet:stale:RWJ57V9PW4",
                                              severity=alerting.SEVERITY_RED,
                                              title="now red", detail="d",
                                              references=("/tmp/obs.jsonl",))],
               now="2026-09-13T20:00:00+08:00")
    assert worse.message is not None
    assert worse.message.severity == alerting.SEVERITY_RED


def test_a_first_sight_of_many_conditions_is_one_message_not_many(tmp_path):
    conditions = [alerting.Condition(key=f"fleet:unobserved:{n}", severity=alerting.SEVERITY_ORANGE,
                                     title=f"machine {n} has never been observed", detail="d",
                                     references=("/tmp/obs.jsonl",)) for n in range(17)]
    result = run(tmp_path, conditions)
    assert len(list((tmp_path / "outbox").glob("alert-*.json"))) == 1
    assert result.ok


def test_dry_run_reports_the_decision_and_writes_nothing(tmp_path):
    result = run(tmp_path, one_condition(), dry_run=True)
    assert result.message is not None
    assert "catalogs/all" in result.message.body
    assert not (tmp_path / "state.json").exists()
    assert not (tmp_path / "outbox").exists()


def test_a_bound_knob_of_zero_is_refused_rather_than_meaning_silence(tmp_path):
    for kwargs in ({"ack_ttl": 0}, {"max_refs": 0}, {"max_conditions": 0}):
        with pytest.raises(ValueError):
            run(tmp_path, one_condition(), **kwargs)
    with pytest.raises(ValueError):
        alerting.conditions(drift_report=DriftReport(), integrity_report=IntegrityReport(),
                            records=[], expected=[], now=NOW, max_age=0)


# --- the command (the wiring, not the module) ----------------------------------------------------

import plistlib                                                                        # noqa: E402
import shutil                                                                          # noqa: E402

from conftest import catalog_array, write_file                                         # noqa: E402
from munki_fleet.cli import Deps, main                                                 # noqa: E402
from munki_fleet.targets import LocalDirTarget                                         # noqa: E402

MACHINE = "Test-Machine"
SERIAL = "TESTSERIAL1"
CLI_NOW = "2026-09-14T09:00:00+08:00"


def cli_fixture(tmp_path, drift=False):
    """A checkout, a local target that serves it, an inventory and one fresh reading.

    `drift=True` adds one file to the target that the checkout does not have, which is the
    hand-edit case this whole project exists to make visible.
    """
    root, target = tmp_path / "checkout", tmp_path / "target"
    entry = {"name": "RemoteDesktop", "version": "1.0", "catalogs": ["testing"],
             "installer_item_location": "RemoteDesktop.dmg"}
    write_file(str(root), "pkgsinfo/RemoteDesktop-1.0.pkginfo", plistlib.dumps(entry))
    write_file(str(root), "manifests/site_default", plistlib.dumps({"included_manifests": ["all"]}))
    write_file(str(root), "manifests/all", plistlib.dumps({"managed_installs": []}))
    write_file(str(root), "catalogs/testing", catalog_array([entry]))
    write_file(str(root), "icons/_icon_hashes.plist", plistlib.dumps({}))
    write_file(str(root), "pkgs/RemoteDesktop.dmg", b"payload")
    if target.exists():
        shutil.rmtree(str(target))          # so a second cycle in one test re-uses one tree
    shutil.copytree(str(root), str(target))
    if drift:
        write_file(str(target), "catalogs/all", catalog_array([entry]))

    inventory = tmp_path / "inventory.json"
    inventory.write_text(json.dumps({"machines": [
        {"munki_name": MACHINE, "serial": SERIAL, "primary_ip": "10.0.0.1",
         "role_recorded": "toc", "role_from_manifest": "toc"}]}))
    store = tmp_path / "observations.jsonl"
    store.write_text(json.dumps(reading(MACHINE, serial=SERIAL, manifest=MACHINE,
                                        observed_at="2026-09-14T08:58:00+08:00")) + "\n")
    return root, target, inventory, store


def alert_cli(tmp_path, drift=False, extra=()):
    root, target, inventory, store = cli_fixture(tmp_path, drift=drift)
    code = main(["alert", "--metadata-root", str(root), "--target", "fake:/repo",
                 "--http-base", "http://192.168.88.188/MunkiRepo",
                 "--store", str(store), "--inventory", str(inventory),
                 "--state", str(tmp_path / "state.json"), "--outbox", str(tmp_path / "outbox"),
                 "--now", CLI_NOW, *extra],
                deps=Deps(target_factory=lambda spec: LocalDirTarget(str(target))))
    return code, tmp_path


def messages(tmp_path):
    outbox = tmp_path / "outbox"
    return sorted(outbox.glob("alert-*.json")) if outbox.exists() else []


def test_the_command_is_silent_and_succeeds_on_an_in_sync_repository(tmp_path, capsys):
    code, path = alert_cli(tmp_path)
    assert code == 0
    assert messages(path) == []
    assert "nothing newly actionable" in capsys.readouterr().out


def test_the_command_hands_over_one_message_for_a_drifted_target(tmp_path, capsys):
    code, path = alert_cli(tmp_path, drift=True)
    assert code == 0
    files = messages(path)
    assert len(files) == 1
    body = json.loads(files[0].read_text())
    assert body["severity"] == alerting.SEVERITY_RED
    assert "http://192.168.88.188/MunkiRepo/catalogs/all" in body["body"]
    assert "source:" in body["body"]


def test_a_dry_run_decides_prints_and_writes_nothing(tmp_path, capsys):
    code, path = alert_cli(tmp_path, drift=True, extra=["--dry-run"])
    out = capsys.readouterr().out
    assert code == 0
    assert messages(path) == []
    assert not (path / "state.json").exists()
    assert "the message this cycle would hand over" in out
    assert "source: http://192.168.88.188/MunkiRepo/catalogs/all" in out


def test_the_command_exits_non_zero_when_a_delivery_failed(tmp_path):
    code, path = alert_cli(tmp_path, drift=True)
    message_id = json.loads(messages(path)[0].read_text())["message_id"]
    with open(path / "outbox" / "receipts.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"message_id": message_id, "delivered": False,
                             "at": CLI_NOW, "detail": "bot send failed"}) + "\n")
    code, _ = alert_cli(tmp_path)
    assert code == 1


def test_the_command_refuses_a_bound_of_zero(tmp_path, capsys):
    code, _ = alert_cli(tmp_path, extra=["--ack-ttl", "0"])
    assert code == 2
    assert "ack_ttl" in capsys.readouterr().err


# --- the two-axis review's findings, each pinned ------------------------------------------------
#
# Every test below exists because a reviewer reproduced the defect through a public seam. The
# comments name what the old behaviour was, so a later reader can tell what is being defended.

def test_an_escalation_while_a_message_is_in_flight_is_delivered_once_that_message_is_acked(tmp_path):
    """The in-flight message carried the lower severity; it must not record the higher one as sent."""
    red = [alerting.Condition(key="fleet:stale:RWJ57V9PW4", severity=alerting.SEVERITY_RED,
                              title="now red", detail="d", references=("/tmp/obs.jsonl",))]
    first = run(tmp_path, [orange_condition()], now="2026-09-14T09:00:00+08:00")
    escalated = run(tmp_path, red, now="2026-09-14T09:05:00+08:00")
    assert escalated.message is None            # one message per condition while it is in flight
    receipt(tmp_path, first.message.message_id, delivered=True)
    after = run(tmp_path, red, now="2026-09-14T09:10:00+08:00")
    assert after.message is not None            # the escalation is still news
    assert after.message.severity == alerting.SEVERITY_RED


def test_a_message_superseded_by_a_delivered_retry_is_not_reported_undelivered_forever(tmp_path):
    """One lost message used to report failure for the rest of the state file's life."""
    first = run(tmp_path, one_condition(), ack_ttl=60)
    retry = run(tmp_path, one_condition(), now="2026-09-14T09:10:00+08:00", ack_ttl=60)
    assert retry.undelivered == [first.message.message_id]
    receipt(tmp_path, retry.message.message_id, delivered=True)
    after = run(tmp_path, one_condition(), now="2026-09-14T09:20:00+08:00", ack_ttl=60)
    assert after.undelivered == []
    assert after.superseded == [first.message.message_id]
    assert after.ok


def test_an_unreadable_clock_is_refused_rather_than_read_as_in_flight(tmp_path):
    run(tmp_path, one_condition(), ack_ttl=60)
    with pytest.raises(alerting.AlertError):
        run(tmp_path, one_condition(), now="yesterday", ack_ttl=60)


def test_a_ledger_entry_whose_age_cannot_be_read_is_undelivered_not_pending(tmp_path):
    """An age nobody can establish must not read as 'in flight', which is how an alert disappears."""
    state = {"version": alerting.STATE_VERSION, "updated_at": NOW,
             "conditions": {}, "messages": {"alert-x": {"created_at": "yesterday", "keys": ["k"],
                                                        "rendered_keys": ["k"], "receipt": None}}}
    (tmp_path / "state.json").write_text(json.dumps(state))
    result = run(tmp_path, one_condition())
    assert result.undelivered == ["alert-x"]
    assert not result.ok


def test_conditions_elided_from_the_digest_are_not_recorded_as_notified(tmp_path):
    """A truncated digest told nobody about the conditions it dropped, so they stay actionable."""
    conditions = [alerting.Condition(key=f"fleet:unobserved:{n}", severity=alerting.SEVERITY_ORANGE,
                                     title=f"machine {n}", detail="d", references=("/tmp/obs",))
                  for n in range(12)]
    first = run(tmp_path, conditions, max_conditions=10)
    assert len(first.message.rendered_keys) == 10
    assert len(first.sent) == 12
    receipt(tmp_path, first.message.message_id, delivered=True)
    second = run(tmp_path, conditions, now="2026-09-14T09:30:00+08:00", max_conditions=10)
    assert second.message is not None
    assert [c.key for c in second.sent] == ["fleet:unobserved:10", "fleet:unobserved:11"]


def test_a_duplicate_key_is_one_condition_at_the_higher_severity(tmp_path):
    result = run(tmp_path, [orange_condition(), red_condition(key="fleet:stale:RWJ57V9PW4")])
    assert len(result.conditions) == 1
    assert len(result.sent) == 1
    assert result.message.severity == alerting.SEVERITY_RED
    assert result.message.body.count("source:") == 1


def test_a_receipt_for_a_message_the_state_does_not_hold_is_reported_and_changes_nothing(tmp_path):
    run(tmp_path, no_conditions())
    receipt(tmp_path, "alert-nobody-wrote-this", delivered=False)
    result = run(tmp_path, no_conditions(), now="2026-09-14T09:40:00+08:00")
    assert [r["message_id"] for r in result.stray] == ["alert-nobody-wrote-this"]
    assert result.ok                                # it names no condition, so it owes none
    state = alerting.load_state(str(tmp_path / "state.json"))
    assert state["messages"] == {}                  # and it is not materialised into the ledger


def test_an_inventory_row_the_alert_could_not_check_is_refused(tmp_path):
    inventory = tmp_path / "inventory.json"
    inventory.write_text(json.dumps({"machines": [{"munki_name": None, "serial": None}]}))
    with pytest.raises(ValueError):
        alerting.load_inventory(str(inventory))


def test_two_inventory_rows_for_one_machine_are_refused(tmp_path):
    inventory = tmp_path / "inventory.json"
    inventory.write_text(json.dumps({"machines": [
        {"munki_name": "A", "serial": "SAME"},
        {"munki_name": "B", "serial": "SAME"}]}))
    with pytest.raises(ValueError):
        alerting.load_inventory(str(inventory))


def test_the_command_refuses_a_state_file_it_cannot_trust(tmp_path, capsys):
    code, path = alert_cli(tmp_path)
    assert code == 0
    (path / "state.json").write_text(json.dumps({"version": 99, "conditions": {}, "messages": {}}))
    code, _ = alert_cli(tmp_path)
    assert code == 3
    assert "version 99" in capsys.readouterr().err


def test_the_command_refuses_a_receipt_file_it_cannot_trust(tmp_path, capsys):
    code, path = alert_cli(tmp_path, drift=True)
    assert code == 0
    with open(path / "outbox" / "receipts.jsonl", "a", encoding="utf-8") as fh:
        fh.write("{not json\n")
    code, _ = alert_cli(tmp_path)
    assert code == 3
    assert "receipts.jsonl line 1" in capsys.readouterr().err
