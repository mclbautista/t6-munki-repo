# fleet-ssh-access — where this stopped, and what is next

Written 2026-09-15 00:55 at head `e9c833d`, at the end of the session that closed wave 1 and opened the
remaining fleet. Every claim below was read back from the system it describes; nothing is carried from
memory.

## State at the stop

| thing | state | how it was checked |
|---|---|---|
| Repository | `e9c833d` on `main`, pushed, tree clean | `git ls-remote origin refs/heads/main` == `HEAD`; `git status --short` empty |
| Tests | **288 passing** | `/usr/bin/python3 -m pytest`, run bare, staged |
| Ticket 01 | **done** (7/7) — the explicit SSH transport contract | ticket |
| Ticket 02 | **done** (8/8) — pilot authorized and observed; **the rollback drill was RUN and verified**, commit `70b5df5` | `docs/evidence/02-pilot-access-2026-09-14.txt` §7 |
| Ticket 03 | **done** (8/8) — wave 1: all four machines authenticate, trust verified, `complete: True` run | `docs/evidence/03-wave-1-before-state-2026-09-14.txt` and `docs/evidence/03-wave-1-after-state-2026-09-14.txt` |
| Ticket 04 | **2 of 9** — read-only half done (enumeration + sweep + one disposition per machine); 3-9 wait on the operator | `docs/evidence/04-remaining-fleet-enumeration-and-sweep-2026-09-15.txt` |
| Ticket 05 | **blocked by 04** — the writer cutover | ticket |
| Access map | **5 records**: `Sixto-5`, `202-TOC-M4-Max`, `202-Mac-Pro-3`, `202A-Mac-Mini-M4`, `202B-Mac-Studio` | `data/ssh-access.json` |
| Observation store | 79 records / 11 runs; **5 machines ever observed**, 4 of them on their own manifest | newest reading per serial, printed |
| Collector host | **`Cyrils-Mac-mini`** (192.168.88.202, serial `RWJ57V9PW4`) — **not** the admin workstation `Sixto-5` (.151) | `scutil --get LocalHostName`, `ipconfig getifaddr en0`, `system_profiler` |

## What the session did, in order

1. **Ticket 02's last criterion**: the operator ran the rollback drill at the pilot; the end state was
   verified from this host (one key, right fingerprint, 105 bytes, `0600`/`0700`, no `.drill` residue),
   the drill's writes were visible in an mtime that moved, and the pilot's own report predated the drill —
   so no Munki client data was touched. The **intermediate refusal was not observable** here and the
   ticket says so rather than implying otherwise.
2. **Ticket 03, executed**: `202-Mac-Pro-3` and `202B-Mac-Studio` authorise and are verified;
   `202A-Mac-Mini-M4` did **not**, and the cause was **this set's own instruction** — it named `~t6` on a
   machine whose only account is `t6macminim4pro01`, so the shell refused to expand the path and the key
   was written nowhere. Fixed; its host key was then verified by two independent reads and trusted.
3. **Ticket 11 built and exercised**: `tools/onboard-munki-client.sh` +
   `docs/procedures/client-onboarding.md`. Two machines that had **no Munki client at all** now resolve
   their own machine manifests, verified by reading each machine's report back rather than from the
   operators' pasted blocks.
4. **Ticket 04's read-only half**: enumerated 19 identities → 17 expected targets → 14 remaining, and
   swept every one (ICMP, a TCP connect to 22 with *refused* and *timeout* kept apart, and each machine's
   mDNS binding) for one source-grounded disposition each.

## The next step

**The operator's half of ticket 04, then Hermes's half.** The runbook is
`~/T6-Ops-Docs/runbooks/fleet-ssh-ticket04-remaining-fleet-2026-09-15.html`: eleven steps, six machine
blocks (Remote Login **then** the key), and three steps Hermes runs.

1. **Approve the six-machine set** — `201-Viewing-Room` .170, `202-Jason-M2-Max` .179,
   `202-Tim-M2-Max-9` .180, `202C-Studio-M1-Ultra` .181, `303D-Mac-Studio-M2` .193,
   `T6-MacBook-M4-Max` **.82** (the inventory's .100 does not answer).
2. **Hermes**: verify each, write `known_hosts` entries **only** where the served key and the machine's
   own fingerprint agree, add the map records, then run the fleet observation over all 17 targets with
   `--from-inventory data/machines.json --local-host Cyrils-Mac-mini`.
3. **`202A-Mac-Mini-M4` still needs enrolment** — one `sudo` command, staged on it already (bash
   `onboard-munki-client.sh`); it is the third wave machine that had no Munki client.
4. **Author the enrolment-backlog ticket** — see the rollout set's handoff; no ticket owns "which Macs
   actually have a Munki client".

## What a successor must not redo

- **Do not authorize a key with `~t6`.** Use `~/` at the machine after a `whoami`. The failure mode reads
  exactly like a wrong key and is not one.
- **Do not write a `known_hosts` entry from one read.** Two independent reads (what the machine serves,
  and what it says about itself) or it is a blind accept.
- **Do not probe with plain `ssh t6@<ip>`.** The fleet key is not a default identity name, so that form
  cannot work; the collector's own argv carries no `-i` either, which is why a destination must be
  covered by a stanza in the collector host's `~/.ssh/config`.
- **Do not put a pre-image of a repo file inside the repo tree.** They go to
  `~/.munki-fleet/pre-images/` (this repo has no ignore rule for `*.bak*`).
- **Do not rewrite the role matrix with LF.** It is CRLF because it is edited in a spreadsheet; verify a
  small change with `git diff --numstat`, because LF rewrites turn three rows into twenty changed lines.
- **Do not tick a criterion without changing its mark.** A "MET" disposition beside `- [ ]` was written
  in this session and caught only by the tick counts in the criteria check.

## Already decided, so nobody re-opens it

- The map holds **destinations only**; how the credential is presented lives in the collector host's ssh
  config (ADR/ticket 01). No credential may enter Git, the map, logs, the store, or a ticket.
- A machine with no record is probed **by its inventory address** and carries `no-access-record`; a
  malformed or contradicted record **blocks** the probe instead of falling back.
- A locally reached target has **no ssh record at all**: `--local-host` is that transport's declaration.
- **No passwords and no `sudo -S`**: passwordless sudo does not exist on these machines and piping a
  password is blocked by policy, so every privileged step is handed to the operator as one command.
- **The wave-level rollback is not exercised, by Cyril's explicit direction** (2026-09-14 23:38). Ticket
  02's drill did exercise this class of change; the acceptance is recorded in ticket 03's evidence §9.

## Skills the next session should load

`t6-implementation-workflow` (the ticket discipline, the criteria check, the pitfalls this session added),
`munki` and `munki-nas-workflows` (the repository and the NAS), `mac-fleet-state-observation`,
`t6-mac-mini`, `tutorial-html` (the runbooks and its verifier), `update-projects-db`, `obsidian`.
