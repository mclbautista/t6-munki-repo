# 11: One documented onboarding procedure, no MDM

**What to build:** A repeatable, scripted way to bring a new Mac into the fleet: Munki tools installed, the client endpoint set, the machine assigned a manifest, resolution verified, and the machine recorded in the inventory.

**Blocked by:** 04, 07

**Status:** done (2026-09-15) — all seven criteria met. The procedure was exercised at the privilege boundary on two machines that had **no Munki client at all**, and both now resolve their own machine manifest; the evidence was read back off the machines rather than taken from the operators' pasted blocks. It also found a third machine in the same state (`202A-Mac-Mini-M4`), which is recorded rather than folded in. What remains is a single privileged command per machine, run at the machine (this fleet has no passwordless sudo and piping a password to `sudo -S` is blocked by policy, so the collector cannot do it from here).

**Claimed by:** session 20260914_205203_8fee48, 2026-09-15T00:05+08:00 — on Cyril's explicit direction ("enroll the two machines", 2026-09-14 23:59), which is also why it was started while 07 is still open (below).

**Notes:** No MDM (ADR 0005). The procedure is expected to be driven over SSH and the facility's existing remote-management tooling.

**Blocker deviation, recorded rather than glossed.** This ticket is `blocked by: 04, 07`. **04 is done.** **07 is `ready-for-human`** — its mechanism is implemented and the initial promotion was executed 2026-09-14 — and its open half is the production/promotion path, which onboarding does not consume. The substance 07 does gate is "the repository can serve a client", and that was measured live rather than assumed: `curl` from the machines returns **200** for `manifests/202-Mac-Pro-3`, `manifests/202B-Mac-Studio`, `manifests/all` and `manifests/site_default`. Cyril directed the enrolment, so the work proceeded with that measurement standing in for the blocker's substance, and the blocker's own half left where it was.

## What was built

| artifact | what it is |
|---|---|
| `tools/onboard-munki-client.sh` | the executable procedure: preflight (root, installer provenance, the machine's own manifest must exist), before-state capture, install, configure, one check-only, and a verdict that **fails** on any manifest that is not the machine's own |
| `docs/procedures/client-onboarding.md` | the checklist of record: the per-step "correct looks like" table, the tooling requirements, the undo, and the machines this has been exercised on |

The installer is staged on both machines at `~/munki-bootstrap/munkitools-7.3.0.5808.pkg`, sha256 `4ed826bd32811ef54524a10300f66c9af4c9fdd8c243ada146d468485e1bffcc` — **the same build the pilot runs** (`com.googlecode.munki.core 7.3.0.5808`), **signed by Mac Admins Open Source and notarized by Apple**, and the hash was read back off each machine after the copy rather than assumed from the transfer.

## Verification

Read back off the machines, 2026-09-15 00:24–00:26 +08:00 (full capture:
`docs/evidence/11-onboarding-verified-2026-09-15.txt`):

```
$ ssh -n -o BatchMode=yes -o IdentitiesOnly=yes -i ~/.ssh/id_ed25519_t6 t6@192.168.88.174 '<read-back>'
munki_core=7.3.0.5808   all_receipts=6   launchd_jobs=3   repourl=http://192.168.88.188/MunkiRepo
clientid=   manifest=202-Mac-Pro-3   report_mtime=2026-09-15T00:21:23+0800
$ ssh … t6@192.168.88.174 "plutil -p /Library/Preferences/ManagedInstalls.plist"
  "ClientIdentifier" => ""                      # Munki's own default: munkilib/prefs.py:61
  "SoftwareRepoURL" => "http://192.168.88.188/MunkiRepo"
  "LastCheckResult" => 0     "PendingUpdateCount" => 0
$ ssh … t6@192.168.88.174 "ls /Library/LaunchDaemons/com.googlecode.munki.*.plist | wc -l"
6                                               # an ordinary-user `launchctl list` sees 3 of them
the same shape on 202B-Mac-Studio, resolving 202B-Mac-Studio, report 2026-09-15T00:22:42+0800
```

One check whose answer depends on who runs it is recorded in the evidence rather than smoothed
over: the count of munki launchd jobs is **6 installed, 3 visible from an ordinary-user context**.
Both numbers are true and the difference is the domain the shell queries.

- [x] The procedure exists as executable steps plus a checklist, and states what "correct" looks like after each step so the operator can confirm before continuing.
  - `tools/onboard-munki-client.sh` (executable) + `docs/procedures/client-onboarding.md` (the per-step "correct looks like" table). Six numbered steps, each printing its own `ok:` line and its own failure text. Verified by driving it rather than reading it: `/bin/bash -n` clean under the fleet's own `bash 3.2.57`, the **undo plan prints and refuses without `--yes` (exit 2)**, and the **install path refuses without root before touching anything (exit 1)** — both guards watched firing, not asserted.
- [x] It deliberately does not set a ClientIdentifier; the machine resolves by its own short hostname.
  - The script writes only `SoftwareRepoURL`, and it **deletes a `ClientIdentifier` if it finds one** (announcing it), because that value overriding the hostname is exactly how a machine ends up reading another machine's manifest — the live defect already found on Cyril's Mac mini (`t6-test-client`). Its verdict then compares the report's `ManifestName` against `scutil --get LocalHostName`.
- [x] It ends with recorded evidence: the resolved manifest name, a clean check-only result, and the machine's Munki tools version, recorded against the machine's name in the inventory.
  - **MET, and verified rather than accepted.** Both machines' blocks are in `docs/evidence/11-onboarding-verified-2026-09-15.txt`, and every fact in them was read back off the machine over SSH afterwards: `munki core 7.3.0.5808`, 6 receipts, 6 installed launchd plists, `SoftwareRepoURL` set, and the resolved manifest from the machine's own `ManagedInstallReport.plist` — `202-Mac-Pro-3` and `202B-Mac-Studio`, each its own. `LastCheckResult` 0 and `PendingUpdateCount` 0 on both. Recorded against each machine's short hostname in `docs/role-matrix.csv`.
  - **On the tools version specifically:** it is the *same build the pilot runs* (`7.3.0.5808`), which matters because a second version in the fleet is its own kind of drift.
- [x] A machine that resolves `site_default` at the end of onboarding is treated as a failure of the procedure, not a warning.
  - Two places, so it cannot be reached by accident: the **preflight refuses to install at all** if `manifests/<short hostname>` is not served (installing without it guarantees `site_default`), and the **verdict fails** with a distinct message if the resolved manifest is `site_default` or anything other than the machine's own. Both exit non-zero.
- [x] The procedure states the admin workstation's interpreter and tooling requirements explicitly, so it does not fail on a step that depends on a specific tool version.
  - Stated in the script header and in `docs/procedures/client-onboarding.md`: the machine needs macOS's own `/bin/bash` and macOS built-ins only (`pkgutil`, `installer`, `defaults`, `scutil`, `plutil`, `curl`, `launchctl`) — **no Python, no Homebrew, no Munki admin tools** — while the *collector* runs `/usr/bin/python3` (CommandLineTools) per the repository's rule and never invokes Python on the machine being onboarded. The reason this criterion exists in this fleet is on the record: `python3` resolves differently between a session shell and a script here, and the wrong one has no pytest.
- [x] Performing the procedure on at least one machine that is not currently enrolled is the ticket's acceptance evidence, with the before state (unmanaged) and after state (resolving its machine manifest) recorded.
  - **MET on two machines.** Before state, measured from the machines: neither `202-Mac-Pro-3` (x86_64, macOS 15.6.1) nor `202B-Mac-Studio` (arm64, macOS 26.5) had `/usr/local/munki`, a Munki receipt, `/Library/Managed Installs`, client prefs, or a munki launchd job. After state, read back from the machines: tools `7.3.0.5808`, 6 receipts, 6 launchd plists, and **each resolving its own machine manifest** — a machine that had installed the tools but resolved `site_default` would have been recorded here as a failure.
  - **The privileged step stayed where this fleet's rules put it.** No passwordless sudo exists on these machines, piping a password to `sudo -S` is blocked by policy, and `munki-nas-workflows` says stop after one attempt rather than loop on privilege escalation — so the step was handed over as **one command per machine**, with everything it depends on (installer staged and hashed, the procedure's own preflight, the machine's manifest verified present in the repository) done from this side first. Recorded because "the collector cannot run sudo here" is a property of the fleet, not an inconvenience of the session.
  - **A third machine was found in the same state.** `202A-Mac-Mini-M4` also has no Munki client (four absences, measured 2026-09-15), so the wave's real enrolment count is **three machines, not two**. It is not enrolled: that needs the same privileged command, and it is recorded as outstanding rather than implied.
- [x] The procedure documents how to undo what it did, so onboarding is reversible.
  - `--undo` prints the complete plan — the six launchd jobs, `/usr/local/munki`, Managed Software Center, `/Library/Managed Installs`, the client prefs, and the six receipts — states the two things it deliberately does **not** touch (everything Munki ever installed, and the repository), and changes **nothing** until `--yes` is passed. The gate was watched refusing (exit 2) as a non-root user, which is also why the plan is readable without root. Onboarding is re-runnable, and the install path states when it is one (tools already present).
