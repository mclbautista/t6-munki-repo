# 04: One authoritative inventory of which Mac is which

**What to build:** A reconciled inventory of the fleet: every Mac's name, Munki short hostname, serial number, hardware UUID, architecture, and assigned role — cross-checked against the role matrix and the set of machine manifests, with every mismatch reported.

**Blocked by:** None (can start immediately)

**Status:** done (2026-09-13)

**Notes:** The live repository's manifest set is evidence of intent, not evidence of reality: a manifest existing for a hostname does not prove a machine with that hostname exists. Both directions must be checked.

## What was built

- `munki_fleet/identity.py` — stdlib only, and **no live machine and no NAS is touched**: the ARD export, the manifest tree, probe results and the operational projection are all *file* inputs. A machine that has not been probed is a finding, never a guess.
- `tests/test_identity.py` — 31 tests against a trimmed ARD export fixture and a manifest tree generated per test.
- `tests/fixtures/ard/ard_system_overview_sample.txt` — the fixture, in the report's own format including its `Date Collected` comma quirk.
- `data/machines.json` — the inventory ticket 05 reads: 16 rows, 38 findings, `schema_version: 1`, and a provenance label on every field that could come from more than one source.
- Entry point: `python3 -m munki_fleet.identity --ard-export FILE --metadata-root . [--probes P] [--bays B] [--known-absent NAME:DETAIL] [--out data/machines.json] [--summary]`.
- The two input files the real run used, so the artifact is reproducible from the repository: `docs/evidence/04-probes-2026-09-13.json` (the two machines that could be probed directly) and `docs/evidence/04-bays-projection-2026-09-13.json` (the operational `bays` projection as read, read-only; identity columns only — no emails or licence fields). The run:

  ```
  python3 -m munki_fleet.identity \
    --ard-export docs/evidence/04-ard-system-overview-2026-09-13.txt \
    --metadata-root . \
    --probes docs/evidence/04-probes-2026-09-13.json \
    --bays docs/evidence/04-bays-projection-2026-09-13.json \
    --known-absent "Cyrils-Mac-mini:…" --out data/machines.json --summary
  → machines=16 manifests=16 export_date=9/13/26 12:00 AM
  ```

## Acceptance criteria

- [x] Identity is sourced from the Apple Remote Desktop machine export (name, serial, UUID, MAC, OS version, known addresses); the source file used and its export date are recorded.
  - Source: `docs/evidence/04-ard-system-overview-2026-09-13.txt` — the ARD *System Overview Report* Cyril exported on 2026-09-13 18:37 from ARD 3.10 (44 columns × 16 machine rows), captured verbatim under the ticket-01 evidence precedent with its provenance header.
  - Recorded in the artifact: `identity_source` and `export_date` (`9/13/26 12:00 AM`) in `data/machines.json`, and per row the report's own `collected_at`.
  - **The report carries no hardware UUID and no architecture column** — see *The three gaps*, which is where that is resolved and how.
- [x] The 16 role-matrix machines are present with their expected Munki short hostname and assigned role; the Mac Mini admin workstation and Cyril's Mac mini are present as fleet members in their own right.
  - Roles come from the repository, not from a document outside it: each machine manifest names exactly one role group. Sixteen machine manifests, sixteen inventoried machines, and the mapping is in `data/machines.json` per row: `client-facing` 4 (201 Bay 02, 201 Bay 03, Viewing Room, 303D), `online` 3 (Jason, Tim, 202C), `toc` 2 (202 Mac Pro, 202 TOC), `dit` 2 (both MacBooks), `warroom` 2 (202A, 202B), `sound` 1 (201 Bay 01), `interns-temporary` 1 (303B iMac), `coordination-admin` 1 (Angels-iMac).
  - **`production` has no machines at all** — nine role groups exist and one of them is used by nothing. Recorded rather than silently carried: either a machine is missing from it or the group is aspirational.
  - The **admin workstation is present as a fleet member**: ARD's `Sixto (3)` at 192.168.88.151, UNIX hostname `Sixto-5`, serial `C07D317NPJJ7`. It has **no machine manifest**, so it resolves `site_default` — which is what ADR 0004 records independently, and the first probe in this ticket confirms its hardware UUID and `Macmini8,1` (Intel x86_64).
  - **Cyril's Mac mini is not in the export.** It is a fleet member by ADR 0004's own account and it is reported as *needing a record* (criterion 5), not invented.
- [x] Every manifest filename in the repository is matched to an inventoried machine, and every inventoried machine to a manifest — both directions reported.
  - 16 machine manifests against 16 inventoried machines; **10 match exactly**, 4 match after folding (below), and both directions have real gaps:
    - manifests with **no machine in the export**: `202B-Mac-Studio`, `Angels-iMac`;
    - inventoried machines with **no machine manifest**: `303A-Mac-Mini-M4-Pro`, `Sixto-5` (both therefore resolve `site_default`).
  - Matching folds case, spaces and ARD's numeric suffix **for comparison only**; the reported value is always the source's own spelling.
- [x] Mismatches are listed as findings with a proposed correction: hostname differences (including names containing spaces), machines with a manifest but no inventory record, inventory records with no manifest, and role-matrix machines that are unassigned.
  - 38 findings in 9 kinds, each with a `proposed` correction; `data/machines.json` carries them all, and `--summary` prints the counts. The four `name-difference` findings are `201-Bay-01-Mac-Pro-111` → `201-Bay-01-Mac-Pro`, `201-Bay-03-M1-Ultra-2805` → `201-Bay-03-M1-Ultra`, `201-Viewing-Room-1309` → `201-Viewing-Room`, `303B-iMac` → `303B iMac` (the manifest with the space).
  - Two `stale-collection` findings: `201 Viewing Room` collected 12/3/25 and `303D Mac Studio M2` 6/29/26, against a 9/13/26 export. Identity survives age; state does not, and the finding says so.
  - No machine-level `role-unassigned` finding exists in the real tree: every machine manifest names exactly one role group. The code path is exercised by a test, because a machine with *no* manifest must not be reported twice.
- [x] Machines known to exist but absent from the engineering export are reported as needing a record, never guessed.
  - `Cyrils-Mac-mini` — reported with the evidence rather than a row: serial `RWJ57V9PW4`, hardware UUID `B30D55C8-679C-56E2-9654-16CBFD4A905D`, `Mac16,10` (arm64), macOS 26.6.2 (25G83), LAN 192.168.88.202, LocalHostName `Cyrils-Mac-mini`, `HostName` unset. The operational database does know this machine (a `bays` row named "Cyril Machine" at 192.168.88.202), which is noted as corroboration, not as a source.
  - **Reported as leads, not as rows** (weak evidence, for a human to confirm): ARD's own screen-sharing alias list holds 35 names, and five distinct machines appear there that are not in the export — `202B iMac`, `303B Chad M1 Ultra`, `MacBook Air`, `Wesley's Mac mini`, `t6's iMac`. Most of the 26 non-matching names are duplicate aliases of machines that *are* in the export ("Sixto (2)" beside "Sixto (3)", "201 Bay 01 Mac Pro (9)" beside "(63)"). A stale alias is not proof a machine exists, so none of them became a row. `202B iMac` is worth a second look because the repository has a `202B-Mac-Studio` manifest with **no machine at all** — one of the two is wrong, and a probe settles which.
- [x] The inventory is stored in a form the observer (ticket 05) reads as its identity input, and the T6 operational Bays records are reconciled against it as a projection whose differences are reported, not silently applied.
  - `data/machines.json` — one row per machine keyed by serial, with `munki_name`, `role`, `architecture` + `architecture_source`, `hardware_uuid` + `hardware_uuid_source`, addresses, OS, and the collection date. Ticket 05 targets machines **by serial** and includes the known-absent machine in its target list.
  - The projection is read as an input file (`--bays`), never written to: **7 `bays-difference`** findings (address or name disagreements, e.g. the projection calls 201 Bay 03 `Bay 03 Mac Studio Ultra` at 192.168.88.173 while the machine reports 192.168.254.106; 303B iMac at .177 vs .191; T6 MacBook M3 Pro at .118 vs .80; T6 MacBook M4 Max at .17 vs .100) and **5 `bays-missing`** (202 Mac Pro, 202 Tim, 202A, 303A, Sixto-5 — no projection row matches them at all, though "202A iMac" and "Bay 02 Mac Studio" rows exist under names that fold to *different* machines).

## The three gaps — and what was tried first

Cyril's instruction: record a gap as a finding only after failing to find it by other means. Each was hunted before it was recorded.

**1. Hardware UUID — not available for 5 machines; 10 carried as unverified candidates.**
- *ARD report*: no such column (44 columns checked).
- *ARD's own records*: the export task keeps a per-computer record (`~/Library/Containers/com.apple.RemoteDesktop/…/Task History/2026-09-13.plist`) with a UUID, MAC and address for all 16 machines — **but that UUID is ARD's identifier, not the machine's.** Verified: ARD's record for the Mac Mini is `0B1919E6-1503-49DC-A573-DA2DA06A78AE`; the machine's real hardware UUID is `CB3D4672-22E7-573F-9CD2-5F1D2A6BEC0F`. Using it would have put 16 wrong UUIDs in the inventory. The trap is documented in the module docstring so the next person does not fall into it.
- *The operational projection*: 14 `bays` rows carry `hardware_uuid` or `device_uuid`, and 10 fold onto inventoried machines. Carried, **labelled** `bays-projection-unverified:hardware_uuid` (or `:device_uuid`), because ADR 0004 says Bays is a projection and never the source. The column is named in the label because on some Macs those two columns agree and on others they do not, so a future probe mismatch has to say what it disagreed with.
- *Direct probe*: obtained for the two machines reachable from here — the admin workstation (probed over SSH) and this workstation (probed locally). Both are in `data/machines.json` with `hardware_uuid_source: probe`.
- **Consequence:** 5 machines have no UUID at all and 10 have an unverified candidate; ticket 05's probe closes both, and the inventory keys identity on the **serial**, which the report carries for all 16 — so nothing is blocked.

**2. Architecture — inferred for 15, probed for 1.**
The report has no architecture column, but it does discriminate: every Intel row reports a CPU speed in GHz while every Apple Silicon row leaves it empty and the Mac Studio / M-series models identify themselves. `infer_architecture` uses that, labels every row `inferred-from-report`, and returns `unknown` rather than guessing for a model it cannot place (a Mac mini is the case that matters — an Intel 2018 and an M4 both live in this fleet). Ticket 05's probe moves rows to `probe`.

**3. Munki HostName — the report gives the UNIX hostname instead.**
Munki resolves a machine's manifest from `HostName`/`LocalHostName`, while the ARD column is `hostname`. On this workstation `HostName` is unset and `LocalHostName` is `Cyrils-Mac-mini`. So the four `name-difference` findings are **candidates for resolution failures, not proof of them** — that is ticket 06's subject and it needs a live probe. The one machine that could be checked is consistent with ADR 0004's account of it: the admin workstation has `HostName` unset, `LocalHostName` `Sixto-5`, and no machine manifest, so it resolves `site_default`.

## Findings by kind (38)

| kind | n | what it means |
|---|---|---|
| `uuid-unverified` | 10 | the UUID came from the projection, unconfirmed |
| `bays-difference` | 7 | the projection's name or address disagrees with the machine |
| `uuid-unavailable` | 5 | no UUID from any source; needs the probe |
| `bays-missing` | 5 | no projection row matches this machine |
| `name-difference` | 4 | inventory hostname differs from the manifest name (folding matched them) |
| `machine-without-manifest` | 2 | resolves `site_default` instead of its own configuration |
| `manifest-without-machine` | 2 | a manifest nothing answers to |
| `stale-collection` | 2 | collected more than 30 days before the export |
| `needs-record` | 1 | exists, absent from the export (Cyril's Mac mini) |

## Deliberately not done

- **Nothing was changed**: no manifest, no `bays` record, no machine, no NAS. This ticket reports; a correction is a decision in Notion or the repository, and the projection is never written back to.
- The four name differences are **not** resolved — that needs the probed `HostName` and belongs to ticket 06.
- The observation store, the probe itself, and staleness *exposure* are ticket 05's. This ticket supplies identity only.
- The screen-sharing leads (`202B iMac`, `MacBook Air`, …) are not rows for the reason given above.

## Held open for the reviewer

- Whether `production` having no machines is intended.
- Whether `201 Bay 03` (primary address on `192.168.254.0/24` over Wi-Fi) belongs on the wired network — recorded in the 12/13 approval packet as a decision, not a defect here.

## Review disposition

The two-axis review of this ticket's commit runs after it, and the findings are recorded here in a follow-up commit rather than being claimed in advance: ticket 11's review showed that asserting a review a reader cannot find is itself a defect. Nothing in the criteria above depends on that review — every one is backed by a test, a counted run, or a named artifact.
