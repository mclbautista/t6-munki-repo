"""The declared SSH access path for each machine (ticket 01 of `fleet-ssh-access`).

The collector used to derive its transport from the inventory: `primary_ip`, handed straight to
`ssh`, which resolved the *local* account and produced
`cyrilbautista@192.168.88.182: Permission denied` for a fleet whose machines answer to another
account entirely. The address is where a machine was last seen; it is not a login.

So the access path is declared, in a non-secret file, and used **verbatim or refused**:

- A record names the machine (`name`, the Munki short hostname a manifest is named for), optionally
  pins the serial it expects that name to have, and gives the one `destination` to reach it — an ssh
  alias, `user@host`, or a bare host. The string is passed to `ssh` unchanged; nothing here composes
  `user@address`, and a destination containing `:` or whitespace is refused rather than assembled.
- A record is never a credential store. The destination grammar admits no password field, no key
  path and no port, because the alias or the local ssh config is where those belong.
- A machine with no record is `no-access-record`: its transport is undeclared, so the reading it
  produces is tagged with that fact and cannot pass as a verified-access observation.
- A record that is malformed, duplicated, or whose declared serial contradicts the machine's own
  serial **blocks** the probe. That is the whole point of the ticket: a defect in the declaration
  must not quietly fall back to the undeclared path, because a fallback that happens to work is how
  an unverified login becomes fleet state.

This module reads files and returns dataclasses. It opens no connection.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

ACCESS_SCHEMA_VERSION = 1

# The record's own vocabulary, so a caller matches on a name rather than on a string literal.
NO_ACCESS_MAP = "no-access-map"
NO_ACCESS_RECORD = "no-access-record"
RECORD_MALFORMED = "access-record-malformed"
RECORD_DUPLICATE = "access-record-duplicate"
RECORD_SERIAL_MISMATCH = "access-record-serial-mismatch"

RECORD_FIELDS = ("name", "destination", "serial", "note")
MAP_FIELDS = ("schema_version", "machines", "note")

# `[user@]host`, and nothing else. `:` (a password or a port), a space, a slash and a `%` are all
# refused here: a destination is a login, and a login with a secret in it does not belong in a file
# the repository tracks.
DESTINATION = re.compile(r"^(?P<user>[A-Za-z0-9._-]+@)?(?P<host>[A-Za-z0-9._-]+)$")


@dataclass(frozen=True)
class AccessDefect:
    """Something wrong with a machine's declared access, and whether it may still be probed."""

    kind: str
    detail: str
    blocks: bool

    def as_target_field(self) -> dict:
        """The same defect in the shape a target dict carries into the observation store.

        Converted here and nowhere else: the target dict is what lands in the append-only store, and
        the store holds JSON, so the dict is the defect's serialisable form rather than a second
        spelling of it that a later edit could let drift.
        """
        return {"kind": self.kind, "detail": self.detail, "blocks": self.blocks}


@dataclass(frozen=True)
class Resolution:
    """What a machine's access declaration gives: a destination, a defect, or both."""

    destination: Optional[str] = None
    defect: Optional[AccessDefect] = None


@dataclass(frozen=True)
class AccessRecord:
    name: str
    destination: str
    serial: Optional[str] = None
    note: Optional[str] = None


class AccessMapUnreadable(Exception):
    """The map was named explicitly and could not be used. Refusing beats reading around it."""


class AccessMap:
    """The declared access path per machine, loaded from a file and queried per target."""

    def __init__(self, records: Sequence[AccessRecord] = (), source: Optional[str] = None,
                 available: bool = True, reason: Optional[str] = None,
                 malformed: Sequence[Tuple[str, str]] = ()) -> None:
        self.records: List[AccessRecord] = list(records)
        self.source = source
        self.available = available
        self.reason = reason
        # (machine name, why its declaration is unusable). Keyed by name so `resolve` can block the
        # machine the record was about instead of dropping the defect on the floor.
        self.malformed: List[Tuple[str, str]] = list(malformed)

    @classmethod
    def load(cls, path: str) -> "AccessMap":
        """Read a map. A missing or unusable map is unavailable, with the reason kept verbatim.

        Two grades of error, deliberately different:

        - The file cannot be attributed to machines at all (unreadable, bad JSON, unknown fields, a
          row with no machine name) — the whole map is unavailable, because a declaration nobody can
          attribute is not a declaration. The caller refuses rather than reading around it.
        - A row names its machine but its contents are wrong — the map loads and that machine's
          access is **blocked**.
        """
        try:
            with open(path, encoding="utf-8") as fh:
                raw = fh.read()
        except OSError as exc:
            return cls(source=path, available=False, reason=f"could not read {path}: {exc}")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            return cls(source=path, available=False, reason=f"{path} is not valid JSON: {exc}")
        if not isinstance(payload, dict):
            return cls(source=path, available=False, reason=f"{path} is not a JSON object")
        unknown = sorted(set(payload) - set(MAP_FIELDS))
        if unknown:
            return cls(source=path, available=False,
                       reason=f"{path} has unknown top-level field(s): {', '.join(unknown)}")
        if payload.get("schema_version") != ACCESS_SCHEMA_VERSION:
            return cls(source=path, available=False,
                       reason=f"{path} declares schema_version "
                              f"{payload.get('schema_version')!r}, expected {ACCESS_SCHEMA_VERSION}")
        rows = payload.get("machines")
        if not isinstance(rows, list):
            return cls(source=path, available=False, reason=f"{path} has no 'machines' list")

        records: List[AccessRecord] = []
        malformed: List[Tuple[str, str]] = []
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                return cls(source=path, available=False,
                           reason=f"{path} machines[{index}] is not an object")
            name = row.get("name")
            if not isinstance(name, str) or not name.strip():
                return cls(source=path, available=False,
                           reason=f"{path} machines[{index}] names no machine")
            name = name.strip()
            problem = _record_problem(row)
            if problem:
                malformed.append((name, problem))
                continue
            serial = row.get("serial")
            records.append(AccessRecord(name=name, destination=row["destination"],
                                        serial=serial.strip() if isinstance(serial, str) else None,
                                        note=row.get("note")))
        return cls(records=records, source=path, malformed=malformed)

    def resolve(self, target: dict) -> Resolution:
        """The declared access for one target, or the defect that stands in its place."""
        if not self.available:
            return self.unavailable()
        name = target.get("host")
        broken = [reason for record_name, reason in self.malformed if record_name == name]
        if broken:
            return Resolution(None, AccessDefect(RECORD_MALFORMED, broken[0], blocks=True))
        matches = [record for record in self.records if record.name == name]
        if not matches:
            return Resolution(None, AccessDefect(
                NO_ACCESS_RECORD, f"no access record for {name!r}", blocks=False))
        if len(matches) > 1:
            return Resolution(None, AccessDefect(
                RECORD_DUPLICATE,
                f"{len(matches)} access records name {name!r}: the destination is ambiguous",
                blocks=True))
        record = matches[0]
        claimed = record.serial
        known = target.get("serial")
        if claimed and known and claimed != known:
            return Resolution(None, AccessDefect(
                RECORD_SERIAL_MISMATCH,
                f"the access record for {name!r} declares serial {claimed}, "
                f"the machine's own record says {known}",
                blocks=True))
        return Resolution(record.destination, None)

    def unavailable(self) -> Resolution:
        """Every machine is uncovered when there is no map, and the reason travels with each one."""
        return Resolution(None, AccessDefect(NO_ACCESS_MAP, self.reason or "no access map",
                                             blocks=False))


def _record_problem(row: dict) -> Optional[str]:
    """Why this row cannot be used, or None. The machine is named; only its contents are in doubt."""
    unknown = sorted(set(row) - set(RECORD_FIELDS))
    if unknown:
        return f"unknown field(s): {', '.join(unknown)}"
    destination = row.get("destination")
    if not isinstance(destination, str) or not destination.strip():
        return "no destination"
    destination = destination.strip()
    if not DESTINATION.match(destination):
        return (f"destination {destination!r} is not [user@]host — a port, a path, a password or a "
                f"space in it is refused rather than assembled")
    serial = row.get("serial")
    if serial is not None and (not isinstance(serial, str) or not serial.strip()):
        return "serial is empty"
    note = row.get("note")
    if note is not None and not isinstance(note, str):
        return "note is not text"
    return None


def resolve_targets(targets: Sequence[dict], access_map: AccessMap,
                    skip: Optional[Callable[[dict], bool]] = None
                    ) -> Tuple[List[dict], List[AccessDefect]]:
    """Every target carrying its declared destination, plus the defects found while resolving.

    A blocked target **keeps its place** in the list rather than being dropped: the run still has to
    account for the machine (ADR 0004 — a run records its own completeness), it just must not be
    contacted. The defect travels on the target so whoever runs the probe does not have to re-derive
    why the machine was skipped.

    `skip` names the targets that travel by another transport and therefore need no access record —
    the collector's own machine, probed locally. They pass through untouched and raise no defect,
    because a record about an ssh path does not apply to a probe that never opens one.
    """
    resolved: List[dict] = []
    defects: List[AccessDefect] = []
    for target in targets:
        if skip is not None and skip(target):
            resolved.append(dict(target))
            continue
        resolution = access_map.resolve(target)
        carrying = dict(target)
        if resolution.destination:
            carrying["ssh_destination"] = resolution.destination
        if resolution.defect:
            defects.append(resolution.defect)
            carrying["access_defect"] = resolution.defect.as_target_field()
        resolved.append(carrying)
    return resolved, defects
