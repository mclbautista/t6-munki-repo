"""Ticket 04: the machine identity inventory, against a fake metadata tree.

The fixture export is a trimmed copy of the real report (same column names, same
"Date Collected, 12:00 AM" quirk); the manifest tree is generated per test. Nothing
here touches a live machine, the NAS, or the operational database — probe results and
the Bays projection arrive as the JSON files the tool takes.
"""
import json
import pathlib
import plistlib

import pytest

from munki_fleet.identity import (
    ArdRecord,
    BaysRecord,
    ProbeRecord,
    build_report,
    infer_architecture,
    load_bays,
    load_manifests,
    load_role_matrix,
    main,
    normalise_name,
    parse_ard_export,
    report_to_json,
)

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "ard" / "ard_system_overview_sample.txt"
EXPORT_DATE = "9/13/26 12:00 AM"

ROLE_GROUPS = ("toc", "sound", "production", "online", "dit", "warroom",
               "coordination-admin", "client-facing", "interns-temporary")


def write_manifest(root: pathlib.Path, name: str, included, display=None):
    data = {"catalogs": ["testing"], "included_manifests": list(included)}
    if display:
        data["display_name"] = display
    manifests = root / "manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    (manifests / name).write_bytes(plistlib.dumps(data))


def fake_metadata_tree(tmp_path: pathlib.Path) -> pathlib.Path:
    """A metadata root whose manifest set disagrees with the export on purpose."""
    for role in ROLE_GROUPS:
        write_manifest(tmp_path, role, ["all"])
    write_manifest(tmp_path, "all", ["site_default"], "T6 All Macs")
    write_manifest(tmp_path, "site_default", [], "T6 site default")
    write_manifest(tmp_path, "t6-test-client", ["all"], "T6 Test Client")
    # machine manifests: one exact, one with the space, two with no machine at all
    write_manifest(tmp_path, "202-TOC-M4-Max", ["all", "toc"], "202 TOC M4 Max")
    write_manifest(tmp_path, "201-Bay-01-Mac-Pro", ["all", "sound"], "201 Bay 01")
    write_manifest(tmp_path, "303B iMac", ["all", "interns-temporary"], "303B iMac")
    write_manifest(tmp_path, "202B-Mac-Studio", ["all", "warroom"], "202B Mac Studio")
    write_manifest(tmp_path, "201-Bay-03-M1-Ultra", ["all"], "201 Bay 03")  # unassigned
    return tmp_path


def records():
    rows, _ = parse_ard_export(FIXTURE)
    return rows


def report(tmp_path, **kwargs):
    manifests, _ = load_manifests(fake_metadata_tree(tmp_path))
    return build_report(records(), manifests, source=str(FIXTURE),
                        export_date=EXPORT_DATE, **kwargs)


def kinds(rep, kind):
    return [f for f in rep.findings if f.kind == kind]


def row(rep, hostname):
    return next(r for r in rep.rows if r.unix_hostname == hostname)


class TestParseArdExport:
    def test_every_row_is_read_with_its_own_date(self):
        rows, export_date = parse_ard_export(FIXTURE)
        assert len(rows) == 6
        assert export_date == EXPORT_DATE
        assert [r.serial for r in rows][0] == "RW3HL9FL4M"
        assert rows[0].collected_at == "9/13/26 12:00 AM"  # the comma inside the field
        assert rows[-1].collected_at == "6/29/26 12:00 AM"

    def test_an_em_dash_is_absence_not_a_value(self):
        rows, _ = parse_ard_export(FIXTURE)
        assert rows[0].cpu_speed == ""       # Apple Silicon reports no clock speed
        assert rows[1].cpu_speed == "3.5 GHz"

    def test_the_provenance_header_the_project_writes_is_skipped(self, tmp_path):
        # docs/evidence/*.txt carries a "#" provenance block above the export, so the
        # parser must read the artifact in the repository as-is, not a stripped copy.
        captured = tmp_path / "captured.txt"
        captured.write_text("# exported 2026-09-13 18:37 from ARD 3.10\n# 44 columns, "
                            "16 rows, no UUID column\n\n" + FIXTURE.read_text())
        rows, export_date = parse_ard_export(captured)
        # ...and the header's own export date is what the report carries, not the
        # newest per-row collection date that follows it.
        assert len(rows) == 6 and export_date == "2026-09-13 18:37"

    def test_the_export_date_is_the_export_s_own_date_not_the_newest_collection(self, tmp_path):
        # The header records when the report was taken; "Date Collected" is per machine
        # and can be months older, so it cannot stand in for the export date.
        captured = tmp_path / "captured.txt"
        captured.write_text("# Identity source for ticket 04, exported 2026-09-13 18:37\n\n"
                            + FIXTURE.read_text())
        _, export_date = parse_ard_export(captured)
        assert export_date == "2026-09-13 18:37"
        assert export_date != EXPORT_DATE

    def test_a_row_that_does_not_match_the_header_is_refused(self, tmp_path):
        broken = tmp_path / "broken.txt"
        broken.write_text(FIXTURE.read_text().splitlines()[0] + "\nnot, enough\n")
        with pytest.raises(ValueError, match="fields, header has"):
            parse_ard_export(broken)


class TestArchitectureInference:
    def test_the_report_can_speak_for_some_models(self):
        rows, _ = parse_ard_export(FIXTURE)
        by_name = {r.computer: r for r in rows}
        assert infer_architecture(by_name["202 TOC M4 Max"])[0] == "arm64"
        assert infer_architecture(by_name["201 Bay 01 Mac Pro (63)"])[0] == "x86_64"
        assert infer_architecture(by_name["303B iMac"])[0] == "x86_64"
        assert infer_architecture(by_name["303A Mac Mini M4 Pro"])[0] == "arm64"

    def test_an_intel_mac_mini_is_not_called_arm64(self):
        # Both live in this fleet: a 2018 Intel mini (GHz reported) and an M4 mini.
        rows, _ = parse_ard_export(FIXTURE)
        sixto = next(r for r in rows if r.unix_hostname == "Sixto-5")
        assert sixto.cpu_speed == "3.6 GHz"
        assert infer_architecture(sixto) == ("x86_64", "inferred-from-report")

    def test_a_model_the_report_cannot_place_stays_unknown(self):
        record = ArdRecord(computer="Mystery Mac", unix_hostname="mystery", serial="X",
                           model="MacBook Air", os_version="", primary_ip="", primary_mac="",
                           wifi_mac="", cpu_speed="", collected_at="")
        assert infer_architecture(record) == (None, "unknown")


class TestManifestReconciliation:
    def test_exact_match_takes_its_role_from_the_manifest(self, tmp_path):
        rep = report(tmp_path)
        matched = row(rep, "202-TOC-M4-Max")
        assert matched.manifest == "202-TOC-M4-Max"
        assert matched.role_from_manifest == "toc"
        assert matched.munki_name == "202-TOC-M4-Max"

    def test_ards_numeric_suffix_still_finds_the_manifest(self, tmp_path):
        rep = report(tmp_path)
        matched = row(rep, "201-Bay-01-Mac-Pro-111")
        assert matched.manifest == "201-Bay-01-Mac-Pro"
        assert matched.role_from_manifest == "sound"
        assert "201-Bay-01-Mac-Pro-111" in [f.subject for f in kinds(rep, "name-difference")]

    def test_a_name_with_a_space_matches_the_hyphenated_hostname(self, tmp_path):
        rep = report(tmp_path)
        matched = row(rep, "303B-iMac")
        assert matched.manifest == "303B iMac"
        assert matched.role_from_manifest == "interns-temporary"
        assert "303B-iMac" in [f.subject for f in kinds(rep, "name-difference")]

    def test_a_machine_with_no_manifest_is_reported_not_hidden(self, tmp_path):
        rep = report(tmp_path)
        assert set(rep.unmanaged_machines) == {
            "303A-Mac-Mini-M4-Pro", "Sixto-5", "303D-Mac-Studio-M2"}
        unmatched = row(rep, "303A-Mac-Mini-M4-Pro")
        assert unmatched.manifest is None and unmatched.role_from_manifest is None
        # munki_name is the manifest name or nothing: the ARD UNIX hostname is not a
        # Munki HostName, so promoting it here would assert an equivalence nobody checked.
        assert unmatched.munki_name is None
        assert unmatched.unix_hostname == "303A-Mac-Mini-M4-Pro"  # still addressable
        assert {f.subject for f in kinds(rep, "machine-without-manifest")} == set(
            rep.unmanaged_machines)  # both directions agree, order is not a contract

    def test_a_manifest_with_no_machine_is_reported_in_the_other_direction(self, tmp_path):
        rep = report(tmp_path)
        assert set(rep.orphan_manifests) == {"202B-Mac-Studio", "201-Bay-03-M1-Ultra"}
        assert {f.subject for f in kinds(rep, "manifest-without-machine")} == \
            {"202B-Mac-Studio", "201-Bay-03-M1-Ultra"}

    def test_a_manifest_naming_no_role_group_is_reported_as_unassigned(self, tmp_path):
        # The fixture's unassigned manifest has no machine row of its own, so the
        # machine-level finding is exercised here with a machine that does exist.
        metadata = fake_metadata_tree(tmp_path / "metadata")
        write_manifest(metadata, "orphan-mini", ["all"], "Orphan mini")  # no role group
        manifests, _ = load_manifests(metadata)
        machine = ArdRecord(computer="Orphan mini", unix_hostname="orphan-mini", serial="S1",
                            model="Mac mini", os_version="", primary_ip="", primary_mac="",
                            wifi_mac="", cpu_speed="3.2 GHz", collected_at="9/13/26 12:00 AM")
        rep = build_report([machine], manifests, source="fixture", export_date=EXPORT_DATE)
        assert rep.unassigned_roles == ("201-Bay-03-M1-Ultra", "orphan-mini")
        # only the unassigned manifest that has a machine produces a machine finding
        assert [f.subject for f in kinds(rep, "role-unassigned")] == ["orphan-mini"]

    def test_a_machine_with_no_manifest_is_not_also_called_unassigned(self, tmp_path):
        # One defect, one finding: no manifest and an unassigned manifest are different.
        rep = report(tmp_path)
        unassigned = {f.subject for f in kinds(rep, "role-unassigned")}
        assert "303A-Mac-Mini-M4-Pro" not in unassigned
        assert "Sixto-5" not in unassigned

    def test_a_machine_known_to_exist_but_absent_needs_a_record(self, tmp_path):
        rep = report(tmp_path, known_absent=("Cyrils-Mac-mini:Cyril's Mac mini is a fleet member "
                                             "and has no row in the export"))
        assert "Cyrils-Mac-mini" not in [r.unix_hostname for r in rep.rows]
        needs = kinds(rep, "needs-record")
        assert len(needs) == 1 and needs[0].subject == "Cyrils-Mac-mini"
        assert len(rep.known_absent) == 1
        assert rep.known_absent[0].name == "Cyrils-Mac-mini"
        assert rep.known_absent[0].serial is None  # no probe was supplied for it

    def test_a_known_absent_machine_carries_its_serial_when_a_probe_exists(self, tmp_path):
        # Ticket 05 targets machines by serial, so the hand-off must not be prose.
        rep = report(tmp_path,
                     known_absent=("Cyrils-Mac-mini:Cyril's Mac mini, absent from the export",),
                     probes=[ProbeRecord(serial="RWJ57V9PW4",
                                         hardware_uuid="B30D55C8-679C-56E2-9654-16CBFD4A905D",
                                         architecture="arm64", hostname="Cyrils-Mac-mini",
                                         model_identifier="Mac16,10", os_version="26.6.2")])
        entry = rep.known_absent[0]
        assert entry.serial == "RWJ57V9PW4"
        assert entry.probe.hardware_uuid == "B30D55C8-679C-56E2-9654-16CBFD4A905D"
        payload = json.loads(report_to_json(rep))["known_absent"][0]
        assert payload["serial"] == "RWJ57V9PW4" and payload["model_identifier"] == "Mac16,10"

    def test_a_probe_with_no_row_is_reported_without_being_declared(self, tmp_path):
        # A machine that answered a probe but has no export row is evidence, not a guess.
        rep = report(tmp_path, probes=[ProbeRecord(serial="ZZZ", hostname="Sixto",
                                                   architecture="x86_64")])
        absent = {entry.name for entry in rep.known_absent}
        assert "Sixto" in absent
        assert len(kinds(rep, "needs-record")) == 1


class TestHardwareUuidProvenance:
    def test_a_probe_value_wins_and_is_labelled_as_probed(self, tmp_path):
        rep = report(tmp_path, probes=[ProbeRecord(
            serial="RW3HL9FL4M", hardware_uuid="B393E619-D093-5769-A19A-7C2670C32B49",
            architecture="arm64", hostname="202-TOC-M4-Max")])
        matched = row(rep, "202-TOC-M4-Max")
        assert matched.hardware_uuid == "B393E619-D093-5769-A19A-7C2670C32B49"
        assert matched.hardware_uuid_source == "probe"
        assert matched.architecture_source == "probe"
        # the other machines in the fixture still have no authoritative UUID
        assert matched.serial not in [f.subject for f in kinds(rep, "uuid-unavailable")]

    def test_the_operational_projection_is_carried_but_called_unverified(self, tmp_path):
        rep = report(tmp_path, bays=[BaysRecord(name="202 TOC M4 Max", hostname="202 TOC M4 Max",
                                                lan_ip_address="192.168.88.182",
                                                hardware_uuid="B393E619-D093-5769-A19A-7C2670C32B49")])
        matched = row(rep, "202-TOC-M4-Max")
        # ADR 0004: the projection is never the source, so it cannot occupy the
        # authoritative field. A consumer reading hardware_uuid alone sees nothing.
        assert matched.hardware_uuid is None
        assert matched.hardware_uuid_source == "unavailable"
        assert matched.hardware_uuid_candidate == "B393E619-D093-5769-A19A-7C2670C32B49"
        assert matched.hardware_uuid_candidate_source == \
            "bays-projection-unverified:hardware_uuid"
        assert len(kinds(rep, "uuid-unverified")) == 1
        assert matched.serial not in [f.subject for f in kinds(rep, "uuid-unavailable")]

    def test_a_probe_resolves_the_candidate_instead_of_being_overwritten_by_it(self, tmp_path):
        rep = report(tmp_path,
                     bays=[BaysRecord(name="202 TOC M4 Max", hostname="202 TOC M4 Max",
                                      hardware_uuid="PROJECTION")],
                     probes=[ProbeRecord(serial="RW3HL9FL4M", hardware_uuid="REAL")])
        matched = row(rep, "202-TOC-M4-Max")
        assert matched.hardware_uuid == "REAL" and matched.hardware_uuid_source == "probe"
        assert matched.hardware_uuid_candidate is None

    def test_no_source_means_no_value_and_a_finding(self, tmp_path):
        rep = report(tmp_path)
        unmatched = row(rep, "303D-Mac-Studio-M2")
        assert unmatched.hardware_uuid is None
        assert unmatched.hardware_uuid_source == "unavailable"
        assert len(kinds(rep, "uuid-unavailable")) == 6  # every machine in the fixture
        assert all("probe" in f.proposed for f in kinds(rep, "uuid-unavailable"))


class TestProjectionReconciliation:
    def test_an_address_difference_is_reported_not_applied(self, tmp_path):
        rep = report(tmp_path, bays=[BaysRecord(name="Bay 01 Mac Pro",
                                                hostname="201 Bay 01 Mac Pro",
                                                lan_ip_address="192.168.88.99")])
        differences = kinds(rep, "bays-difference")
        assert len(differences) == 1
        assert "192.168.88.99" in differences[0].detail
        assert "192.168.88.171" in differences[0].detail
        assert row(rep, "201-Bay-01-Mac-Pro-111").primary_ip == "192.168.88.171"  # untouched

    def test_a_machine_absent_from_the_projection_is_reported(self, tmp_path):
        rep = report(tmp_path, bays=[BaysRecord(name="202 TOC M4 Max", hostname="202 TOC M4 Max")])
        missing = kinds(rep, "bays-missing")
        assert {f.subject for f in missing} == {
            "201-Bay-01-Mac-Pro-111", "303B-iMac", "303A-Mac-Mini-M4-Pro", "Sixto-5",
            "303D-Mac-Studio-M2"}
        assert all("Bays records in Notion" in f.proposed for f in missing)


class TestTheSourceDateIsCarriedNotJudged:
    """Staleness *exposure* is ticket 05's. This ticket carries each row's own
    collection date, which is identity provenance: when the source said so."""

    def test_every_row_carries_the_date_it_was_collected(self, tmp_path):
        rep = report(tmp_path)
        assert row(rep, "303D-Mac-Studio-M2").collected_at == "6/29/26 12:00 AM"
        assert row(rep, "202-TOC-M4-Max").collected_at == "9/13/26 12:00 AM"
        assert rep.export_date == EXPORT_DATE

    def test_no_staleness_verdict_is_recorded_here(self, tmp_path):
        rep = report(tmp_path)
        assert not kinds(rep, "stale-collection")
        assert row(rep, "303D-Mac-Studio-M2").serial == "PKXTGR769Q"


class TestSerialisationAndCli:
    def test_the_report_serialises_with_provenance_intact(self, tmp_path):
        rep = report(tmp_path)
        payload = json.loads(report_to_json(rep))
        assert payload["schema_version"] == 1
        assert payload["identity_source"] == str(FIXTURE)
        assert payload["export_date"] == EXPORT_DATE
        assert len(payload["machines"]) == 6
        assert all({"serial", "munki_name", "architecture_source", "hardware_uuid_source",
                    "hardware_uuid_candidate_source"} <= set(m) for m in payload["machines"])
        assert {f["kind"] for f in payload["findings"]} >= {
            "uuid-unavailable", "machine-without-manifest", "manifest-without-machine",
            "name-difference", "bays-missing"}
        assert payload["orphan_manifests"] and payload["unmanaged_machines"]

    def test_the_same_inputs_produce_the_same_bytes(self, tmp_path):
        assert report_to_json(report(tmp_path)) == report_to_json(report(tmp_path))

    def test_the_cli_writes_the_file_ticket_05_reads(self, tmp_path, capsys):
        metadata = fake_metadata_tree(tmp_path / "metadata")
        probes = tmp_path / "probes.json"
        probes.write_text(json.dumps({"machines": [
            {"serial": "RW3HL9FL4M", "hardware_uuid": "B393E619-D093-5769-A19A-7C2670C32B49",
             "architecture": "arm64", "hostname": "202-TOC-M4-Max"}]}))
        bays = tmp_path / "bays.json"
        bays.write_text(json.dumps([{"name": "202 TOC M4 Max", "hostname": "202 TOC M4 Max",
                                     "lan_ip_address": "192.168.88.182",
                                     "hardware_uuid": "B393E619-D093-5769-A19A-7C2670C32B49"}]))
        out = tmp_path / "machines.json"

        code = main(["--ard-export", str(FIXTURE), "--metadata-root", str(metadata),
                     "--probes", str(probes), "--bays", str(bays),
                     "--known-absent", "Cyrils-Mac-mini:local probe, serial RWJ57V9PW4",
                     "--out", str(out), "--summary"])

        assert code == 0
        printed = capsys.readouterr().out
        assert "machines=6" in printed and "finding uuid-unavailable" in printed
        payload = json.loads(out.read_text())
        assert len(payload["machines"]) == 6
        assert payload["known_absent"][0]["name"] == "Cyrils-Mac-mini"
        assert "serial RWJ57V9PW4" in payload["known_absent"][0]["detail"]

    def test_a_manifest_that_is_not_a_machine_is_named_not_hardcoded(self, tmp_path, capsys):
        # A manifest added to the tree for another purpose (a future test client, a
        # staging manifest) must not be reported as a machine nothing answers to.
        metadata = fake_metadata_tree(tmp_path / "metadata")
        write_manifest(metadata, "t6-staging-client", ["all"], "T6 staging client")
        out = tmp_path / "m.json"

        main(["--ard-export", str(FIXTURE), "--metadata-root", str(metadata),
              "--site-manifest", "t6-staging-client", "--out", str(out), "--summary"])
        payload = json.loads(out.read_text())
        assert "t6-staging-client" not in payload["machines"]
        assert "t6-staging-client" not in payload["orphan_manifests"]
        assert "t6-manifests" not in capsys.readouterr().out  # summary still prints

    def test_loaders_accept_the_shapes_the_probe_and_the_database_produce(self, tmp_path):
        probes = tmp_path / "p.json"
        probes.write_text(json.dumps([{"serial": "S1", "hardware_uuid": "U"}]))
        bays = tmp_path / "b.json"
        bays.write_text(json.dumps({"bays": [{"name": "n", "hostname": "h"}]}))
        assert load_bays(bays)[0].hostname == "h"
        from munki_fleet.identity import load_probes
        assert load_probes(probes)[0].hardware_uuid == "U"


class TestRecordedRoleMatrix:
    """The matrix Cyril filled in (docs/role-matrix.csv, 2026-09-13).

    Until this existed, a machine's role was the role group its own manifest named —
    derived from the same tree it would be checked against, so a manifest naming the
    wrong role group was invisible. Now the recorded matrix is the outside check.
    """

    def matrix(self, tmp_path, body):
        path = tmp_path / "role-matrix.csv"
        path.write_text("machine,serial,unix_hostname,munki_short_hostname,role_group,"
                        "confirmed_by,confirmed_on,notes\n" + body)
        return path

    def test_it_reads_the_recorded_roles(self, tmp_path):
        path = self.matrix(tmp_path,
                           '202 TOC M4 Max,RW3HL9FL4M,202-TOC-M4-Max,202-TOC-M4-Max,toc,cyril,'
                           '2026-09-13,\n')
        assert load_role_matrix(path) == {"202-TOC-M4-Max": "toc"}

    def test_an_unanswered_row_makes_no_claim(self, tmp_path):
        # A row with no role is a question, not a decision: it cannot be checked against.
        path = self.matrix(tmp_path,
                           'A,X,unix-a,a,,cyril,2026-09-13,\n'
                           'B,Y,unix-b,b,warroom,cyril,2026-09-13,\n')
        assert load_role_matrix(path) == {"b": "warroom"}

    def test_a_role_group_that_is_not_one_of_the_nine_is_refused(self, tmp_path):
        path = self.matrix(tmp_path, 'A,X,u,a,colourist,cyril,2026-09-13,\n')
        with pytest.raises(ValueError, match="not one of the nine"):
            load_role_matrix(path)

    def test_a_role_with_no_machine_name_is_refused(self, tmp_path):
        # A role attached to nothing is how a matrix row gets silently ignored.
        path = self.matrix(tmp_path, 'A,X,u,,warroom,cyril,2026-09-13,\n')
        with pytest.raises(ValueError, match="no Munki short hostname"):
            load_role_matrix(path)

    def test_a_manifest_that_disagrees_with_the_matrix_is_a_finding(self, tmp_path):
        path = self.matrix(tmp_path, '202 TOC M4 Max,RW3HL9FL4M,202-TOC-M4-Max,202-TOC-M4-Max,'
                                      'warroom,cyril,2026-09-13,\n')
        rep = report(tmp_path, role_matrix=load_role_matrix(path))
        mismatches = kinds(rep, "role-mismatch")
        assert [f.subject for f in mismatches] == ["202-TOC-M4-Max"]
        assert "toc" in mismatches[0].detail and "warroom" in mismatches[0].detail
        matched = row(rep, "202-TOC-M4-Max")
        assert matched.role_from_manifest == "toc"   # the manifest is untouched
        assert matched.role_recorded == "warroom"    # the matrix is what it disagreed with

    def test_the_matrix_is_folded_the_way_every_other_source_is(self, tmp_path):
        # "303B iMac" in the manifest, "303B-iMac" as the UNIX hostname: same rule.
        path = self.matrix(tmp_path, 'A,X,303B-iMac,303B iMac,interns-temporary,cyril,'
                                      '2026-09-13,\n')
        rep = report(tmp_path, role_matrix=load_role_matrix(path))
        matched = row(rep, "303B-iMac")
        assert matched.role_recorded == "interns-temporary"
        assert not kinds(rep, "role-mismatch")   # the manifest agrees
        assert matched.role_from_manifest == "interns-temporary"

    def test_a_machine_the_matrix_places_but_has_no_manifest_says_so(self, tmp_path):
        path = self.matrix(tmp_path, '303A,H,303A-Mac-Mini-M4-Pro,303A-Mac-Mini-M4-Pro,'
                                      'client-facing,cyril,2026-09-13,\n')
        rep = report(tmp_path, role_matrix=load_role_matrix(path))
        finding = next(f for f in kinds(rep, "machine-without-manifest")
                       if f.subject == "303A-Mac-Mini-M4-Pro")
        assert "client-facing" in finding.detail

    def test_a_matrix_row_matching_no_known_machine_is_reported(self, tmp_path):
        path = self.matrix(tmp_path, 'Ghost,,,ghost-mac,online,cyril,2026-09-13,\n')
        rep = report(tmp_path, role_matrix=load_role_matrix(path))
        unknown = kinds(rep, "role-matrix-unknown-machine")
        assert [f.subject for f in unknown] == ["ghost-mac"]

    def test_a_known_absent_machine_carries_its_recorded_role(self, tmp_path):
        path = self.matrix(tmp_path, "Cyril's Mac mini,RWJ57V9PW4,Cyrils-Mac-mini,Cyrils-Mac-mini,"
                                      "production,cyril,2026-09-13,\n")
        rep = report(tmp_path, known_absent=("Cyrils-Mac-mini:Cyril's Mac mini",),
                     role_matrix=load_role_matrix(path))
        assert rep.known_absent[0].role_group_recorded == "production"
        payload = json.loads(report_to_json(rep))["known_absent"][0]
        assert payload["role_group_recorded"] == "production"

    def test_the_matrix_settles_an_orphan_manifest_the_export_could_not(self, tmp_path):
        # A role recorded for a name with no machine row means the Mac exists: the finding
        # says what it lacks (a record), not that it might be dead, and it is not reported
        # twice as an unknown matrix row.
        path = self.matrix(tmp_path, '202B Mac Studio,,,202B-Mac-Studio,warroom,cyril,'
                                      '2026-09-13,\n')
        rep = report(tmp_path, role_matrix=load_role_matrix(path))
        orphan = next(f for f in kinds(rep, "manifest-without-machine")
                      if f.subject == "202B-Mac-Studio")
        assert "the Mac exists" in orphan.detail and "warroom" in orphan.detail
        assert not kinds(rep, "role-matrix-unknown-machine")

    def test_without_a_matrix_nothing_changes(self, tmp_path):
        # The tool still works with no matrix: no claim, no finding.
        rep = report(tmp_path)
        assert not kinds(rep, "role-mismatch")
        assert not kinds(rep, "role-matrix-unknown-machine")
        assert row(rep, "202-TOC-M4-Max").role_recorded is None


class TestNameNormalisation:
    @pytest.mark.parametrize("left,right", [
        ("202-TOC-M4-Max", "202 TOC M4 Max"),
        ("201-Bay-01-Mac-Pro-111", "201-Bay-01-Mac-Pro"),
        ("303B-iMac", "303B iMac"),
        ("202A-Mac-Mini-M4", "202a mac mini m4"),
    ])
    def test_pairs_that_must_fold_together(self, left, right):
        assert normalise_name(left) == normalise_name(right)

    def test_names_that_must_not_fold_together(self):
        assert normalise_name("202-Tim-M2-Max-9") != normalise_name("202-Jason-M2-Max")
