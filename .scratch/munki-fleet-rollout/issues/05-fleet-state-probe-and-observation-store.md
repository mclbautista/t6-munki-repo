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

## Two-axis code review, and what it found

`git diff 035e4a0...HEAD` was reviewed on both axes (standards + spec). Every finding is listed with
what happened to it; the tests that pin them are in `tests/test_probe_review.py` (13 tests).

**Defects found and fixed**

| finding | fix |
|---|---|
| `--observer` defaulted to `None`, overriding the module default, so a default CLI run wrote `"observer": null` — criterion 2 not met on the default path | the CLI passes `DEFAULT_OBSERVER` when no observer is given; a test runs the command and reads the store back |
| A report with no `serial_number` produced `outcome="observed"` with `machine=None`, and the command that printed it **crashed**; `latest_per_machine` keyed it by hostname — criterion 2's "never a name alone" | such an observation is `partial` with reason `no-serial`; the state is kept because it is real, the outcome is not `observed` because it cannot carry identity |
| `--local` was inert (`build_runner` computed, never used) and its help text lied | flag and dead code removed |
| `--local-host` matched the target's *name* while the runner is handed the *address*, so the local machine was silently probed over ssh | matched on name and address; a test asserts a local run |
| `_inventory_targets` read `entry["host"]` from `known_absent`, whose key is `probe_hostname` — so **the pilot `Cyrils-Mac-mini` was silently dropped from the fleet run**, the one machine the evidence observed | reads `probe_hostname`/`name`; a test uses a real-shaped inventory |
| `append` wrote record-by-record, so a crash could leave half a run — ADR 0004 forbids a partially written run — and a torn final line made `read()` raise, which made `append()` (which read first) **permanently unwritable** | one `write` per run on an `O_APPEND` descriptor, `fsync`ed; keys read tolerantly; `read()` still raises and now **names the bad line** |
| Idempotency was reachable only from tests: `cli probe` never passed a `run_id`, so every rerun got a fresh uuid | default `run_id` is deterministic from the observation time and observer, so a same-second retry is idempotent; a replayed run writes 0 |
| `last_check` had a time but no **result** (criterion 1) | `result` is computed (`clean` / `warnings` / `failed`) and recorded |
| Two serialisation paths: `RunRecord.to_json()` carried the computed `reached`, the store wrote `__dict__` without it | one path: `_body` goes through `to_json()` |
| A malformed `observed_at` crashed `summarise` (None arithmetic) — the reviewer's "latent" finding, hit by the first test written against it | both epochs guarded; pinned by a test |
| Criterion 7 wanted recorded payloads for an unreachable machine and a stale observation; only the healthy one was recorded | `tests/fixtures/probe/recorded-run-records.jsonl` — the **verbatim store** from the live run, replayed in tests |
| `probe_client.sh` and the collector each hard-code the version string | a test asserts the script declares `PROBE_VERSION` |

**Left as judgement calls, deliberately**: the `partial` outcome and the extra fields
(`manifest_lookups`, `run_type`, `source_age_seconds`) are additions the criteria don't literally name
— `partial` exists because a machine with broken Munki is neither healthy nor unreachable, and the
fields are named by criteria 1 and 3. Repeated `kind == "run"` checks, the target as a bare dict and
the outcome vocabulary as bare strings are accepted for now; consolidating them is a refactor with no
behaviour behind it, and the ticket is not the place.

**The spec's named interface**: `latest(hostname)` is implemented. The spec's
`observe(targets) -> ObservationRun` is `probe_run(targets) -> (RunRecord, [Observation])` — the split
is deliberate, because a run's completeness and its per-machine observations are *different records*
in the store, and a wrapper returning both would hide that behind one object. Recorded as a
deviation rather than silently ignored.

## COLLISION: a second implementation of this ticket exists in the worktree

Discovered during the review: an **untracked, uncommitted** implementation of this same ticket sits
in the working tree — `munki_fleet/observe.py` (38 KB), `tests/test_observe.py` (23 KB),
`tests/fixtures/munki/`, and a **SQLite** store at `data/observations.db` with matching `.gitignore`
lines. It was written at the same time as the committed implementation (timestamps within a minute).

Two implementations of one ticket is an architecture decision, not a merge detail, and it is Cyril's:

- This one is committed (`fe3e05c`), reviewed on both axes, and verified live against a real machine.
- The other is untracked — which also means **it is not backed up by anything**, and it stores fleet
  state *inside the checkout* rather than on the admin workstation ADR 0004 names.
- Neither may be merged into the other silently. Whichever loses, the losing work should be kept
  deliberately rather than deleted.

**Recommendation:** decide which implementation the project keeps before either session writes more
observation code, and have the other session commit its work (or Cyril parks it) so it is not lost.
I have not touched those files.

### Resolution, same evening

That session deleted its version — `munki_fleet/observe.py`, `tests/test_observe.py`,
`tests/fixtures/munki/` and `data/observations.db` are gone from the tree, and its `.gitignore` lines
with them. **Only the committed implementation remains**, so there is one observation store again and
no decision is outstanding.

Recorded because the cost is real: the deleted version had never been committed, so its 38 KB of code
and ~50 tests are **not recoverable from Git** — they exist only in that session's own history. Which
implementation was better is now unanswerable from the repository. That is the hazard of untracked
work, and it is the second collision in this repo where a session's work was invisible to the other
until it was too late to compare it.

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
