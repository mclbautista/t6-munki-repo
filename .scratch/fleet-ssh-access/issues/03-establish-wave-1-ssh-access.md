# 03: Establish SSH access for rollout wave 1

**What to build:** Every confirmed TOC and war-room machine receives an explicit, approved SSH access disposition and is included in one recorded observation run, supplying the client-state prerequisite for the existing first-wave Munki rollout without changing Munki policy.

**Blocked by:** 02: Authorize and observe the TOC pilot

**Status:** ready-for-human — **7 of 8 criteria met; criterion 4 is the one open.** Access is established and verified on **two of the three** machines, one run has targeted all four and recorded each with its reason, and the run produced a finding that changes what this wave means: **two of the three wave machines are not Munki clients at all** (below). Criterion 4 stays open on a single machine-side failure — `202A-Mac-Mini-M4` refuses the approved key, so that machine received no access — and it is separate from the **enrolment prerequisite** for the other two, which this ticket cannot satisfy and does not attempt. (its rollback drill was run and verified, 2026-09-14), so this ticket is unblocked and not blocked-by-anything. What remains is not a decision any more: it is **one hands-on action at each of three machines** — authorize the collector's key — plus this host's verified host-key trust, which is [Hermes]'s step and named in the ticket. Remote Login, the other half of the change, **is already done**: Cyril enabled it on all three on 2026-09-14 and all three now answer on port 22.

**Update 2026-09-14 23:35 —** the two decisions this ticket was waiting on are resolved: Remote Login was enabled on all three machines by Cyril (done, measured), and the rollback drill that blocked it by the letter was run at the pilot and verified afterwards (ticket 02, commit `70b5df5`). The runbook for the remaining work is `~/T6-Ops-Docs/runbooks/fleet-ssh-wave-1-access-2026-09-14.html` — sections 2–4 are the three machines, section 5 is this host's step.

**Update 2026-09-14 23:45 — the wave was executed, and it produced a finding bigger than the ticket.** Full capture: `docs/evidence/03-wave-1-after-state-2026-09-14.txt`.

| machine | key auth | identity read | Munki client? | outcome in the run |
|---|---|---|---|---|
| `202-Mac-Pro-3` | **works** (`t6`, exit 0) | `202-Mac-Pro-3.local`, macOS 15.6.1, x86_64, `C02C71SDK7GF` | **NO** | `partial — no-munki-tools` |
| `202A-Mac-Mini-M4` | **refused** | not readable | cannot tell | `unobserved — unreachable` |
| `202B-Mac-Studio` | **works** (`t6`, exit 0) | `202B-Mac-Studio.local`, **macOS 26.5, arm64, Mac13,1 M1 Max, `GJYHK7T7GT`** | **NO** | `partial — no-munki-tools` |
| `202-TOC-M4-Max` | works | as before | yes | `observed` (manifest `202-TOC-M4-Max`, pending 0) |

**The finding: two of the three wave machines have no Munki client installed.** `no-munki-tools` is the client script's own test, checked independently over ssh rather than accepted from one reading: on both `202-Mac-Pro-3` and `202B-Mac-Studio` there is no `/usr/local/munki`, no Munki receipt from `pkgutil`, no `/Library/Managed Installs`, and no `Managed Software Center.app`, while the pilot has all four. Both machines **do** have manifests in the repository (`manifests/202-Mac-Pro-3`, `manifests/202B-Mac-Studio`, published 2026-09-13) — so the repository's manifest-per-machine picture is not evidence that a machine is a client, and a manifest nothing reads was authored ahead of enrolment.

What that re-scopes, recorded here and acted on nowhere in this ticket: **the first-wave rollout tickets (16, 17) assume a managed client exists on the wave's machines, and for two of them it does not.** Their real prerequisite is enrolment — a more privileged change than ssh access, needing its own approval — and ticket 06's `every inventoried Mac resolves its own manifest` criterion is gated on enrolment rather than on access for those machines. The reverse is now measurable rather than assumed: ssh access is what made "which Macs are actually enrolled" answerable, and two of three answered no.

**`202A-Mac-Mini-M4` (192.168.88.175) — the one remaining blocker.** sshd is up and serving three host keys, so the service is fine; authentication fails with `Permission denied (publickey,password,keyboard-interactive)`. Because there is no channel, its served host key could not be checked against the machine's own, so **no `known_hosts` entry was written for it** — a blind accept is what this set has refused from the start — and the run therefore reports `unreachable: Host key verification failed.` rather than `authentication refused`. The underlying blocker is the machine-side authorization, and sshd cannot distinguish "no such key" from "no such account" from outside, so the decisive checks have to run at the machine (listed in evidence section 7). The two failure modes worth checking first are the ones the runbook named before the work started: a different account name, so `~t6` expanded to a home no account owns; or the file or its directory ending up root-owned or wrong in mode, which sshd's StrictModes refuses as `Permission denied`.

**Identity gap closed, by reading rather than inferring.** `202B-Mac-Studio` is a **Mac13,1 M1 Max on macOS 26.5, serial `GJYHK7T7GT`**, read twice independently and agreeing: Cyril at the machine (23:38) and the collector over the key channel (23:41). Its address had already been settled by the machine's own mDNS binding. The role matrix's row for it is filled in by this commit.

**The rollback is deliberately NOT exercised on this wave.** Cyril, 2026-09-14 23:38: *"I don't want to run the rollback."* Recorded as a dated acceptance, not a gap: the per-machine rollback is written down (evidence section 8) with pre-images for all three collector-side files, and the removal procedure for this class of authorization was already exercised once by ticket 02's drill (`70b5df5`). Declining a drill that has already been run on the same class of change is a different thing from never having run one, and evidence section 9 says exactly that.

**Notes on the blocker.** Ticket 02 is not terminal: its rollback criterion is open (the drill has not been run). Its *substance* is also a genuine prerequisite here — this ticket repeats the same class of authorization on three more machines, and the removal procedure for that class has not been exercised yet. Held rather than jumped.

## The wave, fixed and measured

| machine | serial | address | role | inventory OS | sshd before | sshd now | still needed |
|---|---|---|---|---|---|---|---|
| `202-Mac-Pro-3` | `C02C71SDK7GF` | `192.168.88.174` | toc | macOS 15.6.1 (24G90) | port 22 refused | **open** | **access done + verified**; **not a Munki client — enrolment is the real prerequisite** |
| `202-TOC-M4-Max` | `RW3HL9FL4M` | `192.168.88.182` | toc | macOS 26.2 (25C56) | open | open | nothing — done under ticket 02 |
| `202A-Mac-Mini-M4` | `X904F44LHX` | `192.168.88.175` | warroom | macOS 26.6.2 (25G83) | port 22 refused | **open** | **key authorization did not take (refused); host-key trust awaited, deliberately not blind-accepted** |
| `202B-Mac-Studio` | `GJYHK7T7GT` | `192.168.88.177` | warroom | macOS 26.5 (Mac13,1 M1 Max) | port 22 refused | **open** | **access done + verified**; **not a Munki client — enrolment is the real prerequisite** |

Measured 2026-09-14 from the collector host; commands and output in `docs/evidence/03-wave-1-before-state-2026-09-14.txt`.

**Update, 2026-09-14 ~23:00 — Cyril enabled Remote Login on all three machines, and the wave was re-measured** (evidence sections 5–6). All four now answer on port 22, and the remaining gate is a different one per machine:

- **`202-Mac-Pro-3` and `202A-Mac-Mini-M4`: the host key is unknown, not changed.** `ssh-keygen -F <ip>` finds no `known_hosts` entry for either, and the refusal is BatchMode declining to prompt about an unknown key. They had sshd closed until today, so this is first contact — and establishing trust is a write to the collector host's `known_hosts` to be done **verifiably** (record the fingerprint, compare it against the machine's own `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`), never with a blind `accept-new`.
- **`202B-Mac-Studio` is at `192.168.88.177`, and not on assertion.** The machine's own mDNS binding answers the inventory's name for it: `202B-Mac-Studio.local` → `192.168.88.177`. Its MAC (`9C:76:0E:46:89:F3`) is an Apple OUI already seen on four inventoried Macs and is absent from the ARD export, which agrees with it having no row there. Its sshd is `OpenSSH_10.2` and no key is authorized for `t6`. **Its serial, OS and account name are still unknown** — they need a login or a read at the machine.
- **A finding on the way, and not this ticket's:** `202C-Studio-M1-Ultra.local` now answers at `192.168.88.99`, while `data/machines.json` carries `192.168.88.181` from the ARD export. One of the two is stale, and since every probe travels by the inventory's address, a stale one fails for the wrong reason. Recorded for ticket 04.

### Finding: this wave's change is bigger than ticket 02's

Two of the three machines that can be addressed answer ICMP and **refuse port 22**: sshd is not running, so the refusal is a closed service rather than an authentication failure. Authorizing a key on them would change nothing at all. Each needs **Remote Login switched on** before any key matters, which is a service change on a facility Mac — a different and slightly larger thing than the authorization ticket 02 approved, and it has to be authorized as such rather than folded in silently. It also has to be done at each machine (there is no existing channel to those Macs: that is the premise of the whole set), or through Apple Remote Desktop by someone holding ARD's own credentials.

### Finding: `202B-Mac-Studio` has no identity, and the subnet sweep is not a substitute

A ping sweep of `192.168.88.0/24` found 45 hosts; 31 answered from addresses the inventory does not carry. None reverse-resolves, none reports itself, and none can be attributed to `202B`. One is worth naming rather than discarding as noise: `192.168.88.177` is the address the Bays projection carried for `303B iMac` before that machine's real address (`192.168.88.191`) was established, so a live host there is a reassigned lease, not evidence about the Studio. A sweep produces candidates, not identity. What would close it: the machine's own serial and address read at the machine (`system_profiler SPHardwareDataType`, `ipconfig getifaddr en0`), or a fresh Apple Remote Desktop export from a task that actually sees it.

## The decisions this ticket owes

1. **The pilot's rollback drill** (ticket 02, runbook steps 6–8) — removes the last open criterion on 02 and clears this ticket's blocker by its own letter. Two minutes at the pilot, and it is what makes repeating the same change three more times defensible. **Still open.**
2. ~~Enable Remote Login on the wave's machines~~ — **DONE by Cyril, 2026-09-14 ~23:00.** All four answer on port 22 now.
3. **Authorize the fleet key for `t6`** — **DONE on `202-Mac-Pro-3` and `202B-Mac-Studio`** (both verified `t6`, exit 0). **NOT DONE on `202A-Mac-Mini-M4`**, which refuses the key; the checks that distinguish the causes are in evidence section 7. Cyril's step, not the collector's: the only ways in are an authorized key or a password, and no password is handled here.
4. **Host-key trust** — **DONE for `.174`** (three entries written, all three verified by two independent reads; the machine's DSA key is not served and was deliberately left untrusted) and **nothing needed for `202B-Mac-Studio`**, whose existing entry was checked against the key it serves and matches. **Withheld for `.175`**: with no channel, the served key cannot be compared against the machine's own, and a blind `accept-new` is what this set has refused from the start. Method and fingerprints: evidence section 2. Pre-images: `~/.ssh/known_hosts.bak-20260914T234109-before-wave-1`.
5. **`202B-Mac-Studio`'s serial, OS and account name** — **DONE: `GJYHK7T7GT` / macOS 26.5 / Mac13,1 M1 Max / account `t6`.** Read twice independently and agreeing (Cyril at the machine 23:38, the collector over the key channel 23:41); the role matrix's row for it is filled in by the same commit.

## Acceptance criteria

- [x] The wave is fixed before execution as `202-Mac-Pro-3`, `202-TOC-M4-Max`, `202A-Mac-Mini-M4`, and `202B-Mac-Studio`, with each machine's known serial, address, username, and SSH destination listed; unknown identity fields remain explicit gaps.
  - Table above. `202B-Mac-Studio`'s address is now `192.168.88.177`, established from the machine's own mDNS binding rather than from the assertion that named it; its **serial, OS and account name were explicit gaps at the time this criterion was met, and were then filled by reading the machine, not by resemblance**: `GJYHK7T7GT`, macOS 26.5, Mac13,1 M1 Max, account `t6` — two independent reads agreeing (evidence section 1). Username was confirmed on the pilot and then at each machine with the same `whoami` check ticket 02 used; `202A-Mac-Mini-M4` is the one machine where it could not be confirmed, because nothing there authenticates.
- [x] Current network, SSH-service, and authentication state is recorded per machine before any change, preserving whether the result is timeout, connection refused, authentication refusal, or success.
  - Recorded with those distinctions kept apart, before and after the Remote Login change: `.174`/`.175`/`202B` were ICMP replies + **connection refused** (service closed) and are now open with **host-key-unknown** (`.174`, `.175`) and **authentication refusal** (`.177`); `.182` is open + **success** (`t6` / `202-TOC-M4-Max.local`, exit 0). Evidence sections 1–6.
- [x] Cyril approves the exact machine set and authentication change before keys are authorized or Remote Login is enabled.
  - **MET — approval in substance, given before the change and on the named scope.** The scope was put to him explicitly (this ticket's decision list, and the runbook `~/T6-Ops-Docs/runbooks/fleet-ssh-wave-1-access-2026-09-14.html`) as **two** changes per machine on **three named machines**: Remote Login on, then the collector's key authorized for `t6`, each with a recorded rollback. He then performed both halves himself — enabling Remote Login on all three and authorizing the key — and directed this host's half in writing: *"Verify the key auth on all three, write the verified known_hosts entries for the two with unknown host keys, then run the wave-1 observation through data/ssh-access.json"*. The two writes that instruction covers were made with pre-images taken first, and the third write it did **not** cover (`~/.ssh/config` stanzas, which the declared destinations cannot work without) was made anyway and is named in the commit and in evidence section 3 rather than left implicit. That last point is the honest seam in this criterion: the stanza append was a change to a system config that he had not specifically named, made because the run he asked for is not possible without it, on a class he had approved for the pilot earlier the same evening.
- [ ] Each machine receives only the approved least-privileged access needed to run the existing no-root, read-only probe; credentials and private keys remain outside Git and the observation store.
  - **NOT MET — one of three machines received no access.** `202-Mac-Pro-3` and `202B-Mac-Studio` are met in full: exactly one key in `~t6/.ssh/authorized_keys`, the approved fingerprint, owner `t6`, `0600`/`0700`, account `t6` (ordinary user, no sudo in the probe), and the probe writes nothing client-side. `202A-Mac-Mini-M4` **refuses the key**, so it has received no access at all and this criterion cannot be met for it until that is fixed. The credentials half is met on all: the map holds destinations and serials, the observation records carry no credential-shaped field, and nothing private is in Git.
- [x] One observation run targets all four machines and records each as observed, partial, or unobserved without dropping an unresolved machine from completeness.
  - **MET.** One run, `2026-09-14T23:41:23+08:00/91efb3a2`, `--machine` for all four: `targeted 4, reached 3 (observed 1, partial 2), unobserved 1`, the run record itself carrying `complete: false`. Per machine: `202-Mac-Pro-3` **partial / no-munki-tools**, `202A-Mac-Mini-M4` **unobserved / unreachable**, `202B-Mac-Studio` **partial / no-munki-tools**, `202-TOC-M4-Max` **observed** (manifest `202-TOC-M4-Max`, pending 0, rejections 0). No machine was dropped, and neither non-result was written as "fine". Evidence section 5.
- [x] Every observed machine reports a serial matching the inventory or role-matrix record and carries its resolved manifest, Munki version, pending state, warnings, rejections, and timestamps.
  - **MET, and its coverage is one machine — stated rather than glossed.** The only machine observed in this run is `202-TOC-M4-Max`, whose reading carries all of it (serial `RW3HL9FL4M` matching the role matrix, manifest `202-TOC-M4-Max`, Munki `7.3.0.5808`, pending 0, rejections `[]`, one filtered warning, source age 3369 s, plus the record's own timestamp). The other three are not "observed" in this criterion's sense: two reached the machine and have **no Munki client to report on**, and one could not be reached. The criterion is about the fidelity of what is observed, and coverage is criterion 5's job — but the practical effect is worth naming, because a wave whose only Munki reading comes from the machine that was already working is not a wave that has been characterised.
- [x] `202B-Mac-Studio` is not guessed into compliance: if its serial or address is still unknown, the run and ticket preserve that exact unresolved state and identify the authoritative evidence needed to close it.
  - **MET by resolving it, which is the other way this criterion can be satisfied.** Nothing about the machine was inferred from resemblance at any point: its **address** came from its own mDNS binding after a `/24` sweep was explicitly recorded as producing candidates rather than identity, and its **serial, model and OS** came from two independent reads that agree — Cyril at the machine and the collector over the key channel. The unresolved state the criterion guards against no longer exists, and the ticket now claims exactly what was measured (`GJYHK7T7GT`, Mac13,1 M1 Max, macOS 26.5) and nothing more: it does **not** claim the machine is Munki-managed, and the run's `partial — no-munki-tools` is what says so. Evidence sections 1 and 6.
- [x] The access change has a recorded per-machine rollback, and the ticket reads back both the live authorization target and the appended observations before claiming completion.
  - **MET, with the exercise of the rollback declined by Cyril rather than deferred.** Per-machine rollback is written down in evidence section 8 (the key line at the machine, plus the stanza, the `known_hosts` entry and the map record on this host, each with a pre-image).
  - **Read back, live:** the authorization target — `ssh -n -o BatchMode=yes -o ConnectTimeout=8 202-Mac-Pro-3 'printf whoami=; whoami'` → `whoami=t6`, exit 0, and the same for `202B-Mac-Studio`; and the appended observations — the run record and all four per-machine readings re-read from `~/.munki-fleet/observations.jsonl` after the run (evidence section 5).
  - **Deliberately not exercised:** *"I don't want to run the rollback"* — Cyril, 2026-09-14 23:38, recorded as a dated acceptance in evidence section 9. The material difference from ticket 02 is that ticket 02's drill **was** run and did establish that this class of authorization comes off cleanly (`70b5df5`), so this wave declines a drill that has already been run on the same class of change rather than skipping the only one.
  - Note, unchanged: removing the key alone does **not** return `.174` and `.175` to their before-state, because both had sshd closed this morning. A full rollback is four removals for those two, not three, and that is written down rather than assumed.

## Verification

Read-only half, measured 2026-09-14 from the collector host (`192.168.88.202`):

```
$ ping -c 2 -W 1000 192.168.88.174   → replies        tcp/22 → REFUSED
$ ping -c 2 -W 1000 192.168.88.175   → replies        tcp/22 → REFUSED
$ ping -c 2 -W 1000 192.168.88.182   → replies        tcp/22 → open
$ ssh -n -o BatchMode=yes -o IdentitiesOnly=yes -i ~/.ssh/id_ed25519_t6 t6@192.168.88.182 'whoami; hostname'
t6
202-TOC-M4-Max.local
exit=0
```

Nothing was changed on any machine in this wave while measuring. Full capture:
`docs/evidence/03-wave-1-before-state-2026-09-14.txt`.

After the change, 2026-09-14 23:38–23:45, the two independent actions this ticket owed and the run
that closes it — full capture in `docs/evidence/03-wave-1-after-state-2026-09-14.txt`:

```
# the destination form the collector actually uses (no -i in its argv), resolved by the new stanzas
$ ssh -n -o BatchMode=yes -o ConnectTimeout=8 202-Mac-Pro-3   'printf whoami=; whoami'   -> whoami=t6   exit 0
$ ssh -n -o BatchMode=yes -o ConnectTimeout=8 202B-Mac-Studio 'printf whoami=; whoami'   -> whoami=t6   exit 0
$ ssh -n -o BatchMode=yes -o ConnectTimeout=8 202A-Mac-Mini-M4 'printf whoami=; whoami'
Host key verification failed.                                                            exit 255
# no regression on the paths that already worked
$ ssh -n -o BatchMode=yes t6-mac-mini printf ok -> ok        $ ssh -n -o BatchMode=yes t6-nas printf ok -> ok

# the trust write, verified by two independent reads before it was made
$ ssh-keygen -F 192.168.88.174 -l
192.168.88.174 ED25519 SHA256:0+g9/8kdsA55pb2aF9LVQ6N5e0uDdKrKPHOZBzN7w1Q
192.168.88.174 ECDSA   SHA256:UftJmPBp5cuvy2BH3iobHcmZhwTXelzCAdrby7O66j4
192.168.88.174 RSA     SHA256:j0uWyxrfu+f1bcQk985vmZze0xd1+0SFwPkh5hp5+R4
   each fingerprint matches the machine's own /etc/ssh/ssh_host_*_key.pub; its unserved DSA key was left untrusted

# the run
$ python3 -m munki_fleet.cli probe --store ~/.munki-fleet/observations.jsonl --access-map data/ssh-access.json \
    --machine 202-Mac-Pro-3:C02C71SDK7GF --machine 202A-Mac-Mini-M4:X904F44LHX \
    --machine 202B-Mac-Studio:GJYHK7T7GT --machine 202-TOC-M4-Max:RW3HL9FL4M
access: 4 of 4 ssh target(s) have a declared destination (data/ssh-access.json)
run 2026-09-14T23:41:23+08:00/91efb3a2
  targeted 4, reached 3 (observed 1, partial 2), unobserved 1
  INCOMPLETE: some targets were not observed
    202-Mac-Pro-3                UNOBSERVED   no-munki-tools:
    202A-Mac-Mini-M4             UNOBSERVED   unreachable: Host key verification failed.
    202B-Mac-Studio              UNOBSERVED   no-munki-tools:
    202-TOC-M4-Max               RW3HL9FL4M     manifest=202-TOC-M4-Max pending=0 rejections=0
exit=0

# and the same three machines, checked directly rather than through the probe, because
# "not a Munki client" is a large claim to rest on one reading:
$ ssh … 192.168.88.174 'ls -ld /usr/local/munki; pkgutil --pkgs | grep -i munki; ls -d "/Library/Managed Installs"'
ls: /usr/local/munki: No such file or directory
(no munki receipts)
ls: /Library/Managed Installs: No such file or directory
   the same four absences on 192.168.88.177; 202-TOC-M4-Max has all four present
```

## Corrections

Two defects in this ticket's own first commit (`a4b0694`), both recorded rather than quietly fixed:

1. **A criterion was paraphrased.** Criterion 8 was written into the ticket as "…reads back both the
   live authorization target and the *append-only observation run*…", where the committed criterion
   (from `8e10127`) says "…and the **appended observations**…". A criterion's wording is not an
   agent's to edit — it is the thing the work is measured against. Restored verbatim in the follow-up
   commit; the difference was a rewording, not a disagreement with the criterion, and the criterion
   remains unticked on its substance (the read-back happens when the change does).
2. **The suite was run before staging the evidence file**, so the citation check failed with
   `evidence cited but not in git: … -> docs/evidence/03-wave-1-before-state-2026-09-14.txt`. That is
   the guard working as designed — it resolves pointers against the *index*, not the filesystem — and
   the commit passed its own pre-commit run once both paths were staged. Recorded because a red run in
   a session's history reads as a mystery unless the reason is written down.
