# 11: One documented onboarding procedure, no MDM

**What to build:** A repeatable, scripted way to bring a new Mac into the fleet: Munki tools installed, the client endpoint set, the machine assigned a manifest, resolution verified, and the machine recorded in the inventory.

**Blocked by:** 04, 07

**Status:** ready-for-human — the procedure is **built and exercised as far as it can be without privileges**, which is one step short of its own acceptance evidence. What remains is a single privileged command per machine, run at the machine (this fleet has no passwordless sudo and piping a password to `sudo -S` is blocked by policy, so the collector cannot do it from here).

**Claimed by:** session 20260914_205203_8fee48, 2026-09-15T00:05+08:00 — on Cyril's explicit direction ("enroll the two machines", 2026-09-14 23:59), which is also why it was started while 07 is still open (below).

**Notes:** No MDM (ADR 0005). The procedure is expected to be driven over SSH and the facility's existing remote-management tooling.

**Blocker deviation, recorded rather than glossed.** This ticket is `blocked by: 04, 07`. **04 is done.** **07 is `ready-for-human`** — its mechanism is implemented and the initial promotion was executed 2026-09-14 — and its open half is the production/promotion path, which onboarding does not consume. The substance 07 does gate is "the repository can serve a client", and that was measured live rather than assumed: `curl` from the machines returns **200** for `manifests/202-Mac-Pro-3`, `manifests/202B-Mac-Studio`, `manifests/all` and `manifests/site_default`. Cyril directed the enrolment, so the work proceeded with that measurement standing in for the blocker's substance, and the blocker's own half left where it was.

## What was built

| artifact | what it is |
|---|---|
| `tools/onboard-munki-client.sh` | the executable procedure: preflight (root, installer provenance, the machine's own manifest must exist), before-state capture, install, configure, one check-only, and a verdict that **fails** on any manifest that is not the machine's own |
| `docs/procedures/client-onboarding.md` | the checklist of record: the per-step "correct looks like" table, the tooling requirements, the undo, and the machines this has been exercised on |

The installer is staged on both machines at `~/munki-bootstrap/munkitools-7.3.0.5808.pkg`, sha256 `4ed826bd32811ef54524a10300f66c9af4c9fdd8c243ada146d468485e1bffcc` — **the same build the pilot runs** (`com.googlecode.munki.core 7.3.0.5808`), **signed by Mac Admins Open Source and notarized by Apple**, and the hash was read back off each machine after the copy rather than assumed from the transfer.

## Acceptance criteria

- [x] The procedure exists as executable steps plus a checklist, and states what "correct" looks like after each step so the operator can confirm before continuing.
  - `tools/onboard-munki-client.sh` (executable) + `docs/procedures/client-onboarding.md` (the per-step "correct looks like" table). Six numbered steps, each printing its own `ok:` line and its own failure text. Verified by driving it rather than reading it: `/bin/bash -n` clean under the fleet's own `bash 3.2.57`, the **undo plan prints and refuses without `--yes` (exit 2)**, and the **install path refuses without root before touching anything (exit 1)** — both guards watched firing, not asserted.
- [x] It deliberately does not set a ClientIdentifier; the machine resolves by its own short hostname.
  - The script writes only `SoftwareRepoURL`, and it **deletes a `ClientIdentifier` if it finds one** (announcing it), because that value overriding the hostname is exactly how a machine ends up reading another machine's manifest — the live defect already found on Cyril's Mac mini (`t6-test-client`). Its verdict then compares the report's `ManifestName` against `scutil --get LocalHostName`.
- [ ] It ends with recorded evidence: the resolved manifest name, a clean check-only result, and the machine's Munki tools version, recorded against the machine's name in the inventory.
  - **Pending the privileged run.** The script's closing `ONBOARDING EVIDENCE` block carries exactly those three facts plus the machine's identity, and the place they get recorded is named (`docs/role-matrix.csv`, against the machine's short hostname). The block does not exist yet because the step it comes from has not run — the before state is measured, the after state is not, and the two are different claims.
- [x] A machine that resolves `site_default` at the end of onboarding is treated as a failure of the procedure, not a warning.
  - Two places, so it cannot be reached by accident: the **preflight refuses to install at all** if `manifests/<short hostname>` is not served (installing without it guarantees `site_default`), and the **verdict fails** with a distinct message if the resolved manifest is `site_default` or anything other than the machine's own. Both exit non-zero.
- [x] The procedure states the admin workstation's interpreter and tooling requirements explicitly, so it does not fail on a step that depends on a specific tool version.
  - Stated in the script header and in `docs/procedures/client-onboarding.md`: the machine needs macOS's own `/bin/bash` and macOS built-ins only (`pkgutil`, `installer`, `defaults`, `scutil`, `plutil`, `curl`, `launchctl`) — **no Python, no Homebrew, no Munki admin tools** — while the *collector* runs `/usr/bin/python3` (CommandLineTools) per the repository's rule and never invokes Python on the machine being onboarded. The reason this criterion exists in this fleet is on the record: `python3` resolves differently between a session shell and a script here, and the wrong one has no pytest.
- [ ] Performing the procedure on at least one machine that is not currently enrolled is the ticket's acceptance evidence, with the before state (unmanaged) and after state (resolving its machine manifest) recorded.
  - **Half met, and the half that is met is measured.** The **before state is recorded for two machines**, from the machines themselves: `202-Mac-Pro-3` (x86_64, macOS 15.6.1) and `202B-Mac-Studio` (arm64, macOS 26.5) each have no `/usr/local/munki`, no Munki receipt from `pkgutil`, no `/Library/Managed Installs`, no `/Library/Preferences/ManagedInstalls.plist` and zero munki launchd jobs. The installer and the script are staged on both, with the sha256 read back off each machine. **The after state requires the one privileged step**, which this fleet's rules put at the machine rather than in the collector (no passwordless sudo; piping to `sudo -S` is blocked by policy; `munki-nas-workflows` says stop after one attempt rather than loop on privilege escalation).
- [x] The procedure documents how to undo what it did, so onboarding is reversible.
  - `--undo` prints the complete plan — the six launchd jobs, `/usr/local/munki`, Managed Software Center, `/Library/Managed Installs`, the client prefs, and the six receipts — states the two things it deliberately does **not** touch (everything Munki ever installed, and the repository), and changes **nothing** until `--yes` is passed. The gate was watched refusing (exit 2) as a non-root user, which is also why the plan is readable without root. Onboarding is re-runnable, and the install path states when it is one (tools already present).
