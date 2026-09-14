# 03: Establish SSH access for rollout wave 1

**What to build:** Every confirmed TOC and war-room machine receives an explicit, approved SSH access disposition and is included in one recorded observation run, supplying the client-state prerequisite for the existing first-wave Munki rollout without changing Munki policy.

**Blocked by:** 02: Authorize and observe the TOC pilot

**Status:** ready-for-human — the wave is fixed and its before-state is measured (criteria 1 and 2 met); **everything that changes a machine waits on two decisions, below.**

**Notes on the blocker.** Ticket 02 is not terminal: its rollback criterion is open (the drill has not been run). Its *substance* is also a genuine prerequisite here — this ticket repeats the same class of authorization on three more machines, and the removal procedure for that class has not been exercised yet. Held rather than jumped.

## The wave, fixed and measured

| machine | serial | address | role | inventory OS | sshd today |
|---|---|---|---|---|---|
| `202-Mac-Pro-3` | `C02C71SDK7GF` | `192.168.88.174` | toc | macOS 15.6.1 (24G90) | **port 22 refused** — not running |
| `202-TOC-M4-Max` | `RW3HL9FL4M` | `192.168.88.182` | toc | macOS 26.2 (25C56) | open; key auth works (ticket 02) |
| `202A-Mac-Mini-M4` | `X904F44LHX` | `192.168.88.175` | warroom | macOS 26.6.2 (25G83) | **port 22 refused** — not running |
| `202B-Mac-Studio` | *unknown* | *unknown* | warroom | *unknown* | cannot be probed — no address anywhere |

Measured 2026-09-14 from the collector host; commands and output in `docs/evidence/03-wave-1-before-state-2026-09-14.txt`.

### Finding: this wave's change is bigger than ticket 02's

Two of the three machines that can be addressed answer ICMP and **refuse port 22**: sshd is not running, so the refusal is a closed service rather than an authentication failure. Authorizing a key on them would change nothing at all. Each needs **Remote Login switched on** before any key matters, which is a service change on a facility Mac — a different and slightly larger thing than the authorization ticket 02 approved, and it has to be authorized as such rather than folded in silently. It also has to be done at each machine (there is no existing channel to those Macs: that is the premise of the whole set), or through Apple Remote Desktop by someone holding ARD's own credentials.

### Finding: `202B-Mac-Studio` has no identity, and the subnet sweep is not a substitute

A ping sweep of `192.168.88.0/24` found 45 hosts; 31 answered from addresses the inventory does not carry. None reverse-resolves, none reports itself, and none can be attributed to `202B`. One is worth naming rather than discarding as noise: `192.168.88.177` is the address the Bays projection carried for `303B iMac` before that machine's real address (`192.168.88.191`) was established, so a live host there is a reassigned lease, not evidence about the Studio. A sweep produces candidates, not identity. What would close it: the machine's own serial and address read at the machine (`system_profiler SPHardwareDataType`, `ipconfig getifaddr en0`), or a fresh Apple Remote Desktop export from a task that actually sees it.

## The two decisions this ticket owes

1. **The pilot's rollback drill** (ticket 02, runbook steps 6–8) — removes the last open criterion on 02 and clears this ticket's blocker by its own letter. Two minutes at the pilot, and it is the prerequisite that makes repeating the same change three more times defensible.
2. **This wave's authorization**, which is *two* changes per machine, not one: enable Remote Login, then authorize the fleet key for `t6`. Machines `202-Mac-Pro-3` and `202A-Mac-Mini-M4`; both need Cyril at the machine (or ARD). `202-TOC-M4-Max` is already done under ticket 02.
   - **Option A (recommended):** enable Remote Login and authorize the key on both, then observe. Closes criteria 4–6 and unblocks the Munki rollout tickets 11/16/17 for these machines.
   - **Option B:** authorize nothing on the two Mac Pro/Mini machines yet; wave 1 becomes the pilot alone. Nothing new is exposed, and the observation layer covers one machine instead of three.
   - **Option C:** probe them by hand through Apple Remote Desktop's Send UNIX Command, which needs no sshd. Rejected unless Cyril wants it: it puts a human in the loop of every reading, and ADR 0004 wants one deterministic writer, not a hand-carried payload.
3. **Separately, and smaller:** where does `202B-Mac-Studio`'s identity come from? It cannot be authorized against nothing, and it is the only machine in the fleet nobody can currently describe.

## Acceptance criteria

- [x] The wave is fixed before execution as `202-Mac-Pro-3`, `202-TOC-M4-Max`, `202A-Mac-Mini-M4`, and `202B-Mac-Studio`, with each machine's known serial, address, username, and SSH destination listed; unknown identity fields remain explicit gaps.
  - Table above; `202B-Mac-Studio`'s serial, address and OS are recorded as explicit gaps rather than filled by resemblance. Username is `t6` for the fleet by convention — confirmed on the pilot, and to be confirmed at each machine with the same `whoami` check ticket 02 used before its key was authorized.
- [x] Current network, SSH-service, and authentication state is recorded per machine before any change, preserving whether the result is timeout, connection refused, authentication refusal, or success.
  - Recorded with those distinctions kept apart: `.174` and `.175` = ICMP replies + **connection refused** (service closed); `.182` = open + **success** (`t6` / `202-TOC-M4-Max.local`, exit 0); `202B` = not probed, no address. Evidence sections 1–3.
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
