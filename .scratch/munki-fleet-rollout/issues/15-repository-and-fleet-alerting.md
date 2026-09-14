# 15: Alert on repository and fleet problems through Kulit, and stay silent otherwise

**What to build:** Repository drift, integrity failures, and fleet compliance regressions reaching Cyril through the alert transport T6 already uses, with enough context to verify each claim and with no message when nothing is actionable.

**Blocked by:** 03, 05

**Status:** ready-for-human — the decision half is implemented and verified against the live
repository and the recorded fleet; **delivery is not wired, and that is the remaining decision**
(ADR 0011, proposed). Nothing is delivered to anyone yet: see the criteria dispositions below.

**Three things are open, not one:**

1. **The delivery transport** (ADR 0011 needs Cyril's acceptance; then the Kulit-side monitor and the
   launchd job).
2. **Blocker 05 is not complete.** It is `ready-for-human` — the observation store exists but only the
   collector's own machine is observable, which is why 15 of the 17 expected machines have never been
   observed and every one of them is a condition here. This ticket's criterion 6 cannot be finished
   until that is resolved.
3. **Criterion 6's live half also needs 06, 10 and 11** (machine manifests, toolchain, onboarding):
   a live *silent* cycle needs a fleet that is observed and in sync, which does not exist yet.

**Claimed by:** hermes-desktop (Cyril's Mac mini, /Users/cyrilbautista/Projects/t6-munki-repo) 2026-09-14T07:45+08:00

**Notes:** Freshness is part of the alert: failing to observe the fleet is itself an actionable condition, and a stale observation must never be alerted on as if it were current.

## What was built

- `munki_fleet/alerting.py` — the deterministic decision. `Condition` (one actionable fact, with a
  stable key and at least one source), `drift_conditions`, `integrity_conditions`,
  `observation_conditions`, `conditions`, `render` (one message per digest), the durable alert state
  (`load_state`/`save_state`), `actionable`, `read_receipts`, `write_message`, and `cycle`. It holds
  no credential, sends nothing, and touches no machine.
- `munki_fleet.cli alert` — one cycle for an operator: drift + integrity against the target, fleet
  conditions from the observation store against the committed inventory, one message or silence,
  and the delivery outcome read back. `--dry-run` decides and prints without writing.
- `tests/test_alerting.py` — 47 tests: the conditions, the message, the state machine, the command's
  wiring (a clean tree is silent and exits 0; a drifted one hands over one message with URLs; a dry
  run writes nothing; a failed receipt exits 1; a zero bound is refused; a state file or receipt log
  it cannot trust exits 3), and one test per review finding below.
- `docs/adr/0011-alert-decision-and-delivery-contract.md` (Proposed) — how the decision and the
  delivery relate, and why the contract is an outbox with receipts.
- `docs/evidence/15-alert-cycle-live-2026-09-14.txt` — seven captures against live state (a timed dry
  run, four real cycles, the state they left, and the duplicate-monitor check with its commands).

**What is *not* alerted on, and why:** pending-update counts and client warnings are recorded in an
observation but produce no condition, because no criterion here names them (spec stories 16 and 17
are served by the observation model itself, ticket 05). Promotion state is ticket 07's question. If
either is wanted as an alert, it is a condition added to this module and a criterion to point at.

### What is graded, and why

Every condition is ORANGE or RED, and nothing else is ever emitted:

| condition | severity | why |
|---|---|---|
| `drift:*` (a served file the checkout lacks, one it does not serve, differing bytes, unreadable) | RED | the served tree is not the reviewed tree, which is the hand-edit this project exists to make visible |
| `integrity:` payload_missing, pkginfo_missing, item_not_in_catalog, manifest_unresolved, catalog_unreadable | RED | an install that would fail, or a check that cannot be made |
| `integrity:` duplicate_name, catalog_membership_mismatch, catalog_entry_without_pkginfo | ORANGE | a client survives it, but what it receives stops being predictable |
| `fleet:unobserved`, `fleet:not-reached`, `fleet:stale`, `fleet:manifest-unexpected`, `fleet:rejection`, `fleet:uninventoried` | ORANGE | a machine that is unknown, unreachable, stale, not resolving its own manifest, rejecting an item, or not in the inventory |

Two invariants are enforced in code rather than promised in prose: a `Condition` cannot be
constructed without a reference, so an unverifiable claim cannot be sent; and a **stale reading
contributes only its staleness** — its resolved manifest and its rejections are not reported as
current fact.

## The decision that remains: who delivers

Everything up to the outbox is implemented and verified. What is *not* done is a transport, and the
options are not equivalent:

| option | what it means | why not simply choose it |
|---|---|---|
| **A. A monitor in Kulit, reading an outbox the cycle writes into Kulit's mounted `data` dir** | Kulit's process sends, exactly as `ingest_monitor.py` already does for the Ingest API; the munki side writes one message file and reads a receipt back | changes a live service (Kulit code + container restart), and that service is not this repository |
| B. A standalone sender on the host running the cycle, using Kulit's token | no change to Kulit at all | a second sender reading Kulit's credential; the ticket forbids a new sender, and it duplicates delivery outside the process that owns it |
| C. An HTTP intake on Kulit's dashboard | an obvious contract | turns a local operational surface into an API, which Kulit's own `CONTEXT.md` forbids |

**Recommendation: A**, as recorded in ADR 0011 with the paths, the receipt format, the monitor's
loop behaviour, the host that can actually run the cycle, and the failure modes. It needs Cyril's
acceptance because it changes a live service, picks deployment paths, and extends ADR 0008's autonomy
list by one write class; the launchd job and the Kulit-side change are the two things to authorise
together, since neither is useful alone.

## Verification

Live, 2026-09-14, read-only against the NAS and the recorded fleet
(`docs/evidence/15-alert-cycle-live-2026-09-14.txt`):

```
repository: drift missing on the target 2, only on the target 0, differing 1, unreadable 0; integrity 0 finding(s)
fleet: 17 expected, 2 reading(s) held, 2 stale
alert run 2026-09-14T07:55:46+08:00
  conditions: 19 actionable of 19 current
  message: alert-20260914T0755460800-7c7c6df0 (10 of 19 condition(s) rendered) -> /tmp/alert-outbox2/alert-….json
```

What the seven captures show, in order:

1. A dry run: the decision, the message, and nothing written (4.2 s wall clock, measured again at
   4.1–4.3 s over three runs for ADR 0011's cost claim).
2. Cycle 1 handed over **one** message for 19 conditions, with the body captured verbatim from the
   file: the repository conditions carry HTTP URLs
   (`http://192.168.88.188/MunkiRepo/manifests/all`), the fleet conditions carry the observation
   store path (with the run id for the conditions sourced from a *reading*, and the inventory row for
   the ones sourced from the *absence* of one).
3. Cycles 2 and 5: **silence** with 19 conditions current — no message handed over, exit 0.
4. Cycles 3–4: a failed receipt was recorded (`receipt: "failed"`, `failures: 1`, `delivered_at`
   null) and the run **exited 1**; a retry was then delivered, the previously elided 9 conditions
   became actionable and were carried in a second message, and by cycle 5 nothing was outstanding
   (`delivered 1, failed 0, pending 0, undelivered 0, superseded 0`). The *supersession* path — an
   unacknowledged message past its TTL — was **not** exercised live (it needs a wait longer than the
   ack TTL); it is pinned by a test instead.
5. Section 7: the duplicate-monitor check, with its commands (criterion 7).

Tests: `python3 -m pytest` on this tree → **259 passed**; 47 of them are this ticket's. A count is
true only of the tree it was run on.

## Two-axis review, and what it found

`git diff --cached 4865816` was reviewed on both axes (standards + spec), read-only, by two parallel
sub-agents. Every finding is listed with its disposition. Findings 1–4 were reproduced through a
public seam before being fixed, and each now has a test.

**Defects found and fixed**

| finding | what it was | fix |
|---|---|---|
| a severity escalation while a message was in flight was never delivered | the escalation was filtered out as in-flight, the stored severity was advanced anyway, and the in-flight message's receipt then recorded the *worse* severity as already notified | the stored severity is not advanced for a key whose message is in flight, so the escalation re-alerts once that message is acked (`test_an_escalation_while_a_message_is_in_flight_is_delivered_once_that_message_is_acked`) |
| one lost message reported failure forever | a receipt-less message past its TTL was re-listed as undelivered on every cycle, so `ok` was false for the rest of the state file's life and the only cure was deleting the state by hand | a message whose conditions a later message delivered is *superseded* and stops reporting (`test_a_message_superseded_by_a_delivered_retry_is_not_reported_undelivered_forever`) |
| an unreadable clock read as "in flight" | `--now` as anything unparseable made every age `None`, which meant pending, which meant `ok: true` — a lost alert reported as success | `now` is parsed and refused when unreadable; an age that cannot be established is undelivered, never pending (two tests) |
| the CLI's own refusal type was unhandled | a state file at another version, or a corrupt `receipts.jsonl` line, produced a traceback instead of a refusal | `cmd_alert` catches `AlertError`/`ProbeError` and exits 3 with the reason (two tests) |
| conditions elided by `--max-conditions` were recorded as notified | a 19-condition digest listed 10 and marked all 19 delivered, so 9 conditions were never shown to anyone and never sent again | the message records `rendered_keys`; a receipt marks only what was rendered, and the elided conditions are carried by the next cycle (live: cycle 4 carried the 9) |
| a duplicate key would be listed twice | two inventory rows for one machine (or a row with no identity) would produce the same condition twice in one message | `load_inventory` refuses a row with neither serial nor name, and two rows for one machine; `cycle` de-duplicates by key at the higher severity (three tests) |
| a receipt for a message the state does not hold was materialised into the ledger | a keys-less ledger entry that could never resolve and was re-created every cycle | such a receipt is reported as `stray` and changes nothing (test) |

**Corrections to the record, from the same review**

- "A silent cycle writes nothing" was wrong in three places (module docstring, ticket, and the ADR's
  cost sentence): a silent cycle **does** write the state file — that is what the next cycle's
  decision rests on — and hands over no *message*. Corrected in all three.
- The ADR claimed the cycle costs "one SSH round trip (~6s live) and reads two small files". It reads
  94 metadata files with one `stat` each; the measured wall clock is 4.1–4.3 s. Corrected, with the
  measurement cited.
- The ADR and `CONTEXT.md` said the alert state lives "on the admin workstation", which `CONTEXT.md`
  defines as `192.168.88.151` — a different machine from the one holding the checkout, the store and
  the Kulit container (`Cyrils-Mac-mini`, `192.168.88.202`). Both now name the host; the term itself
  is Cyril's to decide, and ADR 0011 records the divergence rather than editing ADR 0004 or
  `CONTEXT.md`'s definition.
- The ticket named a symbol (`AlertState`) that does not exist, and `alerting.py` re-exported
  `CatalogError` for a caller that does not exist. Both removed.
- ADR 0011 now states that adopting it extends ADR 0008's autonomy list, so that ADR 0008 can be
  amended in words on acceptance instead of being quietly outgrown.

**Left open deliberately, with the reason**

- The healthy period is exercised by tests, not live (criterion 6). The healthy *reading* in that
  test is synthesised — the recorded observation with its name and resolved manifest rewritten — and
  the test module says so; the failing half comes from the recorded store unmodified.
- The `partial` case (a machine reached but with no usable state) produces `fleet:not-reached`, the
  same condition as an unreachable machine, with the reason in the detail. Two conditions for one
  machine would be noise; if the distinction matters later, it belongs in the detail text and a
  criterion.

## Acceptance criteria

The criteria below are left exactly as written. What follows each is the disposition, so a gap is
visible rather than absorbed.

- [ ] Alerts are delivered through Kulit — the existing owner of T6 alert delivery — and not through a new sender or a second bot identity.
  - **NOT MET.** Nothing is delivered: the decision half is implemented, and the transport is ADR 0011's
    open decision. What the work does establish is that the design names no second sender and reads
    no credential — but the delivery itself does not exist yet, and this is the ticket's open item.
- [x] Only actionable, ORANGE/RED-level conditions trigger delivery; a healthy check produces no message at all, including no summary and no "no alert" filler.
  - Met in the decision layer — and note the honest scope: since criterion 1 is unmet, **no condition
    has ever triggered a delivered message**. Every condition is graded ORANGE or RED, `cycle` hands
    over nothing when nothing is actionable, and `render` refuses an empty digest. Asserted by tests
    and by two live silent cycles with 19 conditions current. A live *healthy* capture is not
    possible yet, for the reason under criterion 6.
- [x] Every alert includes the source it is grounded in and a direct link or path to that source, so the claim can be checked without asking.
  - Met: `Condition` refuses to exist without a reference; the live message carried HTTP URLs for
    repository conditions and the store path (with its run id where a reading is the source) for
    fleet conditions.
- [x] Alert state is durable across runs: a condition that persists does not re-alert every cycle, and a condition that clears resets the state.
  - Met: the state file survives cycles (live: `version 1 conditions 19 messages 3` after five
    cycles), a persisting condition is not re-sent while it is in flight or already delivered, and a
    cleared condition is forgotten so its return alerts again. Asserted by tests.
- [x] Delivery failure is visible: an alert that could not be delivered is recorded as undelivered, and the run does not report success.
  - Met for the cycle, on both paths: a **failed** receipt is consumed into the state (`receipt:
    "failed"`, `failures: 1`, `failed_at` set) and the run exits 1; a message nobody acknowledged
    within `--ack-ttl` is recorded **undelivered** (`undelivered_at` set, counted, retried), and a
    message superseded by a later delivery stops being counted. Recorded live with **hand-written**
    receipts, because there is no transport to write real ones.
- [ ] A healthy period and a failing period are both exercised, with the resulting (absent or present) messages recorded as evidence.
  - **PARTIAL.** The failing period is a live capture, and the absent-message half is live too (two
    silent cycles with 19 conditions current). What is missing is a live healthy *fleet*, and that is
    not this ticket's work: two files the target does not serve, one file differing, 15 machines
    never observed, one unreachable, one reading stale — tickets 05 (fleet access), 06, 10 and 11
    first. Left open rather than claimed.
- [x] The alerting path is verified to be the single authoritative one — any superseded or duplicate monitor for the same condition is identified and removed.
  - Met: the check found no other monitor and its commands are in the evidence file, so there is
    nothing to remove. The removal half has no subject today.

## Corrections

- None to the criteria' wording; the dispositions above carry the gaps. The ticket cannot move to
  `done` until criterion 1 is met (transport accepted and wired) and criterion 6's live half is
  possible, which needs blocker 05's fleet access resolved.
