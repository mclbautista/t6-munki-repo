"""What is actionable, what a reader can check, and what stays silent (ticket 15).

The decision is **deterministic**, and the delivery is not the decider. This module answers one
question — *which conditions are actionable right now, and what would tell a reader that each one is
real* — and hands the resulting message to whatever transport the deployment uses. Kulit owns Telegram
delivery (ADR 0008's boundary list, and `CONTEXT.md`'s glossary); this module never talks to Telegram,
never talks to a bot, and holds no credentials.

Three rules are enforced in code rather than stated in prose:

- **Silence is the default.** No message is produced unless something is actionable. A healthy cycle
  hands over nothing at all — no summary, no "no alert" line, because that is the noise that makes an
  alert stop meaning anything. It does record the state (a condition's last-seen time, and a cleared
  condition forgetting itself), because the next cycle's decision rests on it.
- **Every condition carries a source.** `Condition` refuses to exist without at least one reference,
  so a claim nobody can check cannot be constructed, let alone sent.
- **An unobserved machine is not a compliant one.** `observation_conditions` emits a condition for a
  machine with no reading, an unreachable reading and a stale reading, and it derives no compliance
  claim from a stale reading: the reading's own manifest and rejections are not reported as current
  fact, only the fact that the reading is old.

Vocabulary, matching `CONTEXT.md`: a **condition** is one actionable fact; a **message** is one
rendered digest of every newly actionable condition (a first sight of seventeen conditions is one
message, not seventeen); a **receipt** is the transport's own record that a message was delivered;
the **alert state** is this module's durable record, so a condition that persists does not re-alert
every cycle and a condition that clears forgets itself.

Delivery is reported, never assumed: the transport writes a receipt into the outbox, the next run
consumes it, and a delivery that failed (or a message nobody acknowledged within its TTL) leaves the
condition **undelivered**, makes the run report failure, and is retried. A message whose conditions a
later message delivered is *superseded*, not still outstanding — otherwise one lost message would
report failure for as long as the state file lives. And a receipt marks a condition notified only if
the message actually showed it to a reader: a digest truncated at `max_conditions` leaves the elided
conditions actionable, for the next cycle to carry.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

from .drift import DriftReport, Finding, IntegrityReport, repo_url
from .drift import drift as drift_report
from .drift import integrity as integrity_report
from . import probe

SEVERITY_ORANGE = "orange"
SEVERITY_RED = "red"
SEVERITIES = (SEVERITY_ORANGE, SEVERITY_RED)
_SEVERITY_ORDER = {SEVERITY_ORANGE: 1, SEVERITY_RED: 2}
_SEVERITY_MARKER = {SEVERITY_ORANGE: "🟠", SEVERITY_RED: "🔴"}

STATE_VERSION = 1
DEFAULT_ACK_TTL = 900          # seconds a message may wait for a receipt before it is undelivered
DEFAULT_MAX_REFS = 3           # references rendered per condition
DEFAULT_MAX_CONDITIONS = 10    # conditions rendered per message
MAX_REFERENCES_PER_CONDITION = 25   # what a condition keeps, so one category cannot grow unbounded
MESSAGE_LEDGER_KEEP = 200      # acked messages retained in the state file, newest last

DRIFT_SEVERITY = {
    "only_on_target": SEVERITY_RED,      # served but not in Git: the hand-edit drift this exists to catch
    "missing_on_target": SEVERITY_RED,   # Git has it, clients cannot fetch it
    "differing": SEVERITY_RED,           # served bytes are not the reviewed bytes
    "unreadable": SEVERITY_RED,          # cannot be verified is not the same as verified
}
DRIFT_TITLE = {
    "only_on_target": "the target serves a file the checkout does not have",
    "missing_on_target": "the checkout has a file the target does not serve",
    "differing": "the target's bytes differ from the checkout",
    "unreadable": "the target could not be read, so the served tree is unverified",
}
INTEGRITY_SEVERITY = {
    # An install that would fail, or a check that cannot be made, is red.
    "payload_missing": SEVERITY_RED,
    "pkginfo_missing": SEVERITY_RED,
    "item_not_in_catalog": SEVERITY_RED,
    "manifest_unresolved": SEVERITY_RED,
    "catalog_unreadable": SEVERITY_RED,
    # Consistency that a client survives but that makes what it receives unpredictable.
    "duplicate_name": SEVERITY_ORANGE,
    "catalog_membership_mismatch": SEVERITY_ORANGE,
    "catalog_entry_without_pkginfo": SEVERITY_ORANGE,
}
INTEGRITY_TITLE = {
    "payload_missing": "an offered item's payload is not on the target",
    "pkginfo_missing": "an offered item has no pkginfo in the checkout",
    "item_not_in_catalog": "a manifest offers an item no catalog serves",
    "manifest_unresolved": "a manifest includes a manifest that does not exist",
    "catalog_unreadable": "a served catalog could not be read",
    "duplicate_name": "two catalog entries share one name, so which installer a client receives "
                      "depends on build order",
    "catalog_membership_mismatch": "a catalog's contents disagree with what the pkginfos declare",
    "catalog_entry_without_pkginfo": "a served catalog has an entry the checkout cannot explain",
}
UNKNOWN_SEVERITY = SEVERITY_ORANGE   # a finding kind this module has not graded is still reported

_PKGS = re.compile(r"pkgs/\S+")
_CATALOG = re.compile(r"catalogs/[^\s;]+")


class AlertError(Exception):
    """A refusal: an unusable knob, or a state or receipt file that cannot be trusted."""


def _bound(name: str, value) -> int:
    """A knob whose job is to bound something refuses a value that cannot bound it."""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(
            f"{name} must be a positive whole number, got {value!r}: 0 would mean 'stop doing the "
            f"work' and is refused rather than quietly reading as silence")
    return value


def check_knobs(*, ack_ttl: int = DEFAULT_ACK_TTL, max_refs: int = DEFAULT_MAX_REFS,
                max_conditions: int = DEFAULT_MAX_CONDITIONS, max_age: int = 3600) -> None:
    """Refuse an unusable bound before anything is read or written."""
    _bound("ack_ttl", ack_ttl)
    _bound("max_refs", max_refs)
    _bound("max_conditions", max_conditions)
    _bound("max_age", max_age)


@dataclass(frozen=True)
class Condition:
    """One actionable fact, with the sources a reader can open to check it.

    `key` is the stable identity used by the durable state, so the same condition recurring is
    recognised as the same condition. `references` is what makes the claim checkable: a repository
    path, an HTTP URL, or the observation store plus the run that wrote the reading.
    """
    key: str
    severity: str
    title: str
    detail: str
    references: Tuple[str, ...] = ()

    def __post_init__(self):
        if self.severity not in SEVERITIES:
            raise ValueError(f"severity must be one of {SEVERITIES}, got {self.severity!r}")
        references = tuple(str(r) for r in self.references if r)
        if not references:
            raise ValueError(
                f"condition {self.key!r} has no reference: an alert nobody can check is not "
                f"allowed to exist")
        object.__setattr__(self, "references", references)

    @property
    def marker(self) -> str:
        return _SEVERITY_MARKER[self.severity]

    def to_json(self) -> str:
        return json.dumps({"key": self.key, "severity": self.severity, "title": self.title,
                           "detail": self.detail, "references": list(self.references)},
                          sort_keys=True)


def _reference(http_base: str, relpath: str) -> str:
    """A path a reader can open, as a URL when the endpoint is known."""
    return repo_url(http_base, relpath) if http_base else relpath


# --- repository conditions -----------------------------------------------------------------------

def drift_conditions(report: DriftReport, http_base: str = "") -> List[Condition]:
    """One condition per drift category, red: the served tree is not the reviewed tree."""
    out: List[Condition] = []
    for category in ("only_on_target", "missing_on_target", "differing", "unreadable"):
        entries = list(getattr(report, category))
        if not entries:
            continue
        detail = (f"{len(entries)} file(s): " + ", ".join(entries[:5])
                  + (" …" if len(entries) > 5 else ""))
        out.append(Condition(
            key=f"drift:{category}",
            severity=DRIFT_SEVERITY[category],
            title=DRIFT_TITLE[category],
            detail=detail,
            references=tuple(_reference(http_base, entry)
                             for entry in entries[:MAX_REFERENCES_PER_CONDITION])))
    return out


def _integrity_references(finding: Finding, http_base: str) -> Tuple[str, ...]:
    """Where a reader looks to see this finding for themselves."""
    kind = finding.kind
    if kind == "payload_missing":
        payload = _PKGS.search(finding.detail or "")
        paths = [payload.group(0)] if payload else ["pkgs/"]
    elif kind == "pkginfo_missing":
        paths = ["pkgsinfo/"]
    elif kind == "catalog_unreadable":
        paths = [finding.subject if finding.subject.startswith("catalogs/") else "catalogs/"]
    elif kind in ("item_not_in_catalog", "manifest_unresolved"):
        paths = [f"manifests/{name}" for name in finding.manifests] or ["manifests/"]
    else:
        named = _CATALOG.search(finding.detail or "")
        paths = [named.group(0) if named else "catalogs/"]
    return tuple(_reference(http_base, path) for path in paths)


def integrity_conditions(report: IntegrityReport, http_base: str = "") -> List[Condition]:
    """One condition per finding kind: groups of the same defect are one thing to act on."""
    by_kind: Dict[str, List[Finding]] = {}
    for finding in report.findings:
        by_kind.setdefault(finding.kind, []).append(finding)
    out: List[Condition] = []
    for kind in sorted(by_kind):
        findings = by_kind[kind]
        details = []
        for finding in findings[:3]:
            wanted = f" [wanted by {', '.join(finding.manifests)}]" if finding.manifests else ""
            details.append(f"{finding.subject}: {finding.detail}{wanted}")
        if len(findings) > 3:
            details.append(f"… and {len(findings) - 3} more")
        references: List[str] = []
        for finding in findings:
            for reference in _integrity_references(finding, http_base):
                if reference not in references:
                    references.append(reference)
        out.append(Condition(
            key=f"integrity:{kind}",
            severity=INTEGRITY_SEVERITY.get(kind, UNKNOWN_SEVERITY),
            title=INTEGRITY_TITLE.get(kind, f"{kind} (ungraded finding kind)"),
            detail="; ".join(details),
            references=tuple(references[:MAX_REFERENCES_PER_CONDITION])))
    return out


# --- the expected fleet, and fleet conditions ----------------------------------------------------

@dataclass(frozen=True)
class ExpectedMachine:
    """A Mac the inventory records, and the manifest it is supposed to resolve."""
    key: str
    name: str
    serial: Optional[str]
    manifest: Optional[str]
    source: str


def load_inventory(path: str) -> List[ExpectedMachine]:
    """The expected fleet, from the identity inventory (ticket 04).

    Both lists are machines with a record: `machines` (seen in the ARD export) and `known_absent`
    (proved to exist without one, which is where Cyril's Mac mini is recorded). `unmanaged_machines`
    and `orphan_manifests` are deliberately not expected machines — they are the inventory's own
    findings about manifests without machines, which is ticket 06's question and not a live
    regression.

    A row with neither a serial nor a name is refused rather than carried: it has no identity to
    check anything against, and a row that quietly disables its own manifest check is how a gap
    survives a review. Two rows for one machine are refused for the same reason.
    """
    with open(path, encoding="utf-8") as fh:
        inventory = json.load(fh)
    out: List[ExpectedMachine] = []
    seen_keys: Dict[str, str] = {}

    def add(machine: ExpectedMachine, where: str) -> None:
        if not machine.name and not machine.serial:
            raise ValueError(f"{path} {where} has neither a serial nor a name: a machine the "
                             f"inventory cannot identify cannot be checked")
        if machine.serial and machine.serial in seen_keys:
            raise ValueError(f"{path} {where} repeats serial {machine.serial!r}, already at "
                             f"{seen_keys[machine.serial]}: one machine, one row")
        if not machine.serial and machine.name in {m.name for m in out}:
            raise ValueError(f"{path} {where} repeats the name {machine.name!r}: one machine, one row")
        if machine.serial:
            seen_keys[machine.serial] = where
        out.append(machine)

    for index, row in enumerate(inventory.get("machines") or []):
        name = row.get("munki_name") or row.get("unix_hostname") or row.get("computer_name")
        serial = row.get("serial")
        add(ExpectedMachine(key=serial or name or "", name=name or "", serial=serial,
                            manifest=row.get("munki_name") or name or "",
                            source=f"{path}#machines[{index}]"), f"machines[{index}]")
    for index, row in enumerate(inventory.get("known_absent") or []):
        name = row.get("probe_hostname") or row.get("name")
        serial = row.get("serial")
        add(ExpectedMachine(key=serial or name or "", name=name or "", serial=serial,
                            manifest=name or "",
                            source=f"{path}#known_absent[{index}]"), f"known_absent[{index}]")
    return out


def _normalise_name(name: Optional[str]) -> str:
    return (name or "").split(".")[0].strip().lower()


def _reading_key(machine: ExpectedMachine, readings: Dict[str, dict]) -> Optional[str]:
    """Which reading belongs to this machine: by serial first, by name only as a fallback."""
    for key, entry in readings.items():
        observation = entry["observation"]
        target = observation.get("target") or {}
        observed = observation.get("machine") or {}
        if machine.serial and machine.serial in (target.get("serial"), observed.get("serial"), key):
            return key
        names = {_normalise_name(target.get("host")), _normalise_name(target.get("name")),
                 _normalise_name(observed.get("hostname"))}
        if machine.name and _normalise_name(machine.name) in names:
            return key
    return None


def _store_reference(store_path: str, observation: dict) -> str:
    run_id = observation.get("run_id")
    return f"{store_path} (run {run_id})" if run_id else store_path


def observation_conditions(records: Sequence[dict], *, expected: Sequence[ExpectedMachine], now: str,
                           max_age: int, store_path: Optional[str] = None) -> List[Condition]:
    """Per-machine conditions from the observation store.

    A machine with no reading, a machine whose reading did not reach it, and a machine whose reading
    is stale are each actionable. A stale reading contributes **only** its staleness: its manifest
    and its rejections are not reported as current fact.
    """
    _bound("max_age", max_age)
    store = store_path or "observation store (path not recorded)"
    readings = probe.latest_per_machine(records, now=now, max_age=max_age)
    out: List[Condition] = []
    claimed: set = set()
    for machine in expected:
        key = _reading_key(machine, readings)
        if key is None:
            out.append(Condition(
                key=f"fleet:unobserved:{machine.key}", severity=SEVERITY_ORANGE,
                title=f"{machine.name or machine.key} has never been observed",
                detail=("no observation has reached this machine, so what it runs is unknown — "
                        "unknown is not compliant"),
                references=(machine.source, store)))
            continue
        claimed.add(key)
        entry = readings[key]
        observation = entry["observation"]
        reference = _store_reference(store, observation)
        if observation.get("outcome") != "observed":
            reason = observation.get("reason") or observation.get("outcome") or "unknown"
            detail = observation.get("detail") or ""
            out.append(Condition(
                key=f"fleet:not-reached:{machine.key}", severity=SEVERITY_ORANGE,
                title=f"{machine.name or machine.key} could not be observed",
                detail=f"{reason}: {detail}".strip(": "),
                references=(reference, machine.source)))
            continue
        state = observation.get("state") or {}
        if entry.get("stale"):
            out.append(Condition(
                key=f"fleet:stale:{machine.key}", severity=SEVERITY_ORANGE,
                title=f"{machine.name or machine.key}'s last observation is stale",
                detail=(f"age {entry.get('age_seconds')}s against a {max_age}s limit; what it "
                        f"resolved and what it pending are not reported here, because this reading "
                        f"is older than the limit"),
                references=(reference,)))
            continue
        resolved = state.get("manifest_name")
        if machine.manifest and resolved != machine.manifest:
            out.append(Condition(
                key=f"fleet:manifest-unexpected:{machine.key}", severity=SEVERITY_ORANGE,
                title=f"{machine.name or machine.key} is not resolving its own manifest",
                detail=(f"{machine.name or machine.key} resolved {resolved!r}; it should resolve its "
                        f"own machine manifest {machine.manifest!r}"),
                references=(reference, machine.source)))
        rejections = state.get("architecture_rejections") or []
        if rejections:
            items = ", ".join(f"{r.get('item')} {r.get('version')} (supports "
                              f"{r.get('supported')}, machine is {r.get('machine_arch')})"
                              for r in rejections[:3])
            out.append(Condition(
                key=f"fleet:rejection:{machine.key}", severity=SEVERITY_ORANGE,
                title=f"{machine.name or machine.key} has items rejected for its architecture",
                detail=f"{len(rejections)} rejection(s): {items}",
                references=(reference,)))
    for key, entry in sorted(readings.items()):
        if key in claimed:
            continue
        observation = entry["observation"]
        target = observation.get("target") or {}
        name = (observation.get("machine") or {}).get("hostname") or target.get("host") or key
        out.append(Condition(
            key=f"fleet:uninventoried:{key}", severity=SEVERITY_ORANGE,
            title=f"{name} was observed but the inventory has no record of it",
            detail=(f"an observation reached {name} while the inventory holds no row for it "
                    f"(serial or name {key!r}); a machine nobody accounts for is not a fleet member"),
            references=(_store_reference(store, observation),)))
    return out


def conditions(*, drift_report: Optional[DriftReport] = None,
               integrity_report: Optional[IntegrityReport] = None, records: Sequence[dict] = (),
               expected: Sequence[ExpectedMachine] = (), now: str, max_age: int = 3600,
               http_base: str = "", store_path: Optional[str] = None) -> List[Condition]:
    """Every actionable condition across the repository and the fleet, repository first."""
    out: List[Condition] = []
    if drift_report is not None:
        out += drift_conditions(drift_report, http_base)
    if integrity_report is not None:
        out += integrity_conditions(integrity_report, http_base)
    out += observation_conditions(records, expected=expected, now=now, max_age=max_age,
                                  store_path=store_path)
    return out


# --- the message ---------------------------------------------------------------------------------

@dataclass(frozen=True)
class Message:
    """One rendered digest of every newly actionable condition, and the record of what it carried.

    `conditions` is everything the message carried (so nothing is sent twice while it is in flight);
    `rendered_keys` is what a reader can actually see in the body. The two differ when a digest is
    truncated, and the difference is recorded because a receipt may only mark as notified what the
    reader was shown.
    """
    message_id: str
    created_at: str
    severity: str
    body: str
    conditions: Tuple[Condition, ...]
    rendered_keys: Tuple[str, ...] = ()

    def to_json(self) -> str:
        return json.dumps({"message_id": self.message_id, "created_at": self.created_at,
                           "severity": self.severity, "body": self.body,
                           "rendered_keys": list(self.rendered_keys),
                           "conditions": [json.loads(c.to_json()) for c in self.conditions]},
                          sort_keys=True)


def _max_severity(conditions: Sequence[Condition]) -> str:
    return max((c.severity for c in conditions), key=lambda s: _SEVERITY_ORDER[s])


def _stamp(created_at: str) -> str:
    return "".join(ch for ch in created_at if ch.isalnum())


def render(conditions: Sequence[Condition], created_at: str, *, max_refs: int = DEFAULT_MAX_REFS,
           max_conditions: int = DEFAULT_MAX_CONDITIONS) -> Message:
    """Render one message. Refuses an empty digest — there is nothing to send, and a message that
    says so is the noise this ticket exists to remove."""
    conditions = list(conditions)
    if not conditions:
        raise ValueError("refusing to render a message with no conditions: silence is the "
                         "healthy state, not a notification")
    _bound("max_refs", max_refs)
    _bound("max_conditions", max_conditions)
    severity = _max_severity(conditions)
    lines = [f"{_SEVERITY_MARKER[severity]} T6 Munki: {len(conditions)} actionable condition(s) "
             f"at {created_at}", ""]
    for number, condition in enumerate(conditions[:max_conditions], start=1):
        lines.append(f"{number}. {condition.marker} {condition.title}")
        lines.append(f"   {condition.detail}")
        for reference in condition.references[:max_refs]:
            lines.append(f"   source: {reference}")
        if len(condition.references) > max_refs:
            lines.append(f"   … and {len(condition.references) - max_refs} more source(s)")
        lines.append("")
    if len(conditions) > max_conditions:
        lines.append(f"… and {len(conditions) - max_conditions} more condition(s) not listed "
                     f"(max-conditions {max_conditions})")
    digest = hashlib.sha256("|".join(sorted(c.key for c in conditions)).encode("utf-8")).hexdigest()
    return Message(message_id=f"alert-{_stamp(created_at)}-{digest[:8]}", created_at=created_at,
                   severity=severity, body="\n".join(lines).rstrip(), conditions=tuple(conditions),
                   rendered_keys=tuple(c.key for c in conditions[:max_conditions]))


# --- durable state, receipts, and the cycle ------------------------------------------------------

def load_state(path: str) -> Optional[dict]:
    """The alert state, or None when there is none yet."""
    if not path or not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        try:
            state = json.load(fh)
        except json.JSONDecodeError as exc:
            raise AlertError(f"{path} is not readable JSON: {exc}") from exc
    if state.get("version") != STATE_VERSION:
        raise AlertError(f"{path} is state version {state.get('version')!r}, this build writes "
                         f"{STATE_VERSION}: reconcile it deliberately rather than guessing")
    return state


def save_state(path: str, state: dict) -> None:
    """Write the state atomically: a half-written state file is a lost alert or a duplicate one."""
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    temporary = f"{path}.tmp"
    with open(temporary, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=1, sort_keys=True)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(temporary, path)


def _blank_state(now: str) -> dict:
    return {"version": STATE_VERSION, "updated_at": now, "conditions": {}, "messages": {}}


def receipts_path(outbox: str) -> str:
    return os.path.join(outbox, "receipts.jsonl")


def read_receipts(outbox: str) -> List[dict]:
    """What the transport recorded. A line that cannot be read is named, not skipped."""
    path = receipts_path(outbox)
    if not os.path.isfile(path):
        return []
    out: List[dict] = []
    with open(path, encoding="utf-8") as fh:
        for number, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise AlertError(f"{path} line {number} is not readable JSON: {exc}") from exc
    return out


def write_message(outbox: str, message: Message) -> str:
    os.makedirs(outbox, exist_ok=True)
    path = os.path.join(outbox, f"{message.message_id}.json")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(message.to_json())
        fh.write("\n")
    return path


def actionable(state: dict, conditions: Sequence[Condition]) -> List[Condition]:
    """The subset worth telling someone about: new, worse, or not yet notified."""
    out: List[Condition] = []
    for condition in conditions:
        entry = (state.get("conditions") or {}).get(condition.key)
        if entry is None or entry.get("severity") != condition.severity \
                or entry.get("delivered_at") is None:
            out.append(condition)
    return out


def _parse_time(value, what: str):
    """An ISO-8601 timestamp, or a refusal naming what could not be read.

    The clock decides whether a message is in flight or lost, so an unreadable one is refused
    rather than allowed to read as 'in flight' forever, which is how a lost alert disappears.
    """
    if isinstance(value, str) and value.endswith("Z"):
        value = value[:-1] + "+00:00"      # the one ISO-8601 form Python 3.9's parser rejects
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise AlertError(f"{what} is not an ISO-8601 timestamp I can read: {value!r}") from exc


def _age_seconds(created_at: Optional[str], now: str) -> Optional[int]:
    """How long a message has been waiting; None when the age cannot be established."""
    if not created_at:
        return None
    try:
        return int(_parse_time(now, "now").timestamp()
                   - _parse_time(created_at, "a ledger entry's created_at").timestamp())
    except AlertError:
        return None                       # unreadable age is never read as "in flight"


def _later(candidate: Optional[str], than: Optional[str]) -> bool:
    """Is `candidate` later than `than`? An unreadable one is never treated as later."""
    if not candidate or not than:
        return False
    try:
        return _parse_time(candidate, "created_at") > _parse_time(than, "created_at")
    except AlertError:
        return False


def _dedupe(conditions: Sequence[Condition]) -> List[Condition]:
    """One condition per key, at the highest severity seen.

    A duplicate key is one fact, not two: the state keys on it, and a message that listed it twice
    would overstate what was found. `load_inventory` refuses the rows that would cause it; this is
    the guard for any other producer.
    """
    by_key: Dict[str, Condition] = {}
    for condition in conditions:
        seen = by_key.get(condition.key)
        if seen is None or _SEVERITY_ORDER[condition.severity] > _SEVERITY_ORDER[seen.severity]:
            by_key[condition.key] = condition
    return list(by_key.values())


@dataclass
class AlertRun:
    """What one cycle decided, did, and learned."""
    now: str
    conditions: List[Condition]
    sent: List[Condition]
    message: Optional[Message] = None
    message_path: Optional[str] = None
    delivered: List[dict] = field(default_factory=list)
    failed: List[dict] = field(default_factory=list)
    pending: List[str] = field(default_factory=list)
    undelivered: List[str] = field(default_factory=list)
    superseded: List[str] = field(default_factory=list)
    stray: List[dict] = field(default_factory=list)
    dry_run: bool = False

    @property
    def ok(self) -> bool:
        """A run that could not deliver does not report success."""
        return not self.failed and not self.undelivered

    def describe(self) -> str:
        lines = [f"{'dry run (no state written) — ' if self.dry_run else ''}alert run {self.now}"]
        lines.append(f"  conditions: {len(self.sent)} actionable of {len(self.conditions)} current")
        if self.message is None:
            lines.append("  message: none — nothing newly actionable")
        else:
            lines.append(f"  message: {self.message.message_id} "
                         f"({len(self.message.rendered_keys)} of {len(self.sent)} condition(s) "
                         f"rendered)"
                         + (f" -> {self.message_path}" if self.message_path else " (not written)"))
        lines.append(f"  delivered {len(self.delivered)}, failed {len(self.failed)}, "
                     f"pending {len(self.pending)}, undelivered {len(self.undelivered)}, "
                     f"superseded {len(self.superseded)}, stray receipts {len(self.stray)}")
        return "\n".join(lines)


def cycle(*, state_path: str, outbox: str, conditions: Sequence[Condition], now: str,
          ack_ttl: int = DEFAULT_ACK_TTL, max_refs: int = DEFAULT_MAX_REFS,
          max_conditions: int = DEFAULT_MAX_CONDITIONS, dry_run: bool = False) -> AlertRun:
    """One alert cycle: consume receipts, decide, render one message, write it, record what happened.

    A dry run writes nothing at all. A cycle with nothing actionable hands over no message — it
    still records the state, because the next cycle's decision (what is new, what has cleared, how
    long a message has waited) rests on it.
    """
    _bound("ack_ttl", ack_ttl)
    _bound("max_refs", max_refs)
    _bound("max_conditions", max_conditions)
    _parse_time(now, "now")
    conditions = _dedupe(list(conditions))
    state = load_state(state_path) or _blank_state(now)
    state["conditions"] = state.get("conditions") or {}
    state["messages"] = state.get("messages") or {}
    known = state["messages"]

    # 1. What the transport said about the messages it was handed. A receipt for a message this
    #    state does not hold changes nothing and is reported rather than materialised: a ledger
    #    entry with no keys can never resolve, and would be re-created on every cycle.
    fresh_receipts: List[dict] = []
    stray: List[dict] = []
    for receipt in read_receipts(outbox):
        message_id = receipt.get("message_id")
        if not message_id:
            raise AlertError(f"a receipt names no message: {receipt!r}")
        entry = known.get(message_id)
        if entry is None:
            stray.append(receipt)
            continue
        if entry.get("receipt") is not None:
            continue
        fresh_receipts.append(receipt)
        entry["receipt"] = "delivered" if receipt.get("delivered") else "failed"
        entry["receipt_at"] = receipt.get("at")
        entry["detail"] = receipt.get("detail") or ""
        # Only what the reader was shown counts as notified: a condition elided from a truncated
        # digest has not been told to anyone, and stays actionable until a message shows it.
        for key in entry.get("rendered_keys") or []:
            condition_entry = state["conditions"].setdefault(
                key, {"severity": None, "first_seen": entry.get("created_at"), "last_seen": None,
                      "delivered_at": None, "failed_at": None, "failures": 0})
            if receipt.get("delivered"):
                condition_entry["delivered_at"] = receipt.get("at") or now
            else:
                condition_entry["failures"] = (condition_entry.get("failures") or 0) + 1
                condition_entry["failed_at"] = receipt.get("at") or now

    # 2. What is still in flight, what nobody acknowledged in time, and what a later delivery has
    #    already covered. A message whose conditions a later message delivered is history, not an
    #    outstanding failure — otherwise one lost message reports failure forever, and the only
    #    cure is deleting the state file by hand.
    deliverers: Dict[str, str] = {}
    for message_id, entry in known.items():
        if entry.get("receipt") != "delivered":
            continue
        for key in entry.get("keys") or []:
            held = deliverers.get(key)
            if held is None or _later(entry.get("created_at"), known[held].get("created_at")):
                deliverers[key] = message_id
    pending: List[str] = []
    undelivered: List[str] = []
    superseded: List[str] = []
    for message_id, entry in sorted(known.items()):
        if entry.get("receipt") is not None:
            continue
        keys = list(entry.get("keys") or [])
        if not keys:
            continue                     # carries nothing, owes nothing; pruning removes it
        created = entry.get("created_at")
        covered = {key: deliverers[key] for key in keys if key in deliverers}
        if len(covered) == len(keys) and all(_later(known[mid].get("created_at"), created)
                                             for mid in covered.values()):
            entry["superseded_by"] = covered
            superseded.append(message_id)
            continue
        age = _age_seconds(created, now)
        if age is not None and age <= ack_ttl:
            pending.append(message_id)
            continue
        undelivered.append(message_id)
        if not entry.get("undelivered_at"):
            entry["undelivered_at"] = now
            for key in keys:
                condition_entry = state["conditions"].setdefault(
                    key, {"severity": None, "first_seen": created, "last_seen": None,
                          "delivered_at": None, "failed_at": None, "failures": 0})
                condition_entry["failures"] = (condition_entry.get("failures") or 0) + 1
                condition_entry["failed_at"] = now

    # 3. The decision: what is worth one message, minus whatever already has one in flight.
    todo = actionable(state, conditions)
    in_flight = {key for message_id, entry in known.items() if message_id in pending
                 for key in (entry.get("keys") or [])}
    todo = [condition for condition in todo if condition.key not in in_flight]

    # 4. A condition that is gone is forgotten, so its return alerts again. A condition whose
    #    message is in flight keeps the severity that message carried: advancing it here would let
    #    that message's receipt record a worse severity as already notified.
    for key in list(state["conditions"]):
        if key not in {c.key for c in conditions} and key not in in_flight:
            del state["conditions"][key]
    for condition in conditions:
        entry = state["conditions"].setdefault(
            condition.key, {"severity": condition.severity, "first_seen": now, "last_seen": now,
                            "delivered_at": None, "failed_at": None, "failures": 0})
        if condition.key not in in_flight:
            entry["severity"] = condition.severity
        entry["last_seen"] = now

    # 5. One message, or silence.
    message = render(todo, now, max_refs=max_refs, max_conditions=max_conditions) if todo else None
    message_path = None
    if message is not None and not dry_run:
        message_path = write_message(outbox, message)
        known[message.message_id] = {"created_at": now, "keys": [c.key for c in todo],
                                     "rendered_keys": list(message.rendered_keys),
                                     "receipt": None}
    if not dry_run:
        resolved = sorted((mid for mid, entry in known.items()
                           if entry.get("receipt") is not None or not (entry.get("keys") or [])),
                          key=lambda mid: (known[mid].get("created_at") or "", mid))
        for message_id in resolved[:max(0, len(resolved) - MESSAGE_LEDGER_KEEP)]:
            del known[message_id]
        state["updated_at"] = now
        save_state(state_path, state)
    return AlertRun(now=now, conditions=conditions, sent=todo, message=message,
                    message_path=message_path,
                    delivered=[r for r in fresh_receipts if r.get("delivered")],
                    failed=[r for r in fresh_receipts if not r.get("delivered")],
                    pending=pending, undelivered=undelivered, superseded=superseded, stray=stray,
                    dry_run=dry_run)
