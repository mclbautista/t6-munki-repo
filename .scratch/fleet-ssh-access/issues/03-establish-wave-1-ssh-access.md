# 03: Establish SSH access for rollout wave 1

**What to build:** Every confirmed TOC and war-room machine receives an explicit, approved SSH access disposition and is included in one recorded observation run, supplying the client-state prerequisite for the existing first-wave Munki rollout without changing Munki policy.

**Blocked by:** 02: Authorize and observe the TOC pilot

**Status:** ready-for-human — the wave is fixed and its before-state is measured (criteria 1 and 2 met); **everything that changes a machine waits on two decisions, below.**

**Notes on the blocker.** Ticket 02 is not terminal: its rollback criterion is open (the drill has not been run). Its *substance* is also a genuine prerequisite here — this ticket repeats the same class of authorization on three more machines, and the removal procedure for that class has not been exercised yet. Held rather than jumped.

## The wave, fixed and measured

| machine | serial | address | role | inventory OS | sshd before | sshd now | still needed |
|---|---|---|---|---|---|---|---|
| `202-Mac-Pro-3` | `C02C71SDK7GF` | `192.168.88.174` | toc | macOS 15.6.1 (24G90) | port 22 refused | **open** | host-key trust; key authorization |
| `202-TOC-M4-Max` | `RW3HL9FL4M` | `192.168.88.182` | toc | macOS 26.2 (25C56) | open | open | nothing — done under ticket 02 |
| `202A-Mac-Mini-M4` | `X904F44LHX` | `192.168.88.175` | warroom | macOS 26.6.2 (25G83) | port 22 refused | **open** | host-key trust; key authorization |
| `202B-Mac-Studio` | *unknown* | `192.168.88.177` | warroom | *unknown* | port 22 refused | **open** | its serial; key authorization |

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
3. **Authorize the fleet key for `t6`** on `202-Mac-Pro-3`, `202A-Mac-Mini-M4` and `202B-Mac-Studio`. This is Cyril's step, not the collector's: the only ways in are an authorized key (none yet) or a password, and no password is handled here. The command is ticket 02's step 4, per machine, at the machine.
4. **Host-key trust for `.174` and `.175`** — mine to do once the keys are authorized, but it is a write to the collector host's `known_hosts`, so it is named here rather than done quietly. Method: record the served key's fingerprint, compare it against the machine's own `/etc/ssh/ssh_host_ed25519_key.pub`, then write the entry. No blind `accept-new`.
5. **`202B-Mac-Studio`'s serial, OS and account name.** Its address is settled; its identity is not. Read at the machine: `system_profiler SPHardwareDataType | grep -E 'Serial|Model'` and `ipconfig getifaddr en0`.

## Acceptance criteria

- [x] The wave is fixed before execution as `202-Mac-Pro-3`, `202-TOC-M4-Max`, `202A-Mac-Mini-M4`, and `202B-Mac-Studio`, with each machine's known serial, address, username, and SSH destination listed; unknown identity fields remain explicit gaps.
  - Table above. `202B-Mac-Studio`'s address is now `192.168.88.177`, established from the machine's own mDNS binding rather than from the assertion that named it; its **serial, OS and account name remain explicit gaps**, filled by resemblance nowhere. Username is `t6` by fleet convention — confirmed on the pilot, and to be confirmed at each machine with the same `whoami` check ticket 02 used before its key was authorized.
- [x] Current network, SSH-service, and authentication state is recorded per machine before any change, preserving whether the result is timeout, connection refused, authentication refusal, or success.
  - Recorded with those distinctions kept apart, before and after the Remote Login change: `.174`/`.175`/`202B` were ICMP replies + **connection refused** (service closed) and are now open with **host-key-unknown** (`.174`, `.175`) and **authentication refusal** (`.177`); `.182` is open + **success** (`t6` / `202-TOC-M4-Max.local`, exit 0). Evidence sections 1–6.
- [ ] Cyril approves the exact machine set and authentication change before keys are authorized or Remote Login is enabled.
  - **NOT MET — awaiting Cyril.** The ask is now explicit and larger than the ticket assumed: two changes per machine (Remote Login on, then the key authorized), on two named machines, each with the rollback below.
- [ ] Each machine receives only the approved least-privileged access needed to run the existing no-root, read-only probe; credentials and private keys remain outside Git and the observation store.
- [ ] One observation run targets all four machines and records each as observed, partial, or unobserved without dropping an unresolved machine from completeness.
- [ ] Every observed machine reports a serial matching the inventory or role-matrix record and carries its resolved manifest, Munki version, pending state, warnings, rejections, and timestamps.
- [ ] `202B-Mac-Studio` is not guessed into compliance: if its serial or address is still unknown, the run and ticket preserve that exact unresolved state and identify the authoritative evidence needed to close it.
  - Partly discharged: it is preserved as unresolved rather than guessed (this ticket does not claim it is compliant, and the sweep is explicitly recorded as insufficient). The run that will carry it as `unobserved — identity unknown` is criterion 5's, which waits on the authorization.
- [ ] The access change has a recorded per-machine rollback, and the ticket reads back both the live authorization target and the appended observations before claiming completion.
  - Rollback recorded per machine in evidence section 4; the live read-back happens when the change does. Note that removing the key alone does **not** return these two machines to today's state — they are closed today, so a full rollback also turns Remote Login off again, and that is written down rather than assumed.

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
