# 02: Authorize and observe the TOC pilot

**What to build:** `202-TOC-M4-Max` gains one approved SSH access path from the collector host, and the existing read-only probe records the pilot's actual Munki state. The prior public-key refusal is retained as before-state evidence so the change is demonstrated rather than assumed.

**Blocked by:** 01: Resolve observation targets through an explicit SSH transport contract

**Status:** done (2026-09-14) — all eight criteria met. The eighth was the last: the rollback was exercised at the pilot (remove the key, watch the refusal return, restore) and the end state was verified from the collector host afterwards, including that the drill wrote nothing under `/Library/Managed Installs`. The one claim that rests on the operator's report rather than on this host's observation — the intermediate refusal — is named in the criterion rather than glossed.

**Approval gate:** Enabling Remote Login, changing SSH authentication, or adding an authorized public key changes authentication on a facility Mac and requires Cyril's confirmation before execution. **Discharged 2026-09-14**: Cyril approved appending one per-machine stanza to the collector host's `~/.ssh/config` and authorizing the collector's public key on the pilot's `t6` account, after being shown the exact scope, the key fingerprint and the rollback. The runbook he worked from is `~/T6-Ops-Docs/runbooks/fleet-ssh-pilot-access-ticket02-2026-09-14.html`.

## What was done

| where | change |
|---|---|
| the pilot, `t6` account | the collector's public key (`id_ed25519_t6.pub`, `SHA256:yQdIFGNdehuePZHauN7tB/S3dZWiluxz78rGQUEzkqU`) added to `~/.ssh/authorized_keys` by Cyril, at the machine as `t6` — the pilot's own listing shows `drwx------ t6 staff` and `-rw------- t6 staff`, and **exactly one** key |
| the collector host, `~/.ssh/config` | one stanza appended (no existing block touched): `Host 202-TOC-M4-Max` / `HostName 192.168.88.182` / `User t6` / `IdentityFile ~/.ssh/id_ed25519_t6` / `IdentitiesOnly yes`. Pre-image: `~/.ssh/config.bak-20260914T220422-before-fleet-ssh-stanza` |
| `data/ssh-access.json` | a record for `202-TOC-M4-Max`, serial `RW3HL9FL4M`, destination `202-TOC-M4-Max` |

**Nothing was enabled.** The pilot was already offering SSH: the before-state refusal is `t6@192.168.88.182: Permission denied (publickey,password,keyboard-interactive)`, which is sshd answering, so Remote Login did not need turning on and no authentication method was changed.

### The stanza exists because the fleet key is not a default identity

Plain `ssh -o BatchMode=yes t6@192.168.88.182` still fails after the key is authorized, because ssh offers its default identities (`~/.ssh/id_ed25519`) and never tries `id_ed25519_t6`. Measured, not assumed: the failure was reproduced in both forms before the stanza was written, and the collector's exact argv shape was dry-run against a throwaway config file before `~/.ssh/config` was touched. Two consequences worth carrying forward:

- **A shared glob block does not work.** `Host 201-* 202-* 202A-* …` was tried first and failed: ssh lowercases the name it is given, and a shared block carries no `HostName`, so there is nothing to resolve. One stanza per machine, keyed on the machine's own name.
- **The case must be exact.** A stanza whose `Host` pattern is lowercase does not match, so a lowercase copy of the block silently fails to resolve (verified both ways). The comment in the config says so.

### A dependency this ticket creates, recorded where it can bite

An access record declares **which** machine may be reached; the machine that runs the collector holds **how** the credential is presented, in its own `~/.ssh/config`. A destination no stanza covers fails as `unreachable` and is reported rather than guessed — but it fails only at probe time, so **ticket 05's cutover must recreate these stanzas on the admin workstation** or its destinations will silently not resolve. Recorded in `CONTEXT.md` (glossary) and in the map's own note. A pre-flight check that a declared destination resolves on this host would be a useful guard; it is not built here, and this ticket is not the place (it would be new behaviour on the same reviewed path).

## Acceptance criteria

- [x] Before any system change, the current state is recorded from the pilot: network reachability, SSH service response, attempted destination and username, and the transport's exact authentication result.
  - `ssh -n -o BatchMode=yes t6@192.168.88.182 'echo key-auth-ok'` → `t6@192.168.88.182: Permission denied (publickey,password,keyboard-interactive).` and `… ssh -o BatchMode=yes 192.168.88.182 …` → `cyrilbautista@192.168.88.182: …` (the undeclared path, named by the local account) — evidence section 1. The service is up, so the refusal is authentication, not reachability.
- [x] The proposed authentication change names the affected machine, collector host, public-key identity, dependencies, rollback steps, and recovery path; Cyril approves that exact scope before execution.
  - Machine `202-TOC-M4-Max`/`192.168.88.182`; collector host this Mac mini `192.168.88.202`; key `id_ed25519_t6.pub` with its fingerprint; dependency = the collector host's ssh config, which is *why* the change is two-sided; rollback = delete the one `authorized_keys` line and the one stanza; recovery = restore `~/.ssh/config` from the pre-image. Approved in session after the plain-form failure was demonstrated.
- [x] Only the approved public key and least-privileged account are authorized; no password, private key, or secret is committed, logged, or copied into the observation store.
  - The pilot's own answer, quoted in evidence section 3: `ssh-keygen -lf ~/.ssh/authorized_keys` lists one entry, the approved fingerprint. Account `t6`, ordinary user, no sudo involved in the probe. The map records a destination and a serial; the observation record's `target` carries `{'address', 'host', 'name', 'serial', 'ssh_destination'}` and nothing credential-shaped.
- [x] The resulting access path is non-interactive from the collector host and permits the read-only probe without root or a client-side write.
  - `BatchMode=yes` makes a prompt impossible; the probe ran with no root and wrote nothing on the pilot (it reads `ManagedInstallReport.plist` and the log tail). Run `2026-09-14T22:04:43+08:00/966dabd2`, `targeted 1, reached 1 (observed 1, partial 0), unobserved 0`.
- [x] A live observation records serial `RW3HL9FL4M`, Munki tools version, resolved manifest, pending count, last-check result, architecture rejections, warnings, source timestamps, and observation timestamp.
  - Serial `RW3HL9FL4M`; Munki `7.3.0.5808`; **resolved manifest `202-TOC-M4-Max` — its own machine manifest, not `site_default`**; pending 0; `last_check.result` `warnings` with `run_kind: auto` and the run's own start/end in both the report's UTC (`13:45:07`/`13:45:11`) and the log's local offset (`21:45:07.937+08:00`/`21:45:11.117+08:00`) forms, recorded as given; `architecture_rejections: []`; warnings = one item filtered (`IBMAsperaConnect … No pkginfo found in catalogs: ["testing"]`, the x86_64-only item on an arm64 machine); `observed_at 2026-09-14T22:04:43+08:00`; source age 1172 s. Full record verbatim in evidence section 4.
- [x] A serial mismatch, fallback manifest, partial payload, or authentication failure leaves the ticket incomplete and is reported with its source evidence.
  - None occurred: the record's `problems` is `[]`, the serial matches the inventory row (`RW3HL9FL4M`), and the resolved manifest is the machine's own. Had any of them occurred the observation would have been `partial`/`unobserved` or flagged, and the ticket would say so — the mechanism is ticket 01's and is tested there.
- [x] Rollback is exercised or independently verified: removing the approved authorization returns the access path to its prior state without altering Munki client data.
  - **MET, by exercise plus after-the-fact verification.** Cyril ran the drill at the pilot on 2026-09-14 ~23:31 (runbook steps 6–8): `authorized_keys` copied aside, the approved line removed, the refusal confirmed, the copy restored. Verified from this host afterwards — evidence section 7:
    - The end state is **exactly** the pre-drill state, not merely working again: one key line, the approved fingerprint `SHA256:yQdIFGN…`, 105 bytes (104 characters plus its newline), owner `t6`, mode `0600`, directory `0700`, and **no `.drill` copy left behind**.
    - The drill's own writes are visible in the file's mtime, `21:52 → 23:31:01`, so the removal and the restore actually happened rather than being skipped.
    - Both working forms still work: `-i ~/.ssh/id_ed25519_t6` explicitly, and by name `202-TOC-M4-Max` through the stanza.
    - **No Munki client data was altered**, and that is checkable rather than asserted: the pilot's own report was last written at `22:45:14`, **46 minutes before** the drill at `23:31`, so the drill wrote nothing under `/Library/Managed Installs`. The reading afterwards is the same in substance (`manifest=202-TOC-M4-Max pending=0`, Munki `7.3.0.5808`, `problems=[]`, run `2026-09-14T23:32:38+08:00/0977f76c`).
  - **On the operator's report, not independently observed:** the intermediate refusal. Reading the pilot's unified log without privilege returned no sshd entries, so the removal taking effect was not witnessed from this host. What is verified is that the file changed during the drill window and came back as exactly one approved key — its end state; the middle state rests on Cyril's account plus that mtime. Recorded because "the drill was run" and "the drill was observed" are different claims.
  - The collector-side half of the rollback (delete the stanza, restore the pre-image `~/.ssh/config.bak-20260914T220422-before-fleet-ssh-stanza`) is **not** exercised: it is a one-line deletion with a pre-image in hand, and exercising it would break the pilot's access that tickets 03–04 depend on. Named as the residual rather than claimed.
- [x] The ticket records before/after evidence and reads the exact access target and observation back before claiming completion.
  - Before and after, with the commands and what each returned: `docs/evidence/02-pilot-access-2026-09-14.txt`. The read-back is section 4: `49 records, 7 run(s)`, newest reading per machine, with `RW3HL9FL4M current age=0s … manifest=202-TOC-M4-Max`. The stanza's own effect was read back twice — `ssh 202-TOC-M4-Max whoami` → `t6`, and the paths that already worked (`t6-mac-mini`, `t6-nas`) still answer after the append.

## What this changes for the rest of the set

- **Fleet coverage after this ticket: 2 of 16 ssh targets declared** (`Sixto-5`, `202-TOC-M4-Max`), 17 targeted, 3 observed, 14 unobserved with their transport reasons. The fleet run is evidence section 5.
- **Ticket 06 gains its first production-machine data point.** The pilot resolves its own manifest, so criterion 4's "every inventoried Mac reports a resolved manifest name that is its own machine manifest" has a real machine behind it (2 with `Sixto-5`). Its four `name-difference` cases are elsewhere and untouched by this.
- **Ticket 03's wave 1** is `202-Mac-Pro-3`, `202-TOC-M4-Max` (done here), `202A-Mac-Mini-M4`, and `202B-Mac-Studio`. Each new machine needs its own stanza *and* its own approval. *Corrected 2026-09-14 by ticket 03's measurement:* `202B-Mac-Studio` **does** have an address — `192.168.88.177`, confirmed by the machine's own mDNS binding `202B-Mac-Studio.local` rather than by assertion — so it can be reached; what it still lacks is its **serial**, which is what an inventory row and a manifest need. The earlier claim here that it had no address was written from the ARD export's silence and is superseded.
- **Ticket 04's remaining fleet** includes `303B iMac`, whose Munki name contains a space: it needs an alias form (its UNIX hostname `303B-iMac`) in both the stanza and the map, which is a naming decision rather than a mechanical one.

## Verification

Suite unchanged by this ticket (no code), run bare at `b3f62d5`:

```
$ /usr/bin/python3 -m pytest
288 passed
```

After the rollback drill, the same host, 2026-09-14 23:32 — the criterion-7 read-back:

```
$ ssh -n -o BatchMode=yes -o ConnectTimeout=6 -o IdentitiesOnly=yes -i ~/.ssh/id_ed25519_t6 t6@192.168.88.182 'printf key-auth-ok'
key-auth-ok                                                        exit=0
$ ssh -n -o BatchMode=yes -o ConnectTimeout=6 202-TOC-M4-Max 'printf key-auth-ok'
key-auth-ok                                                        exit=0
$ ssh … t6@192.168.88.182 'stat -f "%Sm %N" ~/.ssh ~/.ssh/authorized_keys'
2026-09-14T23:31:14 /Users/t6/.ssh
2026-09-14T23:31:01 /Users/t6/.ssh/authorized_keys
$ ssh … t6@192.168.88.182 'ls -la ~/.ssh; ssh-keygen -lf ~/.ssh/authorized_keys'
drwx------   3 t6  staff    96 Sep 14 23:31 .
-rw-------   1 t6  staff   105 Sep 14 23:31 authorized_keys
256 SHA256:yQdIFGNdehuePZHauN7tB/S3dZWiluxz78rGQUEzkqU t6-cyril@192.168.88.188 (ED25519)
(no .drill copy: it was consumed by the restore)
$ python3 -m munki_fleet.cli probe --store ~/.munki-fleet/observations.jsonl \
    --access-map data/ssh-access.json --machine 202-TOC-M4-Max:RW3HL9FL4M
run 2026-09-14T23:32:38+08:00/0977f76c
  targeted 1, reached 1 (observed 1, partial 0), unobserved 0
  complete: True
    202-TOC-M4-Max               RW3HL9FL4M     manifest=202-TOC-M4-Max pending=0 rejections=0
exit=0
```

Live, on the collector host (`192.168.88.202`), 2026-09-14, before the drill:

```
$ python3 -m munki_fleet.cli probe --store ~/.munki-fleet/observations.jsonl \
    --access-map data/ssh-access.json --machine 202-TOC-M4-Max:RW3HL9FL4M
access: 1 of 1 ssh target(s) have a declared destination (data/ssh-access.json)
run 2026-09-14T22:04:43+08:00/966dabd2
  targeted 1, reached 1 (observed 1, partial 0), unobserved 0
  complete: True
    202-TOC-M4-Max               RW3HL9FL4M     manifest=202-TOC-M4-Max pending=0 rejections=0
  appended to /Users/cyrilbautista/.munki-fleet/observations.jsonl
exit=0
```

Full capture, including the before state, the pilot's own account of its `authorized_keys`, the
regression checks and the whole-fleet run: `docs/evidence/02-pilot-access-2026-09-14.txt`.
