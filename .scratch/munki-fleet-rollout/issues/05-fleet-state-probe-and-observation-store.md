# 05: Deterministic per-machine state probe and an append-only observation store

**What to build:** The single authoritative record of what state each Mac is in: a deterministic probe of each machine's Munki client, written append-only with provenance, so that fleet state is read from a record with a known age instead of from a live sweep.

**Blocked by:** 04

**Status:** ready-for-human (implemented and verified on one machine; fleet access is the remaining
decision, below)

## What was built

- `munki_fleet/probe_client.sh` — the read-only client probe. No root, writes nothing, emits a
  line-oriented envelope whose sections are explicit, so a missing file, an empty file and a machine
  that could not be reached at all are three different answers.
- `munki_fleet/probe.py` — the collector: `parse_envelope`, `Observation`, `RunRecord`,
  `probe_run`, `ObservationStore`, `staleness`, `latest_per_machine`.
- `munki_fleet.cli probe` (appends a run) and `munki_fleet.cli observations` (read-only, per-machine
  age and staleness).
- `tests/fixtures/probe/healthy-envelope.txt` — the **verbatim output of the probe on
  `Cyrils-Mac-mini`**, not a payload written to match the parser, with its provenance in the
  fixture's `README.md`.
- 16 tests; full suite green.

**What the probe reads is Munki's own answer**: the client's `ManagedInstallReport.plist` plus the
tail of `ManagedSoftwareUpdate.log`. It does not re-implement install detection — a home-made check
is what produced five confident wrong "missing" items earlier the same day (see ticket 08).

### A bug the design caught

The first probe converted the report with `plutil -convert json`, which **cannot represent the
report's date objects and exits 0 while printing nothing** — so the whole report was silently lost.
Because the envelope distinguishes "report present but empty" from healthy, the collector wrote a
**partial** observation instead of a false healthy one. The probe now emits the report verbatim as
the XML plist Munki writes; the collector parses plist or JSON.

### Recorded gotcha, verified on the machine

The report's own `StartTime`/`EndTime` are **UTC** (`11:26:23`) while the log's timestamps carry the
local offset (`19:26:23.317+08:00`) for the same run. Both are recorded as given with their source
named, so nothing has to reinterpret them, and the file mtimes are recorded as epoch.

### The transport needs an address

`ssh 202-TOC-M4-Max` fails DNS outright: fleet machines are reachable by their `.local` mDNS names,
not by bare short hostname. The probe therefore travels by the inventory's `primary_ip` and records
the machine's name and serial. `--machine ADDRESS@HOST[:SERIAL[:NAME]]` names both.

## Verification

Live run, 3 targets on 2026-09-13 (`docs/evidence/05-observation-run.txt`):

```
run 2026-09-13T19:34:59+08:00/ba4fdd2a
  targeted 3, reached 1 (observed 1, partial 0), unobserved 2
  INCOMPLETE: some targets were not observed
    Cyrils-Mac-mini   RWJ57V9PW4  manifest=site_default pending=0 rejections=2
    202-TOC-M4-Max    UNOBSERVED   unreachable: Permission denied (publickey,password,...)
    Sixto-5           UNOBSERVED   unreachable: Permission denied (publickey,password,...)
```

The observed record carries `munki_version`, `manifest_name`, `pending_count`, `last_check`,
`architecture_rejections` (two real ones, with item, version, supported list and machine arch),
`warnings`, the three failed manifest lookups, and its provenance. Read two hours later the same
store reports all three **STALE** (`age=7200s`), and replaying a recorded run writes **0** records.

## The remaining decision: fleet access

Only the machine the collector runs on is observable today. The rest need SSH access, or a different
transport, and that is a real prerequisite rather than a detail:

- **Ticket 10 (toolchain alignment)** and **11 (client onboarding)** are where per-machine access
  belongs. Until then a fleet run is honestly 1 observed / 18 unobserved, which the run record states
  rather than hides.
- **Where the store lives** is a rollout decision too. ADR 0004 puts it on the admin workstation
  (`Sixto-5`); `--store` is deliberately **required** by the CLI so fleet state is never appended
  somewhere unintended, and the deployment path is recorded when the collector is deployed there.
- `unobserved` is not a failure of this ticket: it is the truthful answer, and the one the ticket
  exists to make impossible to mistake for compliance.

**Notes:** The store holds fleet state, not the fleet. It must not hold credentials, and it must not be a prerequisite for any Mac receiving software: if the observer is down, software delivery is unaffected.

## Acceptance criteria

- [ ] For each reachable machine the probe records: Munki tools version, resolved manifest name, pending update count, last check time and result, architecture rejections, and client warnings.
- [ ] Every observation carries the source's own timestamp, the observation timestamp, the observer identity and the machine's identity (serial) — never a name alone.
- [ ] A machine that cannot be reached produces an explicit unobserved record for that run; no code path can write a compliant-looking row for an unreached machine.
- [ ] The store is append-only: no run modifies or deletes a prior observation. Asserted by a test.
- [ ] Each run records its own completeness — how many machines were targeted, reached, and unobserved.
- [ ] Observation age is computed per machine and exposed as staleness, so a stale reading cannot be presented as current.
- [ ] Tests run against recorded fixture report payloads covering: a healthy machine, an unreachable machine, a machine with an architecture rejection, and a stale observation.
