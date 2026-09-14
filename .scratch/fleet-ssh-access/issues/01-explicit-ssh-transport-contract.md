# 01: Resolve observation targets through an explicit SSH transport contract

**What to build:** The collector observes a machine through an explicit, non-secret SSH access record rather than assuming the inventory address is also a complete login path. The complete path is proven on the admin workstation using its existing working access: resolve target, connect, run the read-only Munki probe, append the observation, and read it back.

**Blocked by:** None (can start immediately)

**Status:** done (2026-09-14)

**Claimed by:** hermes-desktop (Cyril's Mac mini, /Users/cyrilbautista/Projects/t6-munki-repo) 2026-09-14T21:22+0800

**Boundary:** This ticket installs no keys, enables no services, and changes no client or admin-workstation authentication settings. Nothing was installed, enabled or changed: the one path it exercises already worked.

## What was built

| file | what it now does |
|---|---|
| `munki_fleet/access.py` | The declaration and its two grades of error. `AccessMap.load(path)`, `AccessMap.resolve(target) -> Resolution`, `resolve_targets(targets, access_map) -> (targets, defects)`, `AccessRecord`, `AccessDefect`, `Resolution`. Reads a file, returns dataclasses, opens no connection. |
| `data/ssh-access.json` | The committed map (one record: `Sixto-5` → `t6-mac-mini`). Non-secret by construction — the destination grammar is `[user@]host`, so a port, a path, a space or a `user:password@host` is refused rather than stored. |
| `munki_fleet/probe.py` | `probe_run` travels to `target["ssh_destination"]` when one is declared, and to the inventory address only when none is. A blocked target is recorded `unobserved` with the defect kind and is never contacted. Every reading from an undeclared path carries that fact in `problems`. |
| `munki_fleet/cli.py` | `probe --access-map PATH` (default `data/ssh-access.json`; a map named explicitly that cannot be read refuses the run, exit 2) and `--limit N`; the access summary and the defect list are printed before the run; `observations` now prints `problems=` so the operator view distinguishes a reading from a verified-access reading. |
| `CONTEXT.md` | **Access record** and **Access map** added to the glossary. |

### Two defects found by driving the entry point, not by the tests

| defect | what it was | fix |
|---|---|---|
| `--from-inventory` could not run at all | `cmd_probe` read `args.limit` and the parser defined no such option, so the documented command died with `AttributeError: 'Namespace' object has no attribute 'limit'` before it probed anything. Every module-seam test for the probe was green through it. | `--limit N` added to the parser; `test_the_probe_command_drives_the_inventory_and_the_access_map` drives the command |
| a timeout stored 200 characters of heredoc | `default_ssh_runner` reports a timeout as `ssh timed out after Ns: <command>`, and for the probe that command is the entire script — so each unreachable machine stored and printed a script tail as its "reason" | `probe._transport_message` keeps the transport's message and names the script as `<the probe script>` |

The first was pre-existing and unreported: nothing had ever run `--from-inventory`, which is why the
2026-09-13 fleet sweep in `docs/evidence/05-fleet-reachability-sweep-2026-09-13.txt` was produced by a
"parallel implementation that has since been parked". A wiring audit of the whole CLI (every
`args.<name>` read against every argparse dest) finds exactly this one miss; `args.func` is set by
`set_defaults` and is the expected second hit.

## The judgement call, recorded rather than left implicit

Criterion 3 names four states of a record. Three of them are **refused**; two are **reported and
proceeded past**. The split is deliberate and was decided with Cyril on 2026-09-14:

- **malformed / duplicated / serial-mismatched** — the declaration exists and cannot be trusted, so
  the machine is **not contacted**. Contacting it by the undeclared address instead is precisely the
  silent fallback this ticket exists to remove, and a fallback that happens to work is how an
  unverified login becomes fleet state.
- **missing** — decided as *probe by the inventory address and keep the transport's own reason*. A
  map that is absent means no access has been declared yet, and refusing to run would report nothing
  about the fleet. The reading is real state, so it stays `observed`, and `problems: ["no-access-record"]`
  travels with it; the `observations` line prints `problems=` so the operator view cannot show it as a
  declared path. The residual gap, stated plainly: **`outcome` alone does not distinguish a
  declared-path reading from an undeclared one — `problems` does.** Any later consumer asking that
  question must read `problems`, not `outcome`.

## Acceptance criteria

- [x] An observation target can declare its SSH destination separately from its inventory address, machine name, and serial; no credential or private-key material is stored in the repository or observation store.
  - The target carries `ssh_destination` (address, name and serial untouched); the destination is recorded on the reading's `target`, so which path produced a reading is provenance rather than assumption. The grammar `[user@]host` refuses a credential-bearing or port-bearing destination, and a test asserts it (`test_a_malformed_record_blocks_the_machine_it_names[a destination carrying a credential]`). The live record (evidence section 6) carries `"ssh_destination": "t6-mac-mini"` and nothing else from the map.
- [x] Inventory-driven probing uses the explicit SSH destination when one is present and does not silently fall back to `t6@<primary_ip>` for a target that requires an access record.
  - `test_the_probe_travels_to_the_declared_destination_not_the_inventory_address` asserts the runner is handed `t6-mac-mini`, not `192.168.88.151`; `test_a_blocked_target_is_recorded_unobserved_and_never_contacted` asserts the runner is not called at all. No code path composes `user@address`: the destination is passed to `ssh` verbatim, or the target is not probed.
- [x] A missing, malformed, duplicate, or serial-mismatched access record is reported deterministically and cannot produce a compliant-looking observation.
  - *malformed*: five shapes pinned, including a misspelled field and `t6:hunter2@192.168.88.151`; *duplicate*: two records naming one machine are refused as ambiguous; *serial-mismatch*: the defect names both serials. All three block and yield `unobserved` with the defect kind — never `observed`.
  - *missing*: a map named explicitly that cannot be read exits 2 having written nothing (`test_the_probe_command_refuses_an_unusable_access_map`); the default map being absent prints `no-access-map` per machine and tags each reading (`test_an_absent_default_map_is_reported_and_the_readings_say_the_path_was_undeclared`); a machine with no record is tagged `no-access-record` and the flag is visible in the operator view (`test_the_operator_view_shows_why_a_reading_is_not_a_declared_path`). The reading stays `observed` because the state is real — see *The judgement call* above.
  - **Where the flag is and is not read today** (reproduced by a review, kept as a finding in *Left open*): `alerting.py:342` and `toolchain.py:85` branch on `outcome` and never read `problems`. Both ask what a machine *runs*, and the state they read is real whatever carried it, so they are right to ignore the flag — but it means nothing yet surfaces access *coverage* as a condition.
- [x] Existing targets without an access record retain an explicit unobserved result with the transport reason preserved; they are never omitted from run completeness.
  - Live: 16 ssh targets, 1 with a declared destination, and the run records `targeted 17, reached 2, unobserved 15` with `complete: False`. Each unreachable machine keeps the transport's own message (`Connection refused`, `Permission denied (publickey,password,keyboard-interactive)`; for a timeout `ssh timed out after 6s: <the probe script>`, where the script embedded in the transport's message is replaced rather than quoted) — evidence section 4.
  - **What this criterion does *not* say**, because a review read it as an absolute: a machine with no record that *does* answer on its inventory address is not forced to stay unobserved. It is probed, its real state is recorded, and the reading carries `problems: ["no-access-record"]`. The criterion is about the existing fleet — which does retain an unobserved result, 15 of 17, with each reason preserved — not about a machine that happens to be reachable by an undeclared path.
- [x] Tests cover an SSH alias, a distinct username/destination, an absent mapping, a serial mismatch, and proof that secrets are neither required in nor written to repository data.
  - Alias `t6-mac-mini`, `t6@192.168.88.175`, bare host `192.168.88.175` (one parametrized test); absent record, absent map, duplicate, malformed and serial mismatch as above; `test_the_committed_access_map_is_readable_and_carries_no_credential` reads `data/ssh-access.json` itself and asserts every destination matches the grammar and no value contains `:`, and the credential-shaped destination is refused by the parser.
- [x] A live run reaches `Sixto-5` through the already-working `t6-mac-mini` access path, appends an observation to an explicitly named store outside the checkout, and reads back the matching serial, resolved manifest, and observation timestamp.
  - Run `2026-09-14T21:28:24+08:00/0bf01128` and the fleet run `2026-09-14T21:28:25+08:00/6927dd96` both reached it; the read-back gives serial `C07D317NPJJ7`, `manifest=Sixto-5`, `pending=0`, `observed_at 2026-09-14T21:28:25+08:00`, store `/Users/cyrilbautista/.munki-fleet/observations.jsonl` (outside the checkout). Evidence sections 3–6.
- [x] The full test suite passes, and the ticket records the exact live command, system, observation-store location, and returned result.

## Verification

Suite, run bare so pytest's own status is the one that counts (2026-09-14, `/usr/bin/python3`,
Python 3.9.6, pytest 8.4.2, checkout at the commit that adds this work):

```
$ /usr/bin/python3 -m pytest
288 passed in 0.68s          pytest_exit=0
```

29 of those are this ticket's across its two commits: the same command in a detached worktree at the
commit before both (`35f43b2`) reports `259 passed in 0.88s`, and the pre-review commit reported
`287 passed`.
Two sensitivity checks, both reverted byte-for-byte afterwards (`sha256` compared): `blocks=True` →
`blocks=False` on the malformed branch fails 5 tests, and dropping `ssh_destination` from
`probe_run`'s address choice fails `test_the_probe_travels_to_the_declared_destination_not_the_inventory_address`.

Live, on Cyril's Mac mini (`192.168.88.202`, `Cyrils-Mac-mini`), from the checkout:

```
$ python3 -m munki_fleet.cli probe --store ~/.munki-fleet/observations.jsonl \
    --access-map data/ssh-access.json --machine 192.168.88.151@Sixto-5:C07D317NPJJ7
access: 1 of 1 ssh target(s) have a declared destination (data/ssh-access.json)
run 2026-09-14T21:28:24+08:00/0bf01128
  targeted 1, reached 1 (observed 1, partial 0), unobserved 0
  complete: True
    Sixto-5                      C07D317NPJJ7   manifest=Sixto-5 pending=0 rejections=0
  appended to /Users/cyrilbautista/.munki-fleet/observations.jsonl
exit=0

$ python3 -m munki_fleet.cli probe --store ~/.munki-fleet/observations.jsonl \
    --access-map data/ssh-access.json --from-inventory data/machines.json \
    --local-host Cyrils-Mac-mini --timeout 6
access: 1 of 16 ssh target(s) have a declared destination (data/ssh-access.json)
  no-access-record: no access record for '201-Bay-01-Mac-Pro'          ... (15 machines)
run 2026-09-14T21:28:25+08:00/6927dd96
  targeted 17, reached 2 (observed 2, partial 0), unobserved 15
  INCOMPLETE: some targets were not observed
    Cyrils-Mac-mini              RWJ57V9PW4     manifest=site_default pending=0 rejections=0
    Sixto-5                      C07D317NPJJ7   manifest=Sixto-5 pending=0 rejections=0
    ... 15 machines UNOBSERVED with the transport's own reason
exit=0
```

Full capture, including the store before and after, the verbatim Sixto-5 record and the operator
view: `docs/evidence/01-ssh-access-live-run-2026-09-14.txt`.

**No system change was made.** No key was installed, no Remote Login was enabled, no client was
written to. The store went from 23 records to 43 across the runs captured here (evidence sections 2
and 6) and to 47 after the post-review run (section 9); nothing was rewritten, because the store is
append-only and every run in it is a real observation of the fleet.

### What the first honest fleet reading already shows

Read on the same pass, recorded here because it is what the transport contract was for:

- **`Sixto-5` resolves its own machine manifest** (`Sixto-5`, not `site_default`). That is
  machine-level evidence for ticket 06 criterion 1, which was configuration-only before today: the
  admin workstation genuinely stops falling back. Ticket 06's criteria 4, 5 and 6 need the other
  machines, which is ticket 02 of this set.
- **`Cyrils-Mac-mini` still resolves `site_default`**, as ticket 07's blocker 1 records.
- **The pilot `202-TOC-M4-Max` refuses the undeclared path** — `cyrilbautista@192.168.88.182:
  Permission denied (publickey,password,keyboard-interactive)` — which is the state ticket 02
  authorises fixing.
- **5 of the 26 optional items cannot install on the Intel admin workstation.** Four carry
  `supported_architectures: ["arm64"]` (CineCred, Stow, FrameioDrive, ShutterEncoder) and one,
  OnyX, carries `minimum_os_version: "26.0"` against the machine's 15.7.1. All five are correctly
  filtered, and Munki reports each as `Could not process item X for optional install. No pkginfo
  found in catalogs: testing` — the message that reads like a missing pkginfo and is not. Not this
  ticket's defect; recorded because it is the first machine-level reading of ticket 08's policy.

## Review dispositions (two axes, 2026-09-14)

Reviewed as `git diff 8e10127...HEAD` on both axes by two read-only parallel sub-agents, each given
the ticket at its committed revision (`git show 78b8708:<this file>`) and told not to stage, commit
or edit anything. Every finding is adjudicated below; the fixes are in the review commit.

**Spec axis**

| finding | disposition |
|---|---|
| criterion 4 "not met as written" — a reachable machine with no record yields `observed`, so no explicit unobserved result is retained | **declined as a criterion miss; accepted as an imprecision in the disposition.** The criterion says *existing* targets, and those do retain an unobserved result with the reason preserved (15 of 17, live). What it does not guarantee is that a no-record machine which happens to answer on its address stays unobserved; that reading is real state. The disposition above now states the boundary instead of implying an absolute. |
| criterion 3 "partial" — `alerting.py:342` and `toolchain.py:85` branch on `outcome` and never read `problems` | **reproduced and accepted, kept open.** Both consumers ask what a machine *runs*, and the state they read is real whatever path carried it, so changing them would be wrong. The gap is that access *coverage* is not surfaced anywhere; it belongs to the access rollout and is recorded in *Left open*. |
| "*keeps the transport's own message verbatim*" overclaims, because `_transport_message` substitutes the embedded script and keeps one line | **accepted; the disposition was corrected rather than the code.** The recorded reason is the transport's own message; for a timeout the command inside it is replaced by `<the probe script>`, which is paraphrase. The criterion's disposition now says exactly that. |
| false count: "gained 40 records (23 → 43)" — 43 − 23 is 20 | **fixed.** Both numbers are the ones the capture prints; the sentence now quotes the pair rather than an arithmetic slip. |
| scope creep: `--limit N` | **accepted, answered by decision.** The defect was that `cmd_probe` read a value the parser never defined; the two repairs were to delete the parameter or to wire it. Wiring it is the smaller blast radius and the access rollout needs a bounded first run, so it is now exercised live — evidence section 8 (`--limit 1` bounds the inventory to one machine). |
| scope creep: `Deps.probe_runner` | **declined.** `cli.py` documents `Deps` as the injection seam for tests; without it no CLI test can drive `probe` without contacting live machines, and driving that command is what found the two defects recorded under *What was built*. |

**Standards axis** (all judgement calls; no documented-standard violation was found)

| finding | disposition |
|---|---|
| `queue = iter(resolved)` merged resolved targets back by position, re-applying a predicate (Mysterious Name) | **fixed.** `resolve_targets` takes `skip=` and passes those targets through untouched; the CLI merges nothing. Test: `test_a_machine_probed_locally_needs_no_access_record`. |
| `_declared_path(observation, defect)` — the name says "path", the body notes a defect (Mysterious Name) | **fixed** by renaming to `_note_access_defect`. The mutate-and-return shape stays: all four call sites append its result. |
| `access_defect` re-spelled `AccessDefect`'s three fields as a dict (Primitive Obsession / Data Clumps) | **fixed.** One conversion, `AccessDefect.as_target_field()`, because the target dict is what lands in the JSON store. |
| `unavailable(self, target)` never read `target` (Speculative Generality) | **fixed.** No-argument, with the reason for the shape documented. |
| the same map-writing helper in three test files; `import json` re-imported inside five test functions | **fixed.** One `access_map` in `tests/conftest.py` — where this repository's shared doubles already live — and the import hoisted. |
| `[:200]` repeated across four `probe.py` sites | **fixed.** `DETAIL_LIMIT` and a single `_detail()` truncation. |

One finding of my own, from reading the capture back: the section-8 listing was truncated with
`head`, which cannot support the absence it claimed about the local machine's flag. Section 9 appends
the complete read-back rather than editing section 8.

## Left open deliberately

- Nothing in this ticket observed any machine other than `Sixto-5` and this workstation, so no
  criterion here claims otherwise. Tickets 02–04 carry the access changes, each behind an approval.
- The store still lives on Cyril's Mac mini; moving the authoritative writer to the admin
  workstation is ticket 05 of this set, and ADR 0011 is why the two are different machines.
- `--local-host` is the transport declaration for a machine probed without ssh, so the map
  deliberately has no record for `Cyrils-Mac-mini`. That is a decision, not a gap.
- **Access coverage is not an alertable condition.** `alerting.py:342` and `toolchain.py:85` read
  `outcome`, so a fleet where 15 of 17 machines have no declared path reports fewer readings and
  nothing else. The flag exists in the record and in `observations`, and no consumer asks the access
  question yet. Tickets 02–04 of this set are where coverage becomes a number worth reporting, and
  the condition belongs there rather than here: this ticket's job was to make the undeclared path
  visible, not to make the coverage alert.
