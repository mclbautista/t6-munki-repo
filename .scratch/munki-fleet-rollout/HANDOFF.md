# Where this stopped, and what is next

Written 2026-09-14 at the end of the session that implemented ticket 15 (alerting) and left its
delivery as a decision for Cyril. Every claim below was read back from the system it describes;
anything unverified is marked as such.

The previous version of this file (written 2026-09-13 at head `08c2c78`) is superseded where it
disagrees: tickets 05, 09, 10 and 12 are unchanged, and 15 has moved from unstarted to
implemented-with-one-decision-open.

## State at the stop

| thing | state | how it was checked |
|---|---|---|
| Repository | `8b9b448` on `main`, pushed and read back | `git ls-remote origin refs/heads/main` == `HEAD` |
| Tests | **259 passing** (47 of them ticket 15's) | `python3 -m pytest`, run bare, and again in a detached worktree of the commit |
| Served catalog | **28 items, 28 unique names**, `catalogs/production` correctly absent (HTTP 404) | fetched over HTTP from the NAS, parsed with `plistlib` |
| Drift | 3 findings, all pending one approval: two manifests missing on the target (`303A-Mac-Mini-M4-Pro`, `Sixto-5`) and one file differing (`manifests/all` — the unpublished forced-core suspension) | `munki_fleet.cli check`, exit 1 |
| Alert decision | implemented and exercised live: 19 conditions from the real repository and the recorded fleet, one source-linked message, two silent cycles, a failed receipt recorded with exit 1 | `docs/evidence/15-alert-cycle-live-2026-09-14.txt` |
| Alert delivery | **not wired** — nothing is delivered to anyone | the receipt in that capture was written by hand; the ticket says so |
| Observation store | 1 machine observed, 1 unreachable, everything stale | `munki_fleet.cli observations` (ticket 05's state, unchanged) |

## The next step

**Decide who delivers the alerts (ADR 0011, Proposed).** Ticket 15 is implemented up to the outbox
and verified; the transport is the open item, and until it is accepted and wired, criterion 1 of that
ticket stays open and nothing reaches Cyril. The recommendation is option A — a second monitor inside
Kulit mirroring its existing `ingest_monitor`: read the outbox inside the container's already-mounted
`/data`, send through Kulit's own bot session, append a receipt the next cycle reads. Two things to
authorise together, since neither is useful alone: the Kulit-side monitor, and the launchd job that
runs `munki_fleet.cli alert` every 15 minutes. The cycle must run **on Cyril's Mac mini
(`192.168.88.202`)**, because that is where the checkout, the observation store and the container are
— see ADR 0011 on why that is not the machine `CONTEXT.md` calls the admin workstation.

Then, unchanged from the previous handoff and each still needing one approval:

1. **Approve ticket 06's two manifests** (`303A-Mac-Mini-M4-Pro`, `Sixto-5`). That single publish
   lands them *together with* the suspension of the forced core (ticket 08), because a publish is
   all-or-nothing — and landing them together is the safe order: those two machines then inherit
   0 forced / 26 optional instead of force-installing up to 26 items on first resolution. Until it is
   published, `manifests/all` still force-installs 26 items (re-verified this session: the served
   file differs from the checkout).
2. **Ticket 10's toolchain install** on the admin workstation (6.6.0.4686 → 7.3.x), per ADR 0010.
   The plan, the before/after harness and the rollback versions are in the ticket.
3. **`Cyrils-Mac-mini` still has no machine manifest.** With the forced core suspended this is
   consequence-free, and it is the last blocker on ticket 07's initial promotion (26 items, 27
   manifests).
4. **Ticket 13** (repository network restriction) has no blockers and its decisions are recorded
   (13A–13D: network segregation rather than a firewall, one subnet `192.168.88.0/24`, the negative
   case recorded as not verified, myQNAPcloud verified read-only). The remaining work is the
   network-path change itself, which needs approval, plus the evidence write-up.
5. **Ticket 14** (the fleet view's user-facing shape) needs the grilling session with Cyril. No
   implementation in that ticket; it produces a specification.

Smaller, not blocking: the three stray empty directories in the `Web` share root (`catalogs/ icons/
manifests/`) are a NAS deletion awaiting a yes.

## What a successor must not redo

- **Do not hand-edit the NAS.** It is a publish target. `publish` pushes the checkout and refuses an
  undeclared change; `reconcile` removes target-only files, declared and hash-verified against the
  withdrawal record; `check` reports drift read-only.
- **Do not run `pytest | tail`.** It reports the pipe's status, not pytest's. `.githooks/pre-commit`
  refuses it; `SKIP_TESTS=1` exists for work in progress and must be explained in the message. The
  hook is wired here (`core.hooksPath .githooks`), so it applies to every session working this tree.
- **Do not `git add -A` in this repository.** Another session works the same tree.
- **A publish is all-or-nothing.** Two sessions' changes cannot be published separately, which is why
  the approval above matters more than the ticket it belongs to.
- **Do not treat "the admin workstation" as the machine that runs the cycles.** `CONTEXT.md` defines
  it as the Mac Mini `192.168.88.151`; the checkout, the observation store and the Kulit container are
  on `192.168.88.202`. Verify which host before deploying anything (ADR 0011).
- **Do not wire a sender outside Kulit for ticket 15.** No second bot identity, no second reader of
  the token, no HTTP intake on Kulit's dashboard (Kulit's own `CONTEXT.md` forbids it). ADR 0011 has
  the rejected options and why.
- **`data/promotions.jsonl` does not exist yet** and that is correct: no promotion has been recorded,
  because the initial promotion is the approval above.

## Already decided, so nobody re-opens it

ADR 0001–0011, and specifically: metadata is Git-owned and published over SSH (0001); the forced core
is suspended and empty for now (0002 amendment); two rings with a pilot of `202-TOC-M4-Max` and
`Cyrils-Mac-mini` (0003, `data/rings.json`); one deterministic observation writer, LLM renders only
(0004); no MDM, ever (0005); the store is backed up off-NAS with a restore drill (0006, 0012);
network restriction by path rather than a firewall on the NAS (0007, 0013 decision); agent autonomy
with approval boundaries (0008); a publish must declare what it changes (0009); the catalog builder
must share the clients' major version (0010); **Munki decides alerts, Kulit delivers them, and the
outbox with receipts is the contract between them (0011, proposed — this is the open decision above)**.
