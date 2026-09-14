# Where this stopped, and what is next

Written 2026-09-15 00:55 at head `e9c833d`. Every claim below was read back from the system it describes;
anything unverified is marked as such.

This file previously described the stop of 2026-09-14 (head `d36b18c`). That version is **superseded
where it disagrees**, and two of its lines are now wrong: the observation store said "1 machine observed"
and the fleet had no access beyond the pilot. Tickets 02, 03, 04, 13 and 15 are unchanged by this session;
**09's nine ticked criteria and 10's three are unchanged too**, and the alerting decision (ADR 0011,
Proposed) is still the open one.

## State at the stop

| thing | state | how it was checked |
|---|---|---|
| Repository | `e9c833d` on `main`, pushed, tree clean | `git ls-remote` == `HEAD`; `git status --short` empty |
| Tests | **288 passing** | `/usr/bin/python3 -m pytest`, run bare, on the staged tree |
| Served catalog | **28 items, 28 unique names**; `catalogs/production` still absent (HTTP 404) | fetched over HTTP from the NAS and parsed with `plistlib`, 2026-09-15 00:52 |
| Ticket 11 | **done** (7/7) — the onboarding procedure exists and was exercised | `tools/onboard-munki-client.sh`, `docs/procedures/client-onboarding.md`, evidence `11-onboarding-verified-2026-09-15.txt` |
| Enrolled clients | **`202-Mac-Pro-3` and `202B-Mac-Studio` newly enrolled**, both resolving their own manifest on tools `7.3.0.5808` (the pilot's own build); `202A-Mac-Mini-M4` **not enrolled** | read back off each machine (`pkgutil`, the client prefs, `ManifestName` from its own report) |
| Observation store | 79 records, 11 runs; **5 machines ever observed** — 4 on their own manifest (`202-Mac-Pro-3`, `202B-Mac-Studio`, `202-TOC-M4-Max`, `Sixto-5`), and **`Cyrils-Mac-mini` on `site_default`** | newest reading per serial, printed from `~/.munki-fleet/observations.jsonl` |
| `manifests/Cyrils-Mac-mini` | **does not exist** (HTTP 404) — and that machine resolves `site_default` | fetched over HTTP; the client's own report says `site_default` |
| Fleet access | tickets 01-03 **done**; **04 read-only half done** (2/9), 14 machines remaining, one disposition each; 05 blocked by 04 | `docs/evidence/04-remaining-fleet-enumeration-and-sweep-2026-09-15.txt` |
| Alerting | unchanged: implemented to the outbox, **delivery not wired**, ADR 0011 Proposed | ticket 15; previous handoff's evidence |
| Enrollment backlog | **nobody owns this question yet**: three of the four wave machines had **no Munki client at all** | measured on the machines, four independent absences each |

## The finding that reshaped this workstream

**The wave's prerequisite was enrolment, not access.** `202-Mac-Pro-3` and `202B-Mac-Studio` had no
`/usr/local/munki`, no Munki receipt, no `/Library/Managed Installs` and no Managed Software Center —
and neither did `202A-Mac-Mini-M4`. All three **had manifests in this repository**, published
2026-09-13, so a manifest per machine is not evidence that a machine is a client: a manifest nothing
reads was authored ahead of enrolment.

What that changes: tickets **16 and 17 assume a managed client exists** on the machines they roll out
to, and ticket **06's** "every inventoried Mac resolves its own manifest" criterion is gated on
enrolment rather than on access for those machines. **`Cyrils-Mac-mini` is the live example** — it has a
client, resolves `site_default`, and this repository serves no manifest named after it.

## The next step

**Three things, in this order, and only the first needs anybody's approval:**

1. **Enrol `202A-Mac-Mini-M4`.** One privileged command, already staged on the machine; the procedure
   and its checklist are `docs/procedures/client-onboarding.md`. Nothing else in wave 1 is outstanding.
2. **Author the enrolment-backlog ticket.** No ticket owns "which Macs actually have a Munki client" —
   the question that cost this session its main finding. The sweep that answers it is the same access
   path as ticket 04, so it can ride along with it. Recommended contents: enumerate every machine in the
   role matrix, record per machine whether a client exists and what it resolves, and feed tickets 06/16/17
   a real enrolment list rather than an assumed one.
3. **Ticket 04's operator half** (six machines: Remote Login then the key), then Hermes's half, then
   ticket 05's cutover — which must recreate the `~/.ssh/config` stanzas and `known_hosts` entries on the
   **admin workstation `Sixto-5` (.151)**, because the collector currently runs on `Cyrils-Mac-mini`
   (.202) and a destination no stanza covers fails as `unreachable`.

Then the standing gates, each needing one decision from Cyril and nothing else:

- **Ticket 10** — the toolchain install it authorises (`ready-for-human`, 3/10). Unblocks 16 with 08.
- **Ticket 07** — the production catalog/promotion decision (`ready-for-human`, 3/7). Unblocks 08 and 09.
- **ADR 0011** — who delivers the alerts. Ticket 15 criterion 1 stays open until it is accepted and wired.
- **Ticket 06** — needs fleet SSH *and* the change on `Cyrils-Mac-mini`: `ClientIdentifier` removed and
  `manifests/Cyrils-Mac-mini` published, or a recorded decision that the machine is meant to sit on
  `site_default`.

## What a successor must not redo

- **Do not install a Munki client with a password or over `sudo -S`.** No passwordless sudo exists on
  these machines and piping a password is blocked by policy; the privileged step is handed over as **one
  command**, with everything it depends on staged and verified from this side first.
- **Do not accept an operator's pasted evidence block as the record.** Both enrolments were re-read off
  the machines; the two agreed, and that agreement is the evidence.
- **Do not report the munki launchd job count without naming the context.** It is **6 installed, 3 visible
  from an ordinary-user shell**, because the count depends on the domain you query from.
- **Do not treat an empty `ClientIdentifier` as a defect.** It is Munki's own default
  (`munkilib/prefs.py:61`); a **non-empty** one is the defect, and it is live on `Cyrils-Mac-mini`
  (`t6-test-client`).
- **Do not put a pre-image of a repo file inside the repo tree** — `~/.munki-fleet/pre-images/` is the
  place, and this repo has no ignore rule for `*.bak*`.
- **Do not rewrite `docs/role-matrix.csv` with LF** (it is CRLF, Excel-edited), and **do not rewrite
  tickets with a script slice** — both turn a small edit into a large or silent one.

## Already decided, so nobody re-opens it

- Metadata is Git-owned and published to the NAS (ADR 0001); the SMB mount is a manual fallback only.
- The forced core stays suspended as published 2026-09-14; drift was 0 at that publish and this session
  changed no metadata, so it is still 0 *(asserted from the previous handoff — this session did not
  re-run the drift check)*.
- The network restriction on the repository is accepted as the topology (decision 13E); the pfSense
  firewall stays unread with five tripwires and nothing monitoring them.
- Retired Notion status options stayed retired; that is the data kernel's business, not this repo's.
- **No enrollment is done with an MDM** (ADR 0005).

## Skills the next session should load

`t6-implementation-workflow`, `munki`, `munki-nas-workflows`, `t6-mac-mini`,
`mac-fleet-state-observation`, `productivity/planning-with-files` if the work spans sessions,
`tutorial-html` for any operator procedure, `update-projects-db`, `obsidian`.
