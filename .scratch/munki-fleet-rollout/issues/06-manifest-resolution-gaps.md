# 06: Close the manifest resolution gaps the inventory exposes

**What to build:** Every inventoried Mac resolving the manifest it is supposed to resolve — including the admin workstation that currently falls back to `site_default`, the orphaned group manifests nobody inherits, and the production machine enrolled under a test identifier.

**Blocked by:** 05

**Approval gate:** Cyril approves the manifest assignment for the admin workstation and Cyril's Mac mini, because both changes alter what those machines receive. **Half discharged 2026-09-14:** the admin workstation's assignment (`Sixto-5` → `coordination-admin`) is approved and published; Cyril's Mac mini's is untouched — it has no manifest and still carries the test ClientIdentifier.

**Status:** ready-for-human — the admin workstation's manifest is **live** as of 2026-09-14 (published, served, read back over HTTP). What remains is not an approval: it is an observation of the machines themselves, which needs fleet SSH (ticket 05's open item), plus the change on Cyril's Mac mini. Criteria 1, 2, 4, 5 and 6 stay unticked for those reasons.

## What the 2026-09-14 publish changed (this ticket's half)

Cyril approved one publish carrying this ticket's two manifests and ticket 08's forced-core suspension (they cannot be separated — see ticket 08's ordering note). Full capture, including the gate's refusal in refusing mode and the read-back: `docs/evidence/06-08-publish-2026-09-14.txt`.

- `manifests/303A-Mac-Mini-M4-Pro` and `manifests/Sixto-5` are **added** to the target. Both are now served over HTTP with their role groups: `client-facing` and `coordination-admin` respectively. The gate classified both as declared added files and the publish reported `written 3, unchanged 93, backed up 1`; the HTTP verify came back `96/96 match`.
- The admin workstation therefore stops resolving `site_default` **as a matter of configuration**. That is not the claim criterion 1 below makes, which is about the machine's own behaviour — no Mac has reported since the publish.
- The role matrix's `notes` cell for `303A Mac Mini M4 Pro` ("no machine manifest — the matrix says client-facing, so it needs a manifest named for its Munki HostName including that group") is now **stale**: that manifest exists and is served. The matrix is Cyril's confirmed artifact (`confirmed_by: cyril`), so it was left unedited; correcting it is his call.
- `manifests/Cyrils-Mac-mini` still does not exist — this publish does not touch ticket 07's blocker 1.

## Acceptance criteria

- [ ] The Mac Mini admin workstation no longer falls back to `site_default`: it has a machine manifest, and the change to what it receives is approved before it is applied.
  - **Half — and the observable half is not met.** The manifest exists, is approved and is published (`Sixto-5` → `coordination-admin`, HTTP 200). "No longer falls back" is a statement about the machine, and no Mac has reported since the publish: that half is criterion 4's observation, which needs fleet SSH.
- [ ] Cyril's Mac mini is no longer identified by a test ClientIdentifier; it resolves its own machine manifest.
  - **NOT MET.** Untouched by this publish: the machine still carries `ClientIdentifier = t6-test-client` (read on the machine 2026-09-13), and `manifests/Cyrils-Mac-mini` does not exist. Both changes are outstanding — one in the tree, one on the machine.
- [x] The orphaned group manifests (the `production` group and the test-client group) are either placed in service with a documented purpose or retired — with the decision recorded.
  - **Met, both halves, verified 2026-09-14.** *Retired:* the test-client group is gone from the checkout (`manifests/t6-test-client` absent) and `GET manifests/t6-test-client` returns **HTTP 404** on the target. *In service with a documented purpose:* `manifests/production` (display_name `T6 production`, includes `all`) is served (**HTTP 200**), and its purpose is the role it names — `docs/role-matrix.csv` records `Cyril's Mac mini → role_group production`, `confirmed_by: cyril`, `confirmed_on: 2026-09-13`. Nothing inherits it yet because that machine has no manifest: that is criterion 2's gap, not an orphan.
- [ ] Resolution is verified per machine from observed data: every inventoried Mac reports a resolved manifest name that is its own machine manifest, not `site_default` and not a group.
  - **NOT MET.** No observation run since the publish: the store holds 2 readings for 17 expected machines (`fleet: 17 expected, 2 reading(s) held, 2 stale`, section 7 of the evidence file). Blocked on fleet SSH — ticket 05's open item.
- [ ] Any machine whose hostname does not match its manifest filename is corrected or the manifest renamed, whichever the inventory evidence supports, and the correction is recorded.
  - **NOT MET.** The open case is `201-Bay-01-Mac-Pro-111` (inventory) against `manifests/201-Bay-01-Mac-Pro` (tree), recorded as a `name-difference` finding in `data/machines.json`. Deciding it needs that machine's own `HostName`, which is an observation; renaming a manifest on a guess would be the defect, not the fix.
- [ ] Before/after evidence is recorded per machine affected.
  - **NOT MET per machine.** What is recorded is the repository's before/after, not any machine's: `manifests/all` moving from 26 forced to 0 forced / 26 optional, and the two manifests going from absent to served (sections 2 and 6 of the evidence file). Per-machine evidence needs the same observation run as criterion 4.
