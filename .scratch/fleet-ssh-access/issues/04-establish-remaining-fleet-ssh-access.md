# 04: Establish SSH access for the remaining fleet

**What to build:** The approved collector access method is extended to every remaining T6 Mac, and one fleet run reconciles all 17 expected observation targets into observed, partial, or unobserved outcomes with exact transport evidence. Authentication failures are findings, not a completed access rollout.

**Blocked by:** 03: Establish SSH access for rollout wave 1

**Status:** ready-for-human — **criteria 1 and 2 are met by measurement; 3-9 are open on the operator's half.** The remaining wave is enumerated and swept, every machine has one source-grounded disposition, and none of the fourteen has been touched: six need Remote Login enabled before a key can matter, six do not answer at all, one has no identity to key on, and the local machine needs no ssh at all. The runbook is `~/T6-Ops-Docs/runbooks/fleet-ssh-ticket04-remaining-fleet-2026-09-15.html`; the capture is `docs/evidence/04-remaining-fleet-enumeration-and-sweep-2026-09-15.txt`.

**Claimed by:** session 20260914_205203_8fee48, 2026-09-15T00:45+08:00.

**Approval gate:** Enabling Remote Login or authorizing a collector key fleet-wide changes authentication on facility Macs and requires Cyril's confirmation of the remaining wave before execution.

- [x] The remaining wave is enumerated from the current authoritative inventory and role matrix immediately before execution; additions, removals, stale addresses, unknown serials, and name disagreements are reported rather than silently normalized.
  - Enumerated 2026-09-15 00:30 from `docs/role-matrix.csv` (19 identities) and `data/machines.json` (16 rows, `export_date` 2026-09-13 18:37), giving **17 expected observation targets** — and the 17 is the loader's own composition, not arithmetic done here: `_inventory_targets` walks `machines` and then `known_absent`, adding the latter by `probe_hostname` (read from `munki_fleet/cli.py`).
  - **14 remaining**, five already approved. Reported rather than normalized: `202B-Mac-Studio` and `Angels-iMac` are orphan manifests; `303A-Mac-Mini-M4-Pro` and `Sixto-5` carry the inventory's `unmanaged` flag; `Cyrils-Mac-mini` is `known_absent`; **two inventory rows carry no `munki_name` at all** (the 303A row and the Sixto-5 row), which is exactly how a join silently drops machines from a "17 machines" count; `T6-MacBook-M4-Max` binds to **.82** while the inventory says .100; `201-Bay-01-Mac-Pro`'s UNIX hostname disagrees with its manifest (already an inventory finding); `201-Bay-03-M1-Ultra` sits on a different subnet; `Angels-iMac` has no serial and no address in any source.
  - The enumeration also settled **which machine the collector runs on**: `Cyrils-Mac-mini`, 192.168.88.202, serial `RWJ57V9PW4` — not the admin workstation (`Sixto-5`, .151), which is what ticket 05's cutover targets. Recorded because every stanza and `known_hosts` entry created here has to be recreated there.
- [x] Every expected machine has one explicit SSH access disposition: already authorized, approved change required, intentionally unavailable, off-site/unreachable, missing identity, or another source-grounded reason.
  - All 19 identities carry one, from the sweep's own measurements (ICMP, a TCP connect to 22 with **refused** and **timeout** kept apart, and each machine's mDNS name binding):
  - **already authorized (5)** `Sixto-5`, `202-TOC-M4-Max`, `202-Mac-Pro-3`, `202A-Mac-Mini-M4`, `202B-Mac-Studio`.
  - **reached locally, no ssh needed (1)** `Cyrils-Mac-mini` — the collector runs on it; `--local-host Cyrils-Mac-mini` is that transport's declaration (a locally reached target travels without ssh, so no ssh record applies to it).
  - **approved change required — two-part (6)** `201-Viewing-Room` .170, `202-Jason-M2-Max` .179, `202-Tim-M2-Max-9` .180, `202C-Studio-M1-Ultra` .181, `303D-Mac-Studio-M2` .193, `T6-MacBook-M4-Max` .82: ICMP answers and port 22 **refuses**, so sshd is off and a key would change nothing until Remote Login is on.
  - **not reachable (6)** `201-Bay-01-Mac-Pro` .171, `201-Bay-02-M1-Max` .172, `201-Bay-03-M1-Ultra` 192.168.254.106, `303A-Mac-Mini-M4-Pro` .190, `303B iMac` .191, `T6-MacBook-M3-Pro` .80 — no ICMP and port 22 times out; recorded as *not reachable at 00:40*, which is not the same claim as *absent*.
  - **missing identity (1)** `Angels-iMac`.
  - A finding of mine is **withdrawn** here: ticket 03 records `202C-Studio-M1-Ultra` answering at .99 against the inventory's .181 and calls one of them stale. Re-measured today it binds to **.181**, so the inventory was right; ticket 03 now carries a dated correction and the finding does not travel here as a defect.
- [ ] Cyril approves the exact remaining machine set and authentication changes before execution.
- [ ] The same least-privileged, no-root probe access proven on the pilot and wave 1 is used; no password, private key, or secret enters Git, the access inventory, logs, tickets, or the observation store.
- [ ] A single recorded fleet run targets all 17 expected machines and reconciles the run totals programmatically against the inventory and role matrix.
- [ ] Every reachable machine is observed with matching serial and records its Munki version, resolved manifest, pending state, last-check result, warnings, architecture rejections, source timestamps, and observation timestamp.
- [ ] Every partial or unobserved machine retains the exact reason and is named individually; authentication refusal is not accepted as finished SSH access unless Cyril explicitly chooses and records an exception.
- [ ] Manifest-name and identity disagreements discovered by the machines' own reports are recorded as findings for the existing manifest-resolution and inventory tickets, not corrected by guesswork in this ticket.
- [ ] Each changed machine has a recorded rollback path, and the final report distinguishes access established, machine observed, and unresolved exceptions.
