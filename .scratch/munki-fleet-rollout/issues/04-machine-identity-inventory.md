# 04: One authoritative inventory of which Mac is which

**What to build:** A reconciled inventory of the fleet: every Mac's name, Munki short hostname, serial number, hardware UUID, architecture, and assigned role — cross-checked against the role matrix and the set of machine manifests, with every mismatch reported.

**Blocked by:** None (can start immediately)

**Status:** done (2026-09-13)

**Notes:** The live repository's manifest set is evidence of intent, not evidence of reality: a manifest existing for a hostname does not prove a machine with that hostname exists. Both directions must be checked.

## What was built

- `munki_fleet/identity.py` — stdlib only, and **no live machine and no live NAS is touched**: the ARD export, the manifest tree, probe results and the operational projection are all *file* inputs. A machine that has not been probed is a finding, never a guess.
- `tests/test_identity.py` — 36 tests against a trimmed ARD export fixture and a manifest tree generated per test.
- `tests/fixtures/ard/ard_system_overview_sample.txt` — the fixture, in the report's own format including its `Date Collected` comma quirk.
- `data/machines.json` — the inventory ticket 05 reads: 16 rows, 36 findings, `schema_version: 1`, and a provenance label on every field that could come from more than one source.
- Evidence and decision inputs, so the artifact is reproducible from the repository: `docs/evidence/04-ard-system-overview-2026-09-13.txt` (the export itself), `docs/evidence/04-probes-2026-09-13.json` (the two machines that could be probed directly), `docs/evidence/04-bays-projection-2026-09-13.json` (the `bays` projection as read; identity columns only), `docs/evidence/04-uuid-source-check-2026-09-13.txt` (the check that ARD's own UUID is not the hardware UUID, with its commands), and **`docs/role-matrix.csv`** (the recorded role matrix, filled in by Cyril on 2026-09-13).
- Entry point, and the run that produced the committed artifact:

  ```
  python3 -m munki_fleet.identity \
    --ard-export docs/evidence/04-ard-system-overview-2026-09-13.txt \
    --metadata-root . \
    --probes docs/evidence/04-probes-2026-09-13.json \
    --bays docs/evidence/04-bays-projection-2026-09-13.json \
    --role-matrix docs/role-matrix.csv \
    --known-absent "Cyrils-Mac-mini:Cyril's Mac mini is a fleet member (ADR 0004 names it among the
      three machines this project has touched) but has no row in the ARD export. Probed locally
      2026-09-13: serial RWJ57V9PW4, Mac16,10, macOS 26.6.2, LAN 192.168.88.202." \
    --out data/machines.json --summary

  → machines=16 manifests=16 export_date=2026-09-13 18:37
    probed uuid 1 | candidate uuid 10 | no uuid 5
    role matrix: 19 rows recorded
    orphan manifests 2 | unmanaged machines 2 | unassigned 0 | known absent 1
    findings: 36 — uuid-unverified 10, bays-difference 7, uuid-unavailable 5, bays-missing 5,
              name-difference 4, machine-without-manifest 2, manifest-without-machine 2,
              needs-record 1; role-mismatch 0, role-matrix-unknown-machine 0
  ```

## Acceptance criteria

- [x] Identity is sourced from the Apple Remote Desktop machine export (name, serial, UUID, MAC, OS version, known addresses); the source file used and its export date are recorded.
  - Source: the *System Overview Report* Cyril exported on 2026-09-13 18:37 from ARD 3.10 (44 columns × 16 machine rows), captured verbatim in `docs/evidence/04-ard-system-overview-2026-09-13.txt` under the ticket-01 evidence precedent with its provenance header.
  - `export_date` is read **from that header's own record of the export** (`2026-09-13 18:37`), not from the newest `Date Collected` — that column says when each machine was last contacted, and the two can be months apart. Each row keeps its own collection date.
  - **The export carries neither a hardware UUID nor an architecture column.** That is the ticket's central gap, resolved in *The three gaps* below.
- [x] The 16 role-matrix machines are present with their expected Munki short hostname and assigned role; the Mac Mini admin workstation and Cyril's Mac mini are present as fleet members in their own right.
  - **The role matrix is not recorded anywhere to cross-check against** — see *Finding: there is no recorded role matrix* below. What can be checked is the manifest tree, and that is what this does: each machine's role is the role group its own manifest names.
  - Sixteen machine manifests, sixteen inventoried machines. Read as **manifests**: `client-facing` 4, `online` 3, `toc` 2, `dit` 2, `warroom` 2 (`202A-Mac-Mini-M4`, `202B-Mac-Studio`), `sound` 1, `interns-temporary` 1, `coordination-admin` 1 (`Angels-iMac`), and **`production` has no machines at all**. Read as **inventory rows**, which is what the artifact carries: `client-facing` 4, `online` 3, `toc` 2, `dit` 2, `warroom` 1, `sound` 1, `interns-temporary` 1 — because `202B-Mac-Studio` and `Angels-iMac` are manifests no machine answers to, so their roles attach to nothing yet. Both numbers are in `data/machines.json`; the roles a *machine* has are the row's `role`.
  - The **admin workstation is present as a fleet member**: ARD's `Sixto (3)` at 192.168.88.151, UNIX hostname `Sixto-5`, serial `C07D317NPJJ7`. It has **no machine manifest**, so it resolves `site_default` — which is what ADR 0004 records independently, and its probe confirms `Macmini8,1`, an Intel mini (`x86_64`), hardware UUID `CB3D4672-22E7-573F-9CD2-5F1D2A6BEC0F`.
  - **Cyril's Mac mini is not in the export.** It is a fleet member by ADR 0004's own account and it is reported as *needing a record*, with its probed facts as a structured entry (`known_absent[0]`: serial, UUID, architecture, model, OS) rather than a sentence.
- [x] Every manifest filename in the repository is matched to an inventoried machine, and every inventoried machine to a manifest — both directions reported.
  - 16 machine manifests against 16 inventoried machines; **10 match exactly**, 4 match after folding (below), and both directions have real gaps:
    - **orphan manifests** (a machine manifest no machine answers to): `202B-Mac-Studio`, `Angels-iMac`;
    - **unmanaged machines** (no manifest, so they resolve `site_default`): `303A-Mac-Mini-M4-Pro`, `Sixto-5`.
  - Matching folds case, spaces and ARD's numeric suffix **for comparison only**; the reported value is always the source's own spelling. Manifests and the projection are matched by the **same** rule — exact first, then folded — so neither source can quietly become more permissive than the other.
- [x] Mismatches are listed as findings with a proposed correction: hostname differences (including names containing spaces), machines with a manifest but no inventory record, inventory records with no manifest, and role-matrix machines that are unassigned.
  - 36 findings in 8 kinds, each with a `proposed` correction. The four `name-difference` findings: `201-Bay-01-Mac-Pro-111` → `201-Bay-01-Mac-Pro`, `201-Bay-03-M1-Ultra-2805` → `201-Bay-03-M1-Ultra`, `201-Viewing-Room-1309` → `201-Viewing-Room`, `303B-iMac` → `303B iMac` (the manifest with the space).
  - No machine-level `role-unassigned` finding exists in the real tree: every machine manifest names exactly one role group. The code path is exercised by a test, because a machine with *no* manifest must not be reported twice.
  - Staleness is **not** judged here — see the review disposition.
- [x] Machines known to exist but absent from the engineering export are reported as needing a record, never guessed.
  - `Cyrils-Mac-mini` — a structured entry, not prose: serial `RWJ57V9PW4`, hardware UUID `B30D55C8-679C-56E2-9654-16CBFD4A905D`, `Mac16,10` (arm64), macOS 26.6.2 (25G83), LAN 192.168.88.202, LocalHostName `Cyrils-Mac-mini`, `HostName` unset. The operational database also knows this machine (a `bays` row named "Cyril Machine" at 192.168.88.202) — noted as corroboration, not as a source.
  - The rule is general: **any probe whose serial has no export row is reported** as needing a record, so a machine that answers a probe but is missing from the export cannot hide.
  - **Reported as leads, then closed by a human.** ARD's screen-sharing alias list holds 35 names, five of which appear in no export row: `202B iMac`, `303B Chad M1 Ultra`, `MacBook Air`, `Wesley's Mac mini`, `t6's iMac`. Most of the 26 non-matching names are duplicate aliases of machines that *are* in the export ("Sixto (2)" beside "Sixto (3)", "201 Bay 01 Mac Pro (9)" beside "(63)"). **Cyril, 2026-09-13: those five machines no longer exist.** They are not inventory records, and the alias list in ARD is stale. The one open question this raised — whether `202B-Mac-Studio` is real or the "202B iMac" alias is — was settled the other way: the Mac Studio exists, in `warroom`.
- [x] The inventory is stored in a form the observer (ticket 05) reads as its identity input, and the T6 operational Bays records are reconciled against it as a projection whose differences are reported, not silently applied.
  - `data/machines.json` — one row per machine, keyed on **serial**; `munki_name` is the **manifest** name or null; `unix_hostname` is the ARD spelling; `architecture` + `architecture_source`; `hardware_uuid` + `hardware_uuid_source`; `hardware_uuid_candidate` + `hardware_uuid_candidate_source`; addresses; OS; the row's own collection date. Ticket 05 targets machines by serial, and the known-absent machine carries its serial too.
  - The projection is read as an input file (`--bays`), never written to: **7 `bays-difference`** findings (address or name disagreements, each citing the Notion record URL where the projection has one) and **5 `bays-missing`**.
  - **A projection UUID never occupies the authoritative field.** `hardware_uuid` is filled by a probe only; a projection value travels in `hardware_uuid_candidate`, labelled with the column it came from, so a consumer that reads `hardware_uuid` alone cannot pick up the source ADR 0004 forbids.

## The three gaps — and what was tried first

Cyril's instruction: record a gap as a finding only after failing to find it by other means. Each was hunted before it was recorded.

**1. Hardware UUID — no authoritative value for 15 machines; 10 carried as unverified candidates.**
- *ARD report*: no such column (44 columns checked).
- *ARD's own records*: the export task keeps a per-computer record with a UUID, MAC and address for all 16 machines — **but that UUID is ARD's identifier, not the machine's.** Checked on 2026-09-13, commands and outputs in `docs/evidence/04-uuid-source-check-2026-09-13.txt`: ARD's record for the admin workstation is `0B1919E6-1503-49DC-A573-DA2DA06A78AE`; the machine's own `system_profiler` answer is `CB3D4672-22E7-573F-9CD2-5F1D2A6BEC0F`. Using ARD's value would have put sixteen wrong UUIDs in the inventory. (The same file shows ARD's cache also disagrees with the report on MAC and address for several machines, so it is not an identity source in any field.)
- *The operational projection*: 10 of the 16 machines have a `hardware_uuid` or `device_uuid` in the projection. Carried, **labelled** `bays-projection-unverified:hardware_uuid` (or `:device_uuid`), in the candidate field only, because ADR 0004 says Bays is a projection and never the source. The column is named because on some Macs those two agree and on others they do not, so a future probe mismatch has to say what it disagreed with.
- *Direct probe*: obtained for the two machines reachable from here — the admin workstation (probed over SSH) and this workstation (probed locally). Both carry `hardware_uuid_source: probe`.
- **Consequence:** 1 probe, 10 candidates, 5 with nothing at all; ticket 05's probe closes all of it, and the inventory keys identity on the **serial**, present for all 16, so nothing is blocked.

**2. Architecture — inferred for 15, probed for 1.**
The export has no architecture column, but it discriminates: every Intel row reports a CPU speed in GHz while every Apple Silicon row leaves it empty and model identifies the rest. `infer_architecture` uses that, labels every row `inferred-from-report`, and returns `unknown` rather than guessing for a model it cannot place (a Mac mini is the case that matters — an Intel 2018 and an M4 both live in this fleet). Ticket 05's probe moves rows to `probe`.

**3. Munki HostName — the export gives the UNIX hostname instead.**
Munki resolves a machine's manifest from `HostName`/`LocalHostName`, while the ARD column is `hostname`. On this workstation `HostName` is unset and `LocalHostName` is `Cyrils-Mac-mini`. So the four `name-difference` findings are **candidates for resolution failures, not proof of them** — ticket 06's subject, needing the probed `HostName`. Because of this, `munki_name` is never set from the ARD hostname: a machine with no manifest gets `null` and a finding, rather than an assertion nobody checked. The one machine that could be checked is consistent with ADR 0004's account of it: the admin workstation has `HostName` unset, `LocalHostName` `Sixto-5`, and no machine manifest, so it resolves `site_default`.

## Finding: there is no recorded role matrix

**Resolved 2026-09-13 — the matrix is now recorded and the check is real (see below). This is how it stood when the ticket was written.** The criterion says the inventory is "cross-checked against the role matrix", and `CONTEXT.md` defines the role matrix as "the assignment of each Mac to one role group, **recorded in the specification**". The specification records no per-machine assignment. So the only checkable source is the manifests themselves, and this ticket derives each machine's role from its own manifest — which means **a manifest that names the wrong role group cannot be detected here**. What detects it is the probe (ticket 05) and a resolution check (ticket 06), both of which ask the machine what it actually resolved. Recorded as a finding about the ticket's own premise rather than papered over.

Related, and for a human to settle: `CONTEXT.md` enumerates **eight** role groups; the spec and the manifest tree have **nine** (`production` is the extra). The code follows the spec, and `production` is used by no machine — **Cyril's decision, 2026-09-13: it exists and is intentionally unassigned for now.**

### Resolved: the matrix is now recorded, and it is a real check

`docs/role-matrix.csv` was generated from this ticket's artifact (19 rows: the 16 inventoried machines, the two manifests no machine answers to, and Cyril's Mac mini), **filled in by Cyril on 2026-09-13** with `confirmed_by` / `confirmed_on`, and is now a tool input (`--role-matrix`). What it changed:

- **`role-mismatch` found nothing — the manifest tree agrees with the recorded matrix for all 14 machines that have a manifest.** That is the point: the agreement is now *checked* rather than assumed, because the matrix is the first source of a machine's role that does not come from the manifest tree itself.
- **Two manifests no machine answers to are confirmed real.** `202B-Mac-Studio` (warroom) and `Angels-iMac` (coordination-admin): Cyril confirmed both Macs exist, so their finding now says they need an inventory record — the serial is not in the export — rather than asking whether to retire them.
- **Two machines with no manifest now have an instruction rather than a complaint**: the matrix places `303A-Mac-Mini-M4-Pro` in `client-facing` and `Sixto-5` (the admin workstation) in `coordination-admin`, so each needs a machine manifest named for its Munki HostName including that group.
- **Cyril's Mac mini is recorded as `production`**, and that role travels with its `needs-record` entry.
- New kinds and their counts today: `role-mismatch` 0, `role-matrix-unknown-machine` 0 (a matrix row that matches no manifest, no machine and no known-absent entry would be reported; nothing does).
- The matrix is validated rather than trusted: a role group that is not one of the nine is refused, a role with no machine name is refused, and a row left unanswered makes no claim.

## Finding: ADR 0004 states the export carries a hardware UUID, and it does not

ADR 0004 says identity comes from the ARD export "(machine name, serial number, **hardware UUID**, MAC address, OS version, known network addresses)". Verified against the artifact: the export has no UUID column, and the UUID ARD does keep is its own identifier. The ADR is therefore factually wrong about the source it pins identity to, and the deliverable's gap section is the evidence for that. **Proposed amendment** (for Cyril, not applied here — a design record is not silently rewritten):
> Identity comes from the Apple Remote Desktop machine export (machine name, serial number, MAC address, OS version, known network addresses). The export carries **no hardware UUID and no architecture**; those arrive from a probe of the machine itself, and the operational `bays` records hold a projection of them that is never the source.

## Findings by kind (36)

| kind | n | what it means |
|---|---|---|
| `uuid-unverified` | 10 | the projection has a UUID; unconfirmed, and not in the authoritative field |
| `bays-difference` | 7 | the projection's name or address disagrees with the machine |
| `uuid-unavailable` | 5 | no UUID from any source; needs the probe |
| `bays-missing` | 5 | no projection row matches this machine |
| `name-difference` | 4 | inventory hostname differs from the manifest name (folding matched them) |
| `machine-without-manifest` | 2 | resolves `site_default` instead of its own configuration |
| `manifest-without-machine` | 2 | a manifest nothing answers to |
| `needs-record` | 1 | exists, absent from the export (Cyril's Mac mini) — now carrying its recorded role |

Two further kinds exist to check the recorded role matrix and report **0** today, which is the result
rather than the absence of a check: `role-mismatch` (a manifest whose role group disagrees with the
matrix — none do; the tree agrees with Cyril's answers for all 14 machines that have a manifest) and
`role-matrix-unknown-machine` (a matrix row that matches no manifest, machine or known-absent entry).

## Deliberately not done

- **Nothing was changed**: no manifest, no `bays` record, no machine, no NAS. This ticket reports; a correction is a decision in Notion or the repository, and the projection is never written back to.
- The four name differences are **not** resolved — that needs the probed `HostName` and belongs to ticket 06.
- The observation store, the probe itself, and staleness *exposure* are ticket 05's. This ticket carries each row's collection date as provenance and records no staleness verdict.
- The screen-sharing leads (`202B iMac`, `MacBook Air`, …) are not rows, for the reason given above.

## Review disposition (two axes, 2026-09-13)

Findings are recorded with what happened to each. The review ran against the state at `c81bf48`; every fix below is in the follow-up commit.

**Spec axis**

| finding | disposition |
|---|---|
| "cross-checked against the role matrix" is not checkable — no recorded matrix; roles read from the manifests they are checked against | **accepted, and recorded as a premise finding above.** It is not fixable by this ticket: nothing records the matrix. The criterion's wording is left intact and the limitation is stated where a reader will hit it. |
| ADR 0004 is left factually wrong and unamended | **accepted; an amendment is proposed above and not applied**, because rewriting a design record is Cyril's call. The verified fact is in the gap section and in the module docstring. |
| 10 rows carried the projection's UUID in the authoritative field, so a consumer reading `hardware_uuid` alone got the forbidden source | **fixed.** `hardware_uuid` is probe-only; the projection value moved to `hardware_uuid_candidate` with the column named. Test: `test_the_operational_projection_is_carried_but_called_unverified` asserts the authoritative field is empty. |
| `munki_name` was the ARD hostname for the two manifest-less rows, with no provenance label, asserting an equivalence gap 3 calls unverified | **fixed.** `munki_name` is the manifest name or `null`; the ARD spelling stays in `unix_hostname`. Tests assert `is None`. |
| criterion 6 ticked on a technicality: ticket 05 could not build a serial-keyed target from prose | **fixed.** `known_absent` is a structured entry carrying serial, UUID, architecture, model and OS from the probe, and any probe with no export row is reported the same way. Two tests. |
| `stale-collection` is scope creep (staleness exposure is ticket 05's) | **removed**, with `STALE_COLLECTION_DAYS` and `_is_stale`. The row keeps its own collection date as provenance, and a test asserts no staleness verdict is recorded. |
| dead parsing in `ProbeRecord`, `ArdRecord`, `BaysRecord` | **fixed.** Unused fields removed; `notion_url` is now used in the projection findings so whoever corrects a record has the link; probe `model_identifier`/`os_version` now populate the known-absent entry. |
| `export_date` was the newest row's collection, not the export date | **fixed.** It is read from the artifact header's own record (`2026-09-13 18:37`), with the fallback documented. Test. |
| the recorded run did not reproduce the artifact (`--known-absent` elided with "…") | **fixed.** The command above is verbatim, and the only inputs are files in the repository. The reviewer confirmed everything else reproduced byte-for-byte. |

**Standards axis**

| finding | disposition |
|---|---|
| ticket cited role counts and named machines that have no row | **fixed.** The role paragraph now separates manifest roles from row roles and names the two manifests that attach to nothing. |
| the ARD-UUID check and the screen-sharing list were live-system claims with no artifact | **fixed.** `docs/evidence/04-uuid-source-check-2026-09-13.txt` carries the commands, the file path and the outputs, including ARD's cached values that disagree with the report. |
| the first four files sit in `a630d3b`, a GoogleChrome commit, and the suite was red there | **recorded, not rewritten.** The add was another session's; it annotated `a630d3b` with a git note taking responsibility, and its next commit turned the lesson into recorded convention (`docs/agents/issue-tracker.md`). `c81bf48` carries the correction and the measured test count. |
| Speculative Generality: `probe`/`bays` on `MachineRow` were populated and never serialised | **fixed.** Both fields removed. |
| Duplicated Code: `Finding` and a manifest loader exist in both `identity.py` and `drift.py` | **deferred, deliberately.** `drift.py` belongs to another session working this tree right now; consolidating across an active writer's file is how work gets lost. Recorded here so it is a decision, not an oversight. |
| Primitive Obsession: provenance as a formatted string, re-parsed | **half fixed.** The column is now a field (`candidate_uuid()`), so nothing re-parses. The human-readable label string stays: it is what a reader of the JSON sees. |
| Data Clumps: value+source pairs | **accepted as-is.** A provenance-carrying type would change the artifact's shape for tidiness at the cost of readability, and ticket 05 is the first consumer. Revisit if a second consumer appears. |
| Mysterious Name: `manifests_without_machine` beside `machines_without_manifest` | **fixed.** Renamed `orphan_manifests` and `unmanaged_machines`. |
| the machine-manifest classifier uses a hardcoded name list | **improved.** `--site-manifest NAME` (repeatable) names a non-machine manifest from outside the module, so a manifest added for another purpose does not become a phantom machine. Test. |
| matching asymmetry: manifests exact-then-folded, projection folded-only | **fixed.** One rule, `_first_match`, used by both. |
| `CONTEXT.md` enumerates eight role groups, the spec nine | **recorded above** as a glossary conflict for a human; the code follows the spec. |

## Held open for the reviewer

- ~~Whether `production` having no machines is intended.~~ **Decided 2026-09-13: `production`
  exists and is intentionally unassigned for now.** A role group with no machines is a deliberate
  state, not a missing assignment; recorded in `CONTEXT.md` so the next reader does not re-open it.
- Whether `201 Bay 03` (primary address on `192.168.254.0/24` over Wi-Fi) belongs on the wired
  network — a decision in the 12/13 approval packet, not a defect here.
- ~~The ADR 0004 amendment above, which only Cyril can accept.~~ **Accepted and applied
  2026-09-13.** ADR 0004's identity bullet now names what the export actually carries, with the
  superseded wording quoted in an amendment section and the verification cited. The decision
  itself is unchanged; only its description of the source was wrong.
- **The role matrix is still not recorded**, which is the one premise this ticket could not fix.
  Until a per-machine list exists, nothing can be checked against it. Cyril has not decided it.
