"""Ticket 04: one authoritative inventory of which Mac is which.

Three sources, each with its own authority, and they do not agree:

* **Identity** comes from the Apple Remote Desktop *System Overview Report* (machine
  name, serial, model, OS build, addresses, hardware facts). It is the source of
  record per ADR 0004. It carries **no hardware UUID and no architecture column**.
* **State of record** for a machine's hardware UUID and architecture is a *probe of
  the machine itself* (ticket 05's probe). Where a probe exists, it wins.
* **The T6 operational database's `bays` records are a projection** (ADR 0004), read
  here only to be *reconciled*: differences are reported, never applied.
* Because of those two rules, a projection UUID **never occupies the authoritative
  field**. `hardware_uuid` is filled only by a probe and is otherwise null, so a
  consumer that reads `hardware_uuid` alone cannot pick up the forbidden source. A
  projection value travels in `hardware_uuid_candidate`, named with the column it came
  from, so the probe that disagrees with it becomes a finding rather than an overwrite.

Two traps worth naming, because both are easy to fall into:

1. **ARD's own computer UUID is not the hardware UUID.** The ARD export task keeps a
   per-computer record with a UUID, a MAC and an address; checked on 2026-09-13, the
   UUID for the Mac Mini admin workstation is `0B1919E6-1503-49DC-A573-DA2DA06A78AE`
   while the machine's real hardware UUID is
   `CB3D4672-22E7-573F-9CD2-5F1D2A6BEC0F`. Different things; that file is not read.
2. **A manifest existing is not a machine existing**, and the converse. Both
   directions are checked and both are reported (the ticket's own note).

`munki_name` is the **manifest** name and nothing else: when no manifest matches, it is
null rather than the ARD UNIX hostname, because Munki resolves a manifest from
`HostName`/`LocalHostName` and the export carries neither (gap 3 in the ticket).

No live machine and no live NAS is touched: the export, the manifest tree, the probe
results and the projection are all *files*. Anything that requires a machine is an
input, not a call.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import plistlib
import re
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Sequence, Tuple

__all__ = [
    "ArdRecord",
    "BaysRecord",
    "ProbeRecord",
    "MachineRow",
    "KnownAbsentMachine",
    "IdentityReport",
    "parse_ard_export",
    "load_manifests",
    "normalise_name",
    "infer_architecture",
    "build_report",
    "report_to_json",
    "main",
]

SCHEMA_VERSION = 1

# The nine role groups the spec defines. A machine manifest that includes none of
# them is unassigned; one that includes more than one is reported rather than guessed.
ROLE_GROUPS = (
    "toc", "sound", "production", "online", "dit", "warroom",
    "coordination-admin", "client-facing", "interns-temporary",
)

# Site-level manifests, not machines: they exist so the chain resolves.
SITE_MANIFESTS = ("all", "site_default")

# Manifests that are not machines, per the spec's own count: "28 manifest files
# including 16 machine manifests" — the other twelve are the nine role groups, the two
# site manifests and the test-client manifest. A machine manifest that names no role
# group is unassigned, which is a finding, not a reason to drop it from the tree.
NON_MACHINE_MANIFESTS = tuple(SITE_MANIFESTS) + ROLE_GROUPS + ("t6-test-client",)

_ARD_SUFFIX = re.compile(r"-\d{2,4}$")


@dataclass(frozen=True)
class ArdRecord:
    """One row of the Apple Remote Desktop System Overview Report."""

    computer: str
    unix_hostname: str
    serial: str
    model: str
    os_version: str
    primary_ip: str
    primary_mac: str
    wifi_mac: str
    cpu_speed: str
    collected_at: str  # MM/DD/YY as the report writes it


@dataclass(frozen=True)
class ProbeRecord:
    """What a machine said about itself (ticket 05's probe, or a one-off probe)."""

    serial: str
    hardware_uuid: Optional[str] = None
    architecture: Optional[str] = None
    hostname: Optional[str] = None
    model_identifier: Optional[str] = None
    os_version: Optional[str] = None


@dataclass(frozen=True)
class BaysRecord:
    """A `bays` row from the operational database: a projection, never a source."""

    name: str
    hostname: Optional[str] = None
    lan_ip_address: Optional[str] = None
    hardware_uuid: Optional[str] = None
    device_uuid: Optional[str] = None
    notion_url: Optional[str] = None

    def candidate_uuid(self):
        """The projection's UUID and the column it came from, if it carries one.

        Which column matters: on some Macs `hardware_uuid` and `device_uuid` hold the
        same value and on others they do not, so a probe mismatch has to say what it
        disagreed with.
        """
        if self.hardware_uuid:
            return self.hardware_uuid, "hardware_uuid"
        if self.device_uuid:
            return self.device_uuid, "device_uuid"
        return None, None


@dataclass(frozen=True)
class MachineRow:
    """One machine in the inventory. Every field that can come from more than one
    source carries which source it came from, and the authoritative UUID field is
    filled by a probe only: a projection value is a *candidate* in its own field."""

    serial: str
    computer_name: str
    unix_hostname: str
    munki_name: Optional[str]  # the manifest name, or null: never the ARD hostname
    manifest: Optional[str]
    role: Optional[str]
    model: str
    architecture: Optional[str]
    architecture_source: str
    hardware_uuid: Optional[str]
    hardware_uuid_source: str
    hardware_uuid_candidate: Optional[str]
    hardware_uuid_candidate_source: str
    os_version: str
    primary_ip: str
    primary_mac: str
    wifi_mac: str
    collected_at: str

    def to_json(self) -> dict:
        return {
            "serial": self.serial,
            "computer_name": self.computer_name,
            "unix_hostname": self.unix_hostname,
            "munki_name": self.munki_name,
            "manifest": self.manifest,
            "role": self.role,
            "model": self.model,
            "architecture": self.architecture,
            "architecture_source": self.architecture_source,
            "hardware_uuid": self.hardware_uuid,
            "hardware_uuid_source": self.hardware_uuid_source,
            "hardware_uuid_candidate": self.hardware_uuid_candidate,
            "hardware_uuid_candidate_source": self.hardware_uuid_candidate_source,
            "os_version": self.os_version,
            "primary_ip": self.primary_ip,
            "primary_mac": self.primary_mac,
            "wifi_mac": self.wifi_mac,
            "collected_at": self.collected_at,
        }


@dataclass(frozen=True)
class KnownAbsentMachine:
    """A machine that exists but has no row in the export.

    Structured, not prose: ticket 05 builds a serial-keyed target list, so the serial
    and any probed facts have to be fields rather than a sentence to parse.
    """

    name: str
    detail: str
    probe: Optional[ProbeRecord] = None

    @property
    def serial(self) -> Optional[str]:
        """The machine's serial, when a probe supplied it: it is the target key."""
        return self.probe.serial if self.probe else None

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "detail": self.detail,
            "serial": self.probe.serial if self.probe else None,
            "hardware_uuid": self.probe.hardware_uuid if self.probe else None,
            "architecture": self.probe.architecture if self.probe else None,
            "probe_hostname": self.probe.hostname if self.probe else None,
            "model_identifier": self.probe.model_identifier if self.probe else None,
            "os_version": self.probe.os_version if self.probe else None,
        }


@dataclass(frozen=True)
class Finding:
    """A mismatch, with the correction proposed and never applied."""

    kind: str
    subject: str
    detail: str
    proposed: str


@dataclass(frozen=True)
class IdentityReport:
    source: str
    export_date: str
    rows: Tuple[MachineRow, ...] = ()
    findings: Tuple[Finding, ...] = ()
    # Named for what they are, in one direction each: a manifest nothing answers to,
    # and a machine with nothing to resolve.
    orphan_manifests: Tuple[str, ...] = ()
    unmanaged_machines: Tuple[str, ...] = ()
    unassigned_roles: Tuple[str, ...] = ()
    known_absent: Tuple[KnownAbsentMachine, ...] = ()

    def to_json(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "identity_source": self.source,
            "export_date": self.export_date,
            "machines": [row.to_json() for row in self.rows],
            "findings": [
                {"kind": f.kind, "subject": f.subject, "detail": f.detail, "proposed": f.proposed}
                for f in self.findings
            ],
            "orphan_manifests": list(self.orphan_manifests),
            "unmanaged_machines": list(self.unmanaged_machines),
            "unassigned_roles": list(self.unassigned_roles),
            "known_absent": [entry.to_json() for entry in self.known_absent],
        }


_EXPORTED = re.compile(r"exported\s+(\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2})?)", re.IGNORECASE)


def _header_export_date(path: pathlib.Path) -> str:
    """The export's own date, taken from the provenance header the project writes.

    The newest "Date Collected" is *not* the export date: that column is when each
    machine was last contacted, and the report itself was exported at a single moment
    which its header records. Falling back to the newest collection is a last resort
    and is visible in the value it produces.
    """
    for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        if not line.startswith("#"):
            break
        found = _EXPORTED.search(line)
        if found:
            return found.group(1)
    return ""


def _ard_rows(path: pathlib.Path) -> List[dict]:
    """The report's rows as dicts, tolerating the one comma that isn't a separator.

    "Date Collected" holds a comma of its own ("9/13/26, 12:00 AM"), so a row splits
    into one field more than the header has and the last two rejoin.
    """
    text = pathlib.Path(path).read_text(encoding="utf-8")
    # The captured artifact carries the provenance header this project writes above
    # every export (source, export date, what the columns do not include), so comment
    # lines are skipped rather than being mistaken for the header row.
    lines = [line for line in text.splitlines() if line.strip() and not line.startswith("#")]
    if len(lines) < 2:
        raise ValueError("%s holds no ARD rows" % path)
    header = [column.strip() for column in lines[0].split(", ")]
    rows = []
    for line in lines[1:]:
        fields = line.split(", ")
        if len(fields) == len(header) + 1:
            # The last column ("Date Collected") holds a comma of its own, so the row
            # splits into one field too many; rejoin it rather than dropping the time.
            fields = fields[:len(header) - 1] + [", ".join(fields[len(header) - 1:])]
        if len(fields) != len(header):
            raise ValueError("row has %d fields, header has %d: %r"
                             % (len(fields), len(header), line[:80]))
        rows.append(dict(zip(header, fields)))
    return rows


def parse_ard_export(path) -> Tuple[List[ArdRecord], str]:
    """Parse the ARD System Overview Report. Returns (records, export date)."""
    path = pathlib.Path(path)
    records = []
    for row in _ard_rows(path):
        def get(column: str) -> str:
            value = (row.get(column) or "").strip()
            return "" if value in ("–", "-", "") else value
        records.append(
            ArdRecord(
                computer=get("Computer"),
                unix_hostname=get("UNIX Hostname"),
                serial=get("Serial Number"),
                model=get("Machine Model"),
                os_version=get("System Version"),
                primary_ip=get("Primary IP Address"),
                primary_mac=get("Primary Network Hardware Address"),
                wifi_mac=get("Wi-Fi Hardware Address"),
                cpu_speed=get("CPU Speed"),
                collected_at=get("Date Collected").replace(", ", " "),
            )
        )
    exported = _header_export_date(path)
    if not exported:
        # No header: fall back to the newest per-row collection date, which is the
        # closest the export itself comes to saying when it was taken.
        dates = sorted({r.collected_at for r in records})
        exported = dates[-1] if dates else ""
    return records, exported


def _first_match(candidates, exact: Dict[str, object], folded: Dict[str, object]):
    """The one matching rule: exact first, then folded, for every source.

    Manifests and the projection are matched the same way so neither can quietly
    become more permissive than the other. `candidates` is in the source's own
    spelling and order; the returned value is whatever the index holds.
    """
    for candidate in candidates:
        if candidate and candidate in exact:
            return exact[candidate]
    for candidate in candidates:
        if candidate:
            hit = folded.get(normalise_name(candidate))
            if hit:
                return hit
    return None


def load_manifests(metadata_root,
                   extra_non_machine: Sequence[str] = (),
                   ) -> Tuple[Dict[str, Optional[str]], Dict[str, List[str]]]:
    """Read the manifest tree.

    Returns (machine manifest -> role group, role group -> machine manifests). A
    machine manifest's role is the one role group it includes; a machine manifest
    that includes none is present with ``None`` so it is reported as unassigned.
    """
    manifests_dir = pathlib.Path(metadata_root) / "manifests"
    non_machine = tuple(NON_MACHINE_MANIFESTS) + tuple(extra_non_machine)
    machine_roles: Dict[str, Optional[str]] = {}
    by_role: Dict[str, List[str]] = {role: [] for role in ROLE_GROUPS}
    for path in sorted(manifests_dir.iterdir()):
        if path.name.startswith(".") or not path.is_file():
            continue
        try:
            data = plistlib.loads(path.read_bytes())
        except Exception as exc:  # a manifest that cannot be read is not a machine
            raise ValueError("manifest %s is not a readable plist (%s)" % (path.name, exc))
        name = path.name
        if name in non_machine:
            continue
        included = data.get("included_manifests") or []
        roles = [entry for entry in included if entry in ROLE_GROUPS]
        machine_roles[name] = roles[0] if len(roles) == 1 else None
        for role in roles:
            by_role[role].append(name)
    return machine_roles, by_role


def normalise_name(name: str) -> str:
    """A comparison key: case, spaces and ARD's numeric suffix are not identity.

    ARD appends a collision suffix to the UNIX hostname ("201-Bay-01-Mac-Pro-111"),
    and several machine names contain spaces where the manifest uses hyphens
    ("303B iMac" vs "303B-iMac"), so both are folded for matching only — the
    reported value is always the source's own spelling.
    """
    folded = name.strip().lower().replace(" ", "-").replace("_", "-")
    folded = re.sub(r"-+", "-", folded)
    return _ARD_SUFFIX.sub("", folded)


def infer_architecture(record: ArdRecord) -> Tuple[Optional[str], str]:
    """arm64 / x86_64 from the report alone, or None when the report cannot say.

    The report has no architecture column, and inventing one from the model name
    alone would be wrong for the Mac mini (an Intel 2018 and an M4 live in this
    fleet). The discriminator that *is* in the data: Apple Silicon rows leave "CPU
    Speed" empty while every Intel row reports a GHz figure. A probed machine
    overrides this (see `build_report`).
    """
    model = record.model
    if record.cpu_speed:
        return "x86_64", "inferred-from-report"
    if model in ("Mac Studio",):
        return "arm64", "inferred-from-report"
    if model in ("Mac Pro", "iMac"):
        return "x86_64", "inferred-from-report"
    if re.search(r"\bM[1-4]\b", record.computer):
        return "arm64", "inferred-from-report"
    return None, "unknown"


def build_report(
    ard_records: Sequence[ArdRecord],
    manifests: Dict[str, Optional[str]],
    *,
    probes: Sequence[ProbeRecord] = (),
    bays: Sequence[BaysRecord] = (),
    known_absent: Sequence[str] = (),
    source: str = "",
    export_date: str = "",
) -> IdentityReport:
    """Reconcile the three sources into rows plus findings. Nothing is applied."""
    if isinstance(known_absent, str):  # a single entry is a string, not a sequence of chars
        known_absent = (known_absent,)
    manifest_names = {name: name for name in manifests}
    manifest_folded = {normalise_name(name): name for name in manifests}
    bays_exact: Dict[str, BaysRecord] = {}
    bays_folded: Dict[str, BaysRecord] = {}
    for bays_row in bays:
        for value in (bays_row.hostname, bays_row.name):
            if value:
                bays_exact.setdefault(value, bays_row)
                bays_folded.setdefault(normalise_name(value), bays_row)
    probes_by_serial = {p.serial: p for p in probes if p.serial}

    rows: List[MachineRow] = []
    findings: List[Finding] = []
    matched_manifests = set()
    matched_serials = set()

    for record in ard_records:
        matched_serials.add(record.serial)
        manifest = _first_match((record.unix_hostname, record.computer),
                                manifest_names, manifest_folded)
        if manifest is not None:
            matched_manifests.add(manifest)
            if manifest != record.unix_hostname:
                findings.append(Finding(
                    kind="name-difference",
                    subject=record.unix_hostname,
                    detail="the inventory calls this machine %r while the manifest is %r"
                           % (record.unix_hostname, manifest),
                    proposed="reconcile the machine's Munki HostName with the manifest, or "
                             "rename the manifest; do not add a second manifest",
                ))
        role = manifests.get(manifest) if manifest else None

        probe = probes_by_serial.get(record.serial)
        bays_row = _first_match((record.unix_hostname, record.computer), bays_exact, bays_folded)

        architecture, architecture_source = infer_architecture(record)
        hardware_uuid: Optional[str] = None
        hardware_uuid_source = "unavailable"
        candidate: Optional[str] = None
        candidate_column: Optional[str] = None
        if probe is not None:
            if probe.architecture:
                architecture, architecture_source = probe.architecture, "probe"
            if probe.hardware_uuid:
                hardware_uuid, hardware_uuid_source = probe.hardware_uuid, "probe"

        if hardware_uuid is None:
            if bays_row is not None:
                candidate, candidate_column = bays_row.candidate_uuid()
            if candidate:
                findings.append(Finding(
                    kind="uuid-unverified",
                    subject=record.serial,
                    detail="no machine has reported its hardware UUID; %r is the operational "
                           "database's %s, which ADR 0004 calls a projection and never the "
                           "source" % (candidate, candidate_column),
                    proposed="confirm with the machine's own probe (ticket 05) and report any "
                             "difference rather than adopting this value; the authoritative "
                             "field stays empty until a machine says so",
                ))
            else:
                findings.append(Finding(
                    kind="uuid-unavailable",
                    subject=record.serial,
                    detail="the ARD export carries no hardware UUID column, no probe exists "
                           "for %s, and the projection has no UUID for it either"
                           % record.computer,
                    proposed="record it from the machine's own probe (ticket 05); identity for "
                             "delivery purposes keys on the serial, which is present",
                ))

        if manifest is not None and not role:
            # Only a manifest can be unassigned: a machine with no manifest at all is
            # reported once, as unmanaged, not twice.
            findings.append(Finding(
                kind="role-unassigned",
                subject=manifest,
                detail="the machine manifest names no role group, or names more than one, so "
                       "the machine inherits nothing role-specific",
                proposed="add exactly one role group to the machine manifest",
            ))

        if bays_row is None:
            findings.append(Finding(
                kind="bays-missing",
                subject=record.unix_hostname,
                detail="the operational database has no bays record matching this machine",
                proposed="add the machine to the Bays records in Notion (the projection is "
                         "downstream of the machine, not the other way round)",
            ))
        else:
            differences = []
            if bays_row.lan_ip_address and record.primary_ip \
                    and bays_row.lan_ip_address != record.primary_ip:
                differences.append("address %s in the projection vs %s collected"
                                   % (bays_row.lan_ip_address, record.primary_ip))
            if bays_row.name and normalise_name(bays_row.name) != normalise_name(record.computer):
                differences.append("named %r in the projection vs %r collected"
                                   % (bays_row.name, record.computer))
            if not bays_row.lan_ip_address:
                differences.append("no address in the projection")
            if differences:
                detail = "; ".join(differences)
                if bays_row.notion_url:
                    # Whoever corrects this has to find the record: name it.
                    detail += " (%s)" % bays_row.notion_url
                findings.append(Finding(
                    kind="bays-difference",
                    subject=record.unix_hostname,
                    detail=detail,
                    proposed="correct the Bays record in Notion; the projection is never "
                             "written back to",
                ))

        rows.append(MachineRow(
            serial=record.serial,
            computer_name=record.computer,
            unix_hostname=record.unix_hostname,
            munki_name=manifest,
            manifest=manifest,
            role=role,
            model=record.model,
            architecture=architecture,
            architecture_source=architecture_source,
            hardware_uuid=hardware_uuid,
            hardware_uuid_source=hardware_uuid_source,
            hardware_uuid_candidate=candidate,
            hardware_uuid_candidate_source=(
                "bays-projection-unverified:%s" % candidate_column if candidate else "none"),
            os_version=record.os_version,
            primary_ip=record.primary_ip,
            primary_mac=record.primary_mac,
            wifi_mac=record.wifi_mac,
            collected_at=record.collected_at,
        ))

    orphan_manifests = tuple(sorted(set(manifests) - matched_manifests))
    for name in orphan_manifests:
        findings.append(Finding(
            kind="manifest-without-machine",
            subject=name,
            detail="a machine manifest exists, but no machine in the export answers to it",
            proposed="confirm whether the machine still exists; if it does, it needs an "
                     "inventory record, and if it does not, retire the manifest",
        ))
    unmanaged_machines = tuple(sorted(row.unix_hostname for row in rows if row.manifest is None))
    for name in unmanaged_machines:
        findings.append(Finding(
            kind="machine-without-manifest",
            subject=name,
            detail="an inventoried machine has no machine manifest, so it resolves "
                   "site_default rather than its own configuration",
            proposed="add a machine manifest named for its Munki HostName and place it in "
                     "exactly one role group",
        ))
    unassigned = tuple(sorted(name for name, role in manifests.items() if role is None))

    # Machines with no row in the export. Declared by the caller, and enriched from any
    # probe for them: the probe is what supplies a serial, so ticket 05 can target them.
    absent: List[KnownAbsentMachine] = []
    leftover_probes = [p for serial, p in sorted(probes_by_serial.items())
                       if serial not in matched_serials]
    for entry in known_absent:
        head, _, tail = entry.partition(":")
        probe = None
        for candidate_probe in leftover_probes:
            if candidate_probe.hostname and \
                    normalise_name(candidate_probe.hostname) == normalise_name(head):
                probe = candidate_probe
                break
        absent.append(KnownAbsentMachine(name=head.strip(), detail=tail.strip(), probe=probe))
        findings.append(Finding(
            kind="needs-record",
            subject=head.strip(),
            detail=tail.strip() or "known to exist but absent from the engineering export",
            proposed="create an inventory record; this module will not invent one",
        ))
    declared = {normalise_name(entry.name) for entry in absent}
    for probe in leftover_probes:
        hostname = probe.hostname or probe.serial
        if normalise_name(hostname) in declared:
            continue
        absent.append(KnownAbsentMachine(
            name=hostname,
            detail="a probe exists for this machine (serial %s) but the export has no row "
                   "for it" % probe.serial,
            probe=probe,
        ))
        findings.append(Finding(
            kind="needs-record",
            subject=hostname,
            detail="probed as serial %s, absent from the engineering export" % probe.serial,
            proposed="create an inventory record; this module will not invent one",
        ))

    return IdentityReport(
        source=source,
        export_date=export_date,
        rows=tuple(sorted(rows, key=lambda row: row.unix_hostname)),
        findings=tuple(findings),
        orphan_manifests=orphan_manifests,
        unmanaged_machines=unmanaged_machines,
        unassigned_roles=unassigned,
        known_absent=tuple(absent),
    )


def report_to_json(report: IdentityReport) -> str:
    return json.dumps(report.to_json(), indent=2, sort_keys=True) + "\n"


def load_probes(path) -> List[ProbeRecord]:
    """Probe results as JSON: a list of objects, or {"machines": [...]}."""
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    entries = data["machines"] if isinstance(data, dict) else data
    return [
        ProbeRecord(
            serial=entry["serial"],
            hardware_uuid=entry.get("hardware_uuid"),
            architecture=entry.get("architecture"),
            hostname=entry.get("hostname"),
            model_identifier=entry.get("model_identifier"),
            os_version=entry.get("os_version"),
        )
        for entry in entries
    ]


def load_bays(path) -> List[BaysRecord]:
    """Bays rows as JSON (the operational database's projection), read-only."""
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else data.get("bays", [])
    return [
        BaysRecord(
            name=row.get("name") or "",
            hostname=row.get("hostname"),
            lan_ip_address=row.get("lan_ip_address"),
            hardware_uuid=row.get("hardware_uuid"),
            device_uuid=row.get("device_uuid"),
            notion_url=row.get("notion_url"),
        )
        for row in rows
    ]


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Write the inventory ticket 05 reads. Reads files only; touches no machine."""
    parser = argparse.ArgumentParser(
        prog="python3 -m munki_fleet.identity",
        description="Build the machine inventory from the ARD export, the manifest tree, "
                    "probe results and the operational projection.",
    )
    parser.add_argument("--ard-export", required=True, help="the System Overview Report file")
    parser.add_argument("--metadata-root", default=".", help="the metadata checkout root")
    parser.add_argument("--probes", default=None, help="probe results as JSON (optional)")
    parser.add_argument("--bays", default=None, help="bays rows as JSON (optional, read-only)")
    parser.add_argument("--site-manifest", action="append", default=[], metavar="NAME",
                        help="a manifest that is not a machine (repeatable); a manifest added "
                             "to the tree for another purpose is named here rather than "
                             "hardcoded into this module's list")
    parser.add_argument("--known-absent", action="append", default=[],
                        metavar="NAME:DETAIL",
                        help="a machine known to exist but absent from the export; repeatable")
    parser.add_argument("--out", default=None, help="write the inventory JSON here")
    parser.add_argument("--summary", action="store_true", help="print a human summary")
    args = parser.parse_args(argv)

    records, export_date = parse_ard_export(args.ard_export)
    manifests, by_role = load_manifests(args.metadata_root,
                                       extra_non_machine=args.site_manifest)
    report = build_report(
        records,
        manifests,
        probes=load_probes(args.probes) if args.probes else (),
        bays=load_bays(args.bays) if args.bays else (),
        known_absent=args.known_absent,
        source=str(args.ard_export),
        export_date=export_date,
    )

    if args.out:
        pathlib.Path(args.out).write_text(report_to_json(report), encoding="utf-8")
    if args.summary or not args.out:
        print("machines=%d manifests=%d export_date=%s"
              % (len(report.rows), len(manifests), report.export_date))
        print("  probed uuid %d | candidate uuid %d | no uuid %d"
              % (sum(1 for r in report.rows if r.hardware_uuid_source == "probe"),
                 sum(1 for r in report.rows if r.hardware_uuid_candidate),
                 sum(1 for r in report.rows if r.hardware_uuid is None
                     and not r.hardware_uuid_candidate)))
        print("  orphan manifests %d | unmanaged machines %d | unassigned %d | known absent %d"
              % (len(report.orphan_manifests), len(report.unmanaged_machines),
                 len(report.unassigned_roles), len(report.known_absent)))
        for role in sorted(by_role):
            if by_role[role]:
                print("  role %-19s %s" % (role, ", ".join(by_role[role])))
        for kind in sorted({f.kind for f in report.findings}):
            count = sum(1 for f in report.findings if f.kind == kind)
            print("  finding %-26s %d" % (kind, count))
        if args.out:
            print("wrote %s" % args.out)
    return 0


if __name__ == "__main__":  # pragma: no cover - thin process entry
    raise SystemExit(main())
