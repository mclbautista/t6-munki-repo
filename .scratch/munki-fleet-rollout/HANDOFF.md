# Where this stopped, and what is next

Written 2026-09-13 at the end of the session that took the project from an unreviewable NAS directory
to a Git-owned, published, verified repository. Every claim below was read back from the system it
describes; anything unverified is marked as such.

## State at the stop

| thing | state | how it was checked |
|---|---|---|
| Repository | `dfce5a2` on `main`, remote verified | `git ls-remote` compared to `HEAD` |
| Tests | **212 passing** | `python3 -m pytest`, and the pre-commit hook runs it on every commit |
| Served catalog | **28 items, 28 unique names**, `catalogs/production` correctly absent (HTTP 404) | fetched over HTTP from the NAS |
| Rebuild | **byte-reproducible** — a fresh build equals what is served, 2/2 catalogs identical | `munki_fleet.cli catalog-compare` |
| Drift | 3 findings, all pending one approval (below) | `munki_fleet.cli check`, exit 1 |
| Integrity | no findings | same check |
| Payloads | 28 referenced, **0 orphans**, 2.2 GB reclaimed | `payload-orphans` |
| Observation store | 1 machine observed, 1 unreachable, staleness computed | `munki_fleet.cli observations` |

## The next step

**Ticket 13 (repository network restriction)** is the next ticket with no blockers. Two others are
also startable now that ticket 05 exists: **14 (fleet view UI spec)** and **15 (alerting)**.

Before starting anything new, **one approval unblocks three tickets at once**:

1. **Approve ticket 06's two manifests** (`303A-Mac-Mini-M4-Pro`, `Sixto-5`). That single publish
   lands them *together with* the suspension of the forced core (ticket 08), because a publish is
   all-or-nothing — and landing them together is the safe order: those two machines then inherit
   0 forced / 26 optional instead of force-installing up to 26 items on first resolution.
   **Until it is published, `manifests/all` still force-installs 26 items on the fleet** (verified
   against the served file, not from memory).
2. **Ticket 10's toolchain install** on the admin workstation (6.6.0.4686 → 7.3.x), per ADR 0010.
   The plan, the before/after harness and the rollback versions are in the ticket.
3. **`Cyrils-Mac-mini` still has no machine manifest.** With the forced core suspended this is now
   consequence-free — it would give the machine its own identity instead of falling back to
   `site_default` — and it is the last blocker on ticket 07's initial promotion (26 items, 27
   manifests).

Smaller, not blocking: the three stray empty directories in the `Web` share root (`catalogs/ icons/
manifests/`) are a NAS deletion awaiting a yes.

## What a successor must not redo

- **Do not hand-edit the NAS.** It is a publish target. `publish` pushes the checkout and refuses an
  undeclared change; `reconcile` removes target-only files, declared and hash-verified against the
  withdrawal record; `check` reports drift read-only. Hand-editing it is the drift this project
  exists to make visible.
- **Do not run `pytest | tail`.** It reports the pipe's status, not pytest's, and a red suite was
  committed twice that way. `.githooks/pre-commit` now refuses it; `SKIP_TESTS=1` exists for work in
  progress and must be explained in the message.
- **Do not `git add -A` in this repository.** Another session works the same tree; a blanket add
  swept its in-flight files into an unrelated commit once (annotated with a git note).
- **A publish is all-or-nothing.** Two sessions' changes cannot be published separately, which is why
  the approval above matters more than the ticket it belongs to.
- **`data/promotions.jsonl` does not exist yet** and that is correct: no promotion has been recorded,
  because the initial promotion is the approval above.

## Already decided, so nobody re-opens it

ADR 0001–0010, and specifically: metadata is Git-owned and published over SSH (0001); the forced core
is suspended and empty for now (0002 amendment); two rings with a pilot of `202-TOC-M4-Max` and
`Cyrils-Mac-mini` (0003, `data/rings.json`); one deterministic observation writer, LLM renders only
(0004); no MDM, ever (0005); the store is backed up off-NAS with a restore drill (0006, 0012);
network restriction by path rather than a firewall on the NAS (0007, 0013 decision); agent autonomy
with approval boundaries (0008); a publish must declare what it changes (0009); the catalog builder
must share the clients' major version (0010, proposed).
