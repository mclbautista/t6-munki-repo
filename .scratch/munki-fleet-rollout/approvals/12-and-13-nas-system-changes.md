# Approval packet: tickets 12 and 13 (the two NAS system changes)

**For:** Cyril's decision, one pass. **Nothing in this packet has been executed.** Every fact below is a
read-only observation taken on 2026-09-13 between 18:35 and 18:45 PST, with the command or tool that
produced it, so each can be re-checked before you decide.

Tickets 12 and 13 are the only two in the set whose blocker graph is satisfied and whose work is a
**change to the NAS** rather than to this repository. Both therefore carry the same gate:

> **12:** "Configuring NAS snapshots and backup jobs is a system change on the NAS and requires Cyril's
> approval before execution."
> **13:** "Changing the NAS firewall is a system change and requires Cyril's approval before execution."

Everything else in the set is either in flight elsewhere or waiting on these two.

---

## Current state (verified today, read-only)

| fact | value | source |
|---|---|---|
| NAS | `192.168.88.188`, QuTS 6.0 | repo `CONTEXT.md`, `curl` below |
| Storage pool | one pool, **RAID 6** over 8 x 16 TB Seagate HDDs (14.55 TB usable each), `pool_capacity` 84.25 TB, **freesize 23.06 TB** | `list_storages` |
| Repository volume | the **`Web` share, volume 8** (thin), 13.0 GB used of 25.6 TB, 75 dirs / 193 files | `list_shared_folder`, `get_shared_folder` |
| Served path | `/Web/MunkiRepo` → `catalogs`, `pkgsinfo`, `icons`, `manifests`, **`pkgs`**; owner `t6-sixto`, group `everyone`, mode `770`, ACL enabled | `list_files` |
| Endpoint | **plain HTTP on port 80, no authentication**: `GET http://192.168.88.188/MunkiRepo/catalogs/all` → `200` (60,092 bytes); `manifests/all` → `200`; directory listings → `403` | `curl` |
| File-layer permission | `Web` share is `admin` RW + `administrators` RW — admin-only over SMB, **world-readable over HTTP** | `get_shared_folder` |
| Backup jobs | **0** — no HBS job exists for anything (`total: 0`) | `hbs_list_jobs` |
| Snapshot Manager | **installed** (2.0.0.0607) | `appcenter_list_apps` |
| HBS 3 | installed (26.4.4.788) | `appcenter_list_apps` |
| **QuFirewall** | **NOT installed** — no firewall app at all | `appcenter_list_apps` |
| myQNAPcloud | installed **and enabled** — a remote-access surface that bears on 13's "never internet-reachable" claim | `appcenter_list_apps` |
| Metadata checkout (Git) | 9.3 MB total: `.git` 4.5 MB, `icons` 3.6 MB, `pkgsinfo` 152 KB, `catalogs` 120 KB, `manifests` 112 KB; 38 pkginfo files, 28 manifest files | `du`, `find` |
| Payloads | **not in Git** — `pkgs/` exists only on the NAS | `ls` |

A second observation, relevant to both: `catalogs` and `pkgsinfo` on the NAS carry mtime **2026-09-13 18:32:09**, i.e. something wrote them minutes ago. That is ticket 02's publish path in flight from another session (that session's working tree holds `munki_fleet/` + tests). It means **the served tree changes under us** while these two tickets are decided; a restore drill or a firewall test must record the checksum it saw, not "the current tree".

---

## Ticket 12 — snapshots, an off-NAS copy, and a proven restore

### What would be configured

**12A. A snapshot schedule on the `Web` volume (volume 8).** QTS takes snapshots per volume; `Snapshot Manager` is installed and there is none today.
- Proposal to approve: **daily snapshot, retention bounded (e.g. 7 daily kept)**, with the *guaranteed snapshot space* set explicitly rather than left at whatever default. Ticket 12 requires the policy be recorded: frequency, retention, what is covered.
- Why bounded and small: the repository volume holds 13.0 GB today, so even a fortnight of daily snapshots is a few hundred GB against **23.06 TB free** in the pool. The failure mode to avoid is an unbounded schedule quietly consuming pool space that `1.Projects` / `02.Project` also depend on — those two shares are 56% and 67% full of 22 TB and 55 TB volumes.
- Blast radius: **pool space only.** Snapshots are invisible to clients; they do not change what Munki serves. Deleting one is irreversible, so the retention number is the real decision.

**12B. The off-NAS copy of the metadata — needs your choice of target, because "a second device" is ambiguous here.**

| option | what it means | cost / risk |
|---|---|---|
| **(i) HBS job: NAS → Mac Mini** (`t6-mac-mini`) | replicates `catalogs`, `manifests`, `pkgsinfo`, `icons` off the NAS entirely; the Mac Mini is already the admin/orchestration host | needs an HBS job + credentials; Mac Mini has ~295 GB free of 1 TB, and the metadata is **under 15 MB**, so size is a non-issue |
| **(ii) Git is already off-NAS** | the checkout on the admin workstation carries the whole metadata history — 9.3 MB, 4.5 MB of it `.git` | arguably already satisfies "not only on the NAS", but it is the *same workstation* that publishes; a workstation loss loses the working copy but not the history if it is also pushed |
| **(iii) both** | HBS job for the served tree **and** `git push` of the checkout | the honest belt-and-braces; more moving parts |

**Recommendation: (iii)**, because the two cover different failure modes — (i) restores what the NAS *served*, (ii) restores the *history of how it got there*, and neither is sufficient alone for a wrong-delete.

**12C. Payload classification and the restore drill.** Payloads (~13 GB, only on the NAS, not in Git) are the part whose acquisition may not be repeatable. Ticket 12 requires each classified **re-fetchable** or **non-reproducible**, and each non-reproducible one either copied off-NAS **or** given a recorded exclusion reason. The drill then has to be *performed*: restore metadata from the backup, verify payload checksums, rebuild catalogs and compare to what the NAS serves.
- Decision needed: **where the drill restores to** — a scratch path on the NAS (fast, exercises the same volume) or off-NAS (exercises the whole path). The ticket's point is that the procedure be followed under pressure, so the drill target should be the *second* device, not the volume being protected.

### Rollback
- 12A: delete the schedule (snapshots already taken remain until deleted individually); worst case a mistaken retention setting costs pool space, which is recoverable by deleting snapshots.
- 12B: stop/delete the HBS job; nothing on the source side is modified by a copy job **provided** it is configured one-way (NAS → Mac Mini) and not as a sync that can delete.
- 12C: a drill writes only to the chosen scratch/second device; no client is touched.

### Verification (what would be reported back)
Schedule and retention read back from Snapshot Manager; the HBS job's first run status; the drill's restore output with checksums and the catalog comparison against the live `all` catalog checksum recorded that day.

---

## Ticket 13 — restrict the endpoint to the fleet

### The finding that changes this ticket's shape

**There is no firewall on the NAS to configure.** No QuFirewall (or equivalent) is installed — the app list is 19 apps and none of them is a firewall. QTS's built-in Security Center is policy *levels*, not a port allowlist. So ticket 13 is not "add a rule"; it is **"install and enable a firewall on the NAS, then add a rule"**, and that first step has its own risk: QuFirewall's default posture can cut off access paths, and the NAS is currently reachable by everything on the LAN.

Second finding: **the repository's port is port 80, shared with everything else the NAS serves over HTTP.** The repo is an unauthenticated plain-HTTP path (`/MunkiRepo/...` → 200) whose file-layer ACL is admin-only — i.e. the HTTP path is the only access control on the metadata today. That is exactly the residual risk ADR 0007 records, and it also defines the blast radius: a rule for "the repository's port" is a rule for **the whole Web share and any other HTTP service on 80**. Admin UI on 8080 did not answer from the admin workstation during this check (`curl --max-time 5` → no response), so an accidental HTTP lockout would not necessarily leave that fallback.

### What would be configured, in order

1. **Install QuFirewall** (App Center) — a system change; the packet treats this as decision **13A**.
2. **Allowlist rule** permitting `TCP 80` only from the fleet's own addresses — decision **13B**, and the substantive one, because the inventory shows **three** address ranges in play, not one:

   | range | who is on it | evidence |
   |---|---|---|
   | `192.168.88.0/24` | the wired fleet — 15 of the 16 inventoried Macs, and the NAS itself | System Overview Report, primary addresses |
   | `192.168.254.0/24` | `201 Bay 03 M1 Ultra`, primary address `192.168.254.106` over **AirPort (Wi-Fi)** | same report, row "201 Bay 03 M1 Ultra (1620)" |
   | `192.168.0.0/24` | **Cyril's Mac mini** (this workstation): LAN `192.168.88.202`, **Wi-Fi `192.168.0.107`** | `ipconfig getifaddr en1` on the machine, 2026-09-13 |

   So the choice is not "one subnet or the other" but "which of the client paths must keep working":
   - allow `192.168.88.0/24` only → any Mac that is on Wi-Fi at the time of its Munki run **cannot fetch** (201 Bay 03 today, Cyril's Mac mini whenever its Wi-Fi is primary);
   - allow all three → keeps every client working, and admits whatever else shares those Wi-Fi ranges — the Wi-Fi subnets are not fleet-only, so this weakens the allowlist's meaning;
   - **recommended:** treat the two Wi-Fi ranges as a *network-path defect to fix*, not as allowlist entries — a studio Mac that must reach the repository belongs on the wired path, and the fix is where the Mac connects, not a firewall hole. Allowlist `192.168.88.0/24`, record the two machines as needing a wired path, and re-check after.

   A related fact for the same decision: **Cyril's Mac mini does not appear in the ARD export at all** (serial `RWJ57V9PW4`, `Mac16,10`, macOS 26.6.2 — `grep` finds it zero times in the captured artifact), even though ticket 04 requires it to be "present as a fleet member in its own right". Whoever runs 04 has to report that as a machine needing a record, not invent one, and 13's client list has to include it once it has one.
3. **Keep a second access path open before applying** (SSH to the NAS, or a console session), so a mis-scoped rule cannot lock administration out along with the clients.
4. **The negative case — decision 13C.** The ticket requires "a refused connection from an address outside the allowlist", with the source recorded, *or* an explicit statement that the negative case was not verified by us and exactly what remains unverified. Options: a phone on cellular (only proves anything if the NAS is otherwise routable from outside — if there is no inbound route, the traffic never reaches the firewall and the test proves nothing), a machine on a different VLAN, or the honest statement. This one cannot be faked in a report.
5. **The internet-reachability claim needs one more check: `myQNAPcloud` is installed and enabled.** Its status (registered/active, and whether it exposes anything) should be verified as part of 13's evidence, because the ticket's own words are "the evidence that this restriction is what stands between the repository and the wider network is stated explicitly, including that the repository must never be internet-reachable." A remote-access app left enabled weakens that sentence even if no firewall rule is missing.

### Rollback
Remove the allowlist rule (or disable QuFirewall) — the connection returns to today's state; the SSH/console path kept open in step 3 is what makes this survivable. Recommended: if QuFirewall supports a monitor/log-only mode, run the rule set in that mode first and read the log for a working day before enforcing it.

### Blast radius summary
Every Munki client's check-in (16 inventoried Macs plus any un-inventoried one, which is the ticket-04 gap), any other HTTP service on the NAS, and administration itself if step 3 is skipped. Nothing on the clients is modified — the failure mode is *denied fetches*, not damage.

---

## What I could not read (so the numbers above are proposals, not current config)

- **Snapshot schedule / retention / guaranteed snapshot space**: not exposed by the read-only storage tools available to me; ticket 12's own record says no snapshot existed as of 2026-09-13, which is consistent with what I can see (nothing in the volume listing). Read it in Snapshot Manager before approving the retention number.
- **Firewall state**: nothing to read — the app is absent, which is the finding.
- **QuFirewall's rule model on QuTS 6.0** (whether it supports log-only staging, and whether its rules are per-interface): not verified. Worth a look at the App Center description before 13A.

## The decision, in one pass

Decided by Cyril on 2026-09-13. Recorded here as the decision of record; the work proceeds ticket by ticket, each with its own verification read back.

| # | decision | outcome |
|---|---|---|
| 12A | snapshot schedule on the `Web` volume (daily, bounded retention, explicit snapshot space) | **declined by Cyril, 2026-09-13: no snapshotting on the NAS.** The policy of record is therefore "no snapshots"; the residual risk is recorded in ticket 12, and the metadata's protection is the Git history (on the admin workstation and off-site) plus the off-NAS payload copy. |
| 12B | off-NAS copy target for the metadata | **approved as recommended** — an HBS job *and* a pushed Git history |
| 12C | where the restore drill restores to, and the payload classification's off-NAS rule | **approved as recommended** — drill on the second device, classify before copying |
| 13A | install QuFirewall on the NAS | **network segregation chosen instead** — no firewall app is to be installed; the restriction comes from where clients can reach the NAS, not from a rule on it |
| 13B | the allowlist: one fleet subnet, or the Wi-Fi subnets too | **one subnet** — `192.168.88.0/24`; the two Wi-Fi ranges are treated as a network-path defect to fix, per the recommendation above |
| 13C | how the negative case is verified (or recorded as unverified) | **no such source — the negative case is recorded as not verified by us**, with exactly what remains unverified stated (Cyril, 2026-09-13). Ticket 13 carries this as a decision, not as a gap discovered later. |
| 13D | `myQNAPcloud` status verified as part of the evidence | **verified read-only from the NAS** — installed and enabled, but **no QNAP ID linked, no service published, no DDNS name of our own, Auto Router Configuration force-disabled**. What stays open is gateway-side only. Evidence: `docs/evidence/13-myqnapcloud-and-reachability-state-2026-09-13.txt` |

### What 13D's check found

Read-only, from the NAS itself, with the sources named in the evidence file:

- `myQNAPcloud` is installed **and enabled** (v1.1.100) — the capability exists and could be switched on from the UI. That is the one thing the app list settles.
- Nothing links the NAS to a QNAP account: both `qid_hash.conf` files are **0 bytes**. No linked ID, no relay path.
- Nothing is published: the QNAP DDNS publish map is `-1` across the board, and every third-party DDNS provider block is disabled with an empty username.
- The NAS does **not** open its own ports on the gateway — Auto Router Configuration is force-disabled with QTS's own reason code (`QTSMQC00-313`).
- A separate fact for 12B: HBS 3's cloud connector has **0 accounts and 0 credentials**, so there is no cloud destination configured today — consistent with the approved off-NAS copy being another device plus the metadata's Git history, not a cloud service.
- **Not verified by us:** whether the NAS is reachable from the public internet. The intended off-network probe was blocked by the browser backend's address guard and was not worked around, and no off-network vantage point is available to the agent. The remaining unknown is gateway-side — a hand-made port-forward, and whether the ISP address is public or carrier-shared. That is a UI fact, and it is recorded as unverified rather than assumed either way.


### What 13A's answer changes

Choosing network segregation over a firewall means the restriction is a property of the **path**, not of a rule set on the NAS:

- Nothing is installed on the NAS, so there is no new service, no default-deny posture to survive, and nothing to roll back on the NAS itself.
- The repository's reachability becomes a function of the client network: a client that can route to `192.168.88.188:80` is allowed by construction. Whatever segments the network (the Unifi switch, the Deco mesh, or a new VLAN) is where the work lands, and that is a network change with its own blast radius — every client on the affected segment, not just Munki.
- It changes what the ticket can *prove*: with no rule to point at, the evidence is a routing/segment fact ("a device outside the allowed path cannot reach the endpoint, because there is no route") rather than a firewall refusal. The ticket's own wording allows that — *"If no such source can be used, the ticket records that the negative case was not verified by us and states exactly what remains unverified, rather than claiming it."*
- It also means the five other things that share port 80 (the whole `Web` share) are **not** restricted by this work. That is a deliberate narrowing to record, not an oversight: the metadata path is the one that must not be reachable from outside the fleet.

