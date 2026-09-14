"""The per-machine state probe and the append-only observation store.

Fleet state is read from a record with a known age, never from a live sweep, and "we could not reach
it" can never be written in a way that reads like "it is fine" (ADR 0004).

What the probe reads is Munki's **own** answer, not a re-implementation of it: the client's
`ManagedInstallReport.plist` for the resolved manifest, what is pending, the warnings and the
`MachineInfo` block, and the tail of `ManagedSoftwareUpdate.log` for the run boundary, the manifest
lookups it attempted and the architecture rejections. That distinction matters — a home-made
install-detection check produces confident wrong answers, which is how five items were once
misreported as missing on a machine that had them.
"""
from __future__ import annotations

import json
import os
import plistlib
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

PROBE_VERSION = "munki-fleet-probe/1"
CLIENT_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "probe_client.sh")
DEFAULT_OBSERVER = "munki-fleet-collector"
DEFAULT_TIMEOUT = 45
LOG_TAIL_LINES = 400

Runner = Callable[..., Tuple[int, bytes, bytes]]


class ProbeError(Exception):
    """The probe could not be interpreted, or was asked for something it cannot do."""


# --- reading what the client said -------------------------------------------------------------

def _split_envelope(text: str) -> Tuple[List[str], str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != PROBE_VERSION:
        raise ProbeError(f"not a {PROBE_VERSION} payload")
    try:
        header_end = lines.index("<<<REPORT>>>")
        log_marker = lines.index("<<<LOG>>>")
    except ValueError as exc:
        raise ProbeError("the payload is missing its section markers") from exc
    header = lines[1:header_end]
    report_text = "\n".join(lines[header_end + 1:log_marker]).strip()
    log_text = "\n".join(lines[log_marker + 1:])
    return header, report_text, log_text


@dataclass
class ProbePayload:
    munki_tools: bool
    report_present: bool
    report_mtime: Optional[int]
    log_present: bool
    log_mtime: Optional[int]
    report: Optional[dict]
    log: str
    problems: List[str] = field(default_factory=list)

    @property
    def newest_source_epoch(self) -> Optional[int]:
        stamps = [s for s in (self.report_mtime, self.log_mtime) if s is not None]
        return max(stamps) if stamps else None


def parse_report_section(text: str):
    """The report, whether it arrived as the plist Munki writes or as JSON.

    Verbatim plist is the normal case: `plutil -convert json` cannot represent the report's date
    objects and fails with a zero exit status, which is how the report was silently lost once.
    """
    text = text.strip()
    if not text:
        return None, "empty-report"
    try:
        parsed = json.loads(text)
        return (parsed, None) if isinstance(parsed, dict) else (None, "unreadable-report")
    except json.JSONDecodeError:
        pass
    try:
        parsed = plistlib.loads(text.encode("utf-8"))
        return (parsed, None) if isinstance(parsed, dict) else (None, "unreadable-report")
    except Exception:
        return None, "unreadable-report"


def parse_envelope(text: str) -> ProbePayload:
    header, report_text, log_text = _split_envelope(text)
    fields: Dict[str, str] = {}
    for line in header:
        if "=" in line:
            key, _, value = line.partition("=")
            fields[key.strip()] = value.strip()

    def flag(name: str, default: bool = False) -> bool:
        return fields.get(name, "yes" if default else "no") == "yes"

    def epoch(name: str) -> Optional[int]:
        value = fields.get(name, "-")
        return int(value) if value.isdigit() else None

    problems: List[str] = []
    report: Optional[dict] = None
    report_present = flag("report_present")
    if not report_present:
        problems.append("no-report")
    else:
        report, problem = parse_report_section(report_text)
        if problem:
            problems.append(problem)

    munki_tools = flag("munki_tools")
    if not munki_tools:
        problems.append("no-munki-tools")
    if not flag("log_present"):
        problems.append("no-log")

    return ProbePayload(munki_tools=munki_tools, report_present=report_present,
                        report_mtime=epoch("report_mtime"), log_present=flag("log_present"),
                        log_mtime=epoch("log_mtime"), report=report, log=log_text,
                        problems=problems)


RUN_START = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+[+-]\d{2}:\d{2}) "
    r"### Starting managedsoftwareupdate run(?:: (?P<kind>[\w-]+))? ###", re.M)
RUN_END = re.compile(
    r"^(?P<ts>\S+ \S+) ### Ending managedsoftwareupdate run ###", re.M)
REJECTION = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+[+-]\d{2}:\d{2}) "
    r"WARNING: Rejected item (?P<item>[^,]+), version (?P<version>\S+) "
    r"with supported architectures (?P<supported>\[[^\]]*\])\..*?"
    r"Our architecture is (?P<arch>[^\s.]+)\.", re.M)
MANIFEST_LOOKUP = re.compile(r"^\S+ \S+ (?P<line>Manifest \S+ not found.*)$", re.M)


def last_run(log: str) -> Optional[dict]:
    """The most recent run boundary in the log tail, with the source's own timestamp."""
    starts = list(RUN_START.finditer(log))
    if not starts:
        return None
    start = starts[-1]
    ends = [m for m in RUN_END.finditer(log) if m.start() > start.start()]
    return {"started": start.group("ts"), "kind": start.group("kind"),
            "ended": ends[-1].group("ts") if ends else None}


def architecture_rejections(log: str) -> List[dict]:
    return [{"timestamp": m.group("ts"), "item": m.group("item").strip(),
             "version": m.group("version"), "supported": m.group("supported"),
             "machine_arch": m.group("arch")} for m in REJECTION.finditer(log)]


def manifest_lookups(log: str) -> List[str]:
    return [m.group("line").strip() for m in MANIFEST_LOOKUP.finditer(log)]


def machine_identity(report: dict) -> Optional[dict]:
    info = report.get("MachineInfo") or {}
    if not info.get("serial_number"):
        return None
    return {"serial": info.get("serial_number"), "arch": info.get("arch"),
            "hostname": info.get("hostname"), "os_vers": info.get("os_vers"),
            "os_build": info.get("os_build_number"), "model": info.get("machine_model"),
            "munki_version": info.get("munki_version")}


def summarise(payload: ProbePayload, observed_at: str) -> dict:
    """The state half of an observation, from a payload that carried a readable report."""
    report = payload.report or {}
    info = report.get("MachineInfo") or {}
    run = last_run(payload.log)
    source_epoch = payload.newest_source_epoch
    observed_epoch = _epoch_of(observed_at)
    return {
        "munki_version": info.get("munki_version") or report.get("ManagedInstallVersion"),
        "manifest_name": report.get("ManifestName"),
        "pending_count": len(report.get("ItemsToInstall") or []),
        "pending_items": report.get("ItemsToInstall") or [],
        "problem_installs": report.get("ProblemInstalls") or [],
        "run_type": report.get("RunType"),
        "last_check": {
            # the report writes these in UTC; they are recorded as given, with the source named
            "timestamp": (run or {}).get("started") or _as_text(report.get("EndTime")),
            "result": _run_result(report),
            "report_started": _as_text(report.get("StartTime")),
            "report_ended": _as_text(report.get("EndTime")),
            "log_run_started": (run or {}).get("started"),
            "log_run_ended": (run or {}).get("ended"),
            "run_kind": (run or {}).get("kind"),
        },
        "warnings": report.get("Warnings") or [],
        "errors": report.get("Errors") or [],
        "architecture_rejections": architecture_rejections(payload.log),
        "manifest_lookups": manifest_lookups(payload.log),
        "source_age_seconds": (observed_epoch - source_epoch)
        if (observed_epoch is not None and source_epoch is not None) else None,
    }


def _run_result(report: dict) -> str:
    """How the last run ended, as a value rather than something a reader has to infer."""
    if report.get("Errors") or report.get("ProblemInstalls"):
        return "failed"
    if report.get("Warnings"):
        return "warnings"
    return "clean"


def _as_text(value) -> Optional[str]:
    if value is None:
        return None
    return value.isoformat(sep=" ") if hasattr(value, "isoformat") else str(value)


def _epoch_of(iso) -> Optional[int]:
    if not isinstance(iso, str):
        return None
    try:
        return int(datetime.fromisoformat(iso).timestamp())
    except ValueError:
        return None


# --- the observation and the run record ---------------------------------------------------------

@dataclass
class Observation:
    run_id: str
    observed_at: str
    observer: str
    target: dict
    outcome: str                      # observed | partial | unobserved
    reason: Optional[str] = None
    detail: Optional[str] = None
    machine: Optional[dict] = None
    state: Optional[dict] = None
    source: Optional[dict] = None
    problems: List[str] = field(default_factory=list)
    kind: str = "observation"

    def to_json(self) -> str:
        return json.dumps(self.__dict__, sort_keys=True)

    @classmethod
    def from_json(cls, line) -> "Observation":
        body = _body(line)
        body.pop("kind", None)
        return cls(**body)

    @classmethod
    def from_payload(cls, target: dict, payload: ProbePayload, observed_at: str, observer: str,
                     run_id: str = "") -> "Observation":
        common: Dict[str, Any] = dict(run_id=run_id, observed_at=observed_at, observer=observer,
                                      target=target)
        if "no-munki-tools" in payload.problems:
            return cls(outcome="partial", reason="no-munki-tools", **common)
        if payload.report is None:
            reason = next((p for p in payload.problems
                           if p in ("no-report", "empty-report", "unreadable-report")), "no-report")
            return cls(outcome="partial", reason=reason, **common)

        machine = machine_identity(payload.report)
        state = summarise(payload, observed_at)
        if machine is None:
            # The report was read but names no serial, so this observation cannot carry the
            # machine's identity. The state is kept because it is real; the outcome is not
            # `observed` because a row identified only by a hostname is not a compliant one.
            return cls(outcome="partial", reason="no-serial", state=state, problems=["no-serial"],
                       **common)
        problems: List[str] = []
        claimed = (target or {}).get("serial")
        if claimed and machine.get("serial") != claimed:
            problems.append("identity-mismatch")
        return cls(outcome="observed", machine=machine, state=state, problems=problems,
                   source={"timestamp": state["last_check"]["log_run_started"]
                                        or state["last_check"]["report_ended"],
                           "age_seconds": state["source_age_seconds"],
                           "report_mtime": payload.report_mtime, "log_mtime": payload.log_mtime},
                   **common)

    @classmethod
    def unreachable(cls, target: dict, observed_at: str, observer: str, reason: str,
                    detail: str = "", run_id: str = "") -> "Observation":
        return cls(run_id=run_id, observed_at=observed_at, observer=observer, target=target,
                   outcome="unobserved", reason=reason, detail=detail or None)


@dataclass
class RunRecord:
    run_id: str
    observed_at: str
    observer: str
    targeted: int
    observed: int
    partial: int
    unobserved: int
    complete: bool
    kind: str = "run"

    @property
    def reached(self) -> int:
        return self.observed + self.partial

    def to_json(self) -> str:
        body = dict(self.__dict__)
        body["reached"] = self.reached
        return json.dumps(body, sort_keys=True)


# --- running the probe over machines -------------------------------------------------------------

def default_runner(host: str, command: str, timeout: Optional[int] = None):
    """SSH, reusing the publish path's connection options. No credentials are ever sent."""
    from .targets import default_ssh_runner
    return default_ssh_runner(host, timeout or DEFAULT_TIMEOUT)(command)


def _declared_path(observation: Observation, defect: Optional[dict]) -> Observation:
    """Keep on the reading the fact that its path was never declared.

    A machine with no access record is still probed — by its inventory address, which is where it was
    last seen and not what it answers to — and the reading is real. But `no-access-record` travels
    with it, so a row produced by a path nobody declared cannot be read as a verified one.
    """
    kind = (defect or {}).get("kind")
    if kind and kind not in observation.problems:
        observation.problems.append(kind)
    return observation


def _transport_message(exc: BaseException, command: str) -> str:
    """The transport's own words, without this probe's whole script quoted back inside them.

    `default_ssh_runner` reports a timeout as `ssh timed out after Ns: <command>`, and the command is
    the entire probe script. Kept verbatim, one unreachable machine contributes 200 characters of
    heredoc to every reading — which buries the one fact that matters and repeats it per machine.
    """
    message = f"{type(exc).__name__}: {exc}"
    if command:
        message = message.replace(command, "<the probe script>")
    return message.splitlines()[0][:200]


def probe_command() -> str:
    with open(CLIENT_SCRIPT, encoding="utf-8") as fh:
        script = fh.read()
    return f"sh -s <<'MUNKI_FLEET_PROBE_EOF'\n{script}\nMUNKI_FLEET_PROBE_EOF"


def probe_run(targets: Sequence[dict], runner: Optional[Runner] = None,
              store_path: Optional[str] = None, observer: str = DEFAULT_OBSERVER,
              now: Optional[str] = None, run_id: Optional[str] = None,
              timeout: Optional[int] = None) -> Tuple[RunRecord, List[Observation]]:
    """Probe every target once, and record the run whether or not it went well.

    Targets that cannot be reached are observations too — marked unobserved, with the transport's
    own message kept as `detail` so the reason is checkable rather than asserted.
    """
    runner = runner or default_runner
    observed_at = now or datetime.now().astimezone().isoformat(timespec="seconds")
    run_id = run_id or f"{observed_at}/{uuid.uuid4().hex[:8]}"
    command = probe_command()

    observations: List[Observation] = []
    for target in targets:
        # A declaration that could not be trusted stops the probe here rather than being replaced by
        # one that was never declared: a fallback that happens to work is how an unverified login
        # becomes fleet state.
        defect = target.get("access_defect") or {}
        if defect.get("blocks"):
            observations.append(Observation.unreachable(
                target, observed_at, observer, defect.get("kind") or "access-blocked",
                detail=defect.get("detail") or "", run_id=run_id))
            continue
        # The declared destination is the transport and is used verbatim. The inventory address is
        # where the machine was last seen, and is the transport only when nothing was declared.
        address = target.get("ssh_destination") or target.get("address") or target["host"]
        try:
            returncode, stdout, stderr = runner(address, command, timeout)
        except Exception as exc:                                   # transport failure
            observations.append(_declared_path(Observation.unreachable(
                target, observed_at, observer, "unreachable",
                detail=_transport_message(exc, command), run_id=run_id), defect))
            continue
        if returncode != 0:
            reason = "unreachable" if returncode == 255 else "probe-failed"
            detail = stderr.decode("utf-8", "replace").strip().splitlines()
            observations.append(_declared_path(Observation.unreachable(
                target, observed_at, observer, reason,
                detail=(detail[-1] if detail else f"exit {returncode}")[:200], run_id=run_id),
                defect))
            continue
        try:
            payload = parse_envelope(stdout.decode("utf-8", "replace"))
        except ProbeError as exc:
            observations.append(_declared_path(Observation.unreachable(
                target, observed_at, observer, "unparseable-probe-output",
                detail=str(exc)[:200], run_id=run_id), defect))
            continue
        observations.append(_declared_path(
            Observation.from_payload(target, payload, observed_at, observer, run_id=run_id),
            defect))

    counts = {outcome: sum(1 for o in observations if o.outcome == outcome)
              for outcome in ("observed", "partial", "unobserved")}
    run = RunRecord(run_id=run_id, observed_at=observed_at, observer=observer,
                    targeted=len(targets), observed=counts["observed"], partial=counts["partial"],
                    unobserved=counts["unobserved"], complete=counts["unobserved"] == 0)
    if store_path:
        ObservationStore(store_path).append([run] + observations)
    return run, observations


# --- the store and staleness ---------------------------------------------------------------------

class ObservationStore:
    """Append-only. Every write is an append; no write path opens the file for truncation."""

    def __init__(self, path: str) -> None:
        self.path = path

    def append(self, records: Sequence) -> int:
        """Append records, skipping any the store already holds.

        Idempotent per run, so a retried or replayed run cannot double-count itself. A run's records
        leave in **one** write on an `O_APPEND` descriptor, flushed to disk: ADR 0004 forbids a
        partially written run, and writing record-by-record left a crash window in which half a run
        was on disk and a torn final line blocked every later run.
        """
        parent = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(parent, exist_ok=True)
        existing = self._known_keys()
        batch = []
        for record in records:
            body = _body(record)
            key = _record_key(body)
            if key in existing:
                continue
            existing.add(key)
            batch.append(json.dumps(body, sort_keys=True) + "\n")
        if not batch:
            return 0
        payload = "".join(batch).encode("utf-8")
        descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            written = 0
            while written < len(payload):
                written += os.write(descriptor, payload[written:])
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return len(batch)

    def _lines(self) -> List[str]:
        if not os.path.isfile(self.path):
            return []
        with open(self.path, encoding="utf-8") as fh:
            return [line for line in fh if line.strip()]

    def _known_keys(self) -> set:
        """Keys the store holds, tolerating a torn final line.

        A torn line is corruption and `read()` says which line it is, but it must not make the store
        permanently unwritable: the collector would never be able to record anything again.
        """
        keys = set()
        for line in self._lines():
            try:
                keys.add(_record_key(json.loads(line)))
            except json.JSONDecodeError:
                continue
        return keys

    def read(self) -> List[dict]:
        records = []
        for number, line in enumerate(self._lines(), start=1):
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ProbeError(f"{self.path} line {number} is not readable JSON: {exc}") from exc
        return records

    def runs(self) -> List[dict]:
        return [r for r in self.read() if r.get("kind") == "run"]


def _body(record) -> dict:
    """One serialisation path for every record, whether it is a dataclass, a dict or a line.

    Going through `to_json()` matters: `RunRecord.to_json` adds the computed `reached`, so reading
    `__dict__` instead stored a run record missing a field its own JSON carries.
    """
    if isinstance(record, str):
        return json.loads(record)
    if hasattr(record, "to_json"):
        return json.loads(record.to_json())
    return dict(record)


def _record_key(record: dict) -> str:
    if record.get("kind") == "run":
        return f"run:{record.get('run_id')}"
    return f"observation:{record.get('run_id')}:{_identity_key(record)}"


def _identity_key(record: dict) -> Optional[str]:
    target = record.get("target") or {}
    machine = record.get("machine") or {}
    return machine.get("serial") or target.get("serial") or target.get("host")


def staleness(observation, now: str) -> Optional[int]:
    """How old an observation is, in seconds, from its own timestamp."""
    body = _body(observation)
    observed = _epoch_of(body.get("observed_at"))
    reference = _epoch_of(now)
    if observed is None or reference is None:
        return None
    return reference - observed


def latest(hostname: str, records: Optional[Sequence] = None, store_path: Optional[str] = None,
           now: Optional[str] = None, max_age: int = 3600) -> Optional[dict]:
    """The most recent reading for one machine, with its age (the spec's `latest(hostname)`).

    Returns None when nothing has been observed for it, which is not the same answer as an
    observation that says the machine was unreachable.
    """
    if records is None:
        records = ObservationStore(store_path).read() if store_path else []
    now = now or datetime.now().astimezone().isoformat(timespec="seconds")
    for entry in latest_per_machine(records, now=now, max_age=max_age).values():
        observation = entry["observation"]
        names = {observation.get("target", {}).get("host"),
                 (observation.get("machine") or {}).get("hostname")}
        if hostname in names or str(hostname) in {k for k in names if k}:
            return entry
    return None


def latest_per_machine(records: Sequence, now: str, max_age: int = 3600) -> Dict[str, dict]:
    """The newest observation per machine, with its age and whether that age is too old to trust."""
    latest: Dict[str, dict] = {}
    for record in records:
        body = _body(record)
        if body.get("kind") == "run":
            continue
        key = _identity_key(body)
        if key is None:
            continue
        current = latest.get(key)
        if current is None or (body.get("observed_at") or "") > (current["observation"].get(
                "observed_at") or ""):
            latest[key] = {"observation": body}
    for key, entry in latest.items():
        age = staleness(entry["observation"], now)
        entry["age_seconds"] = age
        entry["stale"] = age is None or age > max_age
    return latest
