# Client onboarding — bringing a Mac into Munki

**Status:** procedure of record for ticket 11 of `munki-fleet-rollout`. Executable half:
`tools/onboard-munki-client.sh`. This document is the checklist that goes with it: what to confirm
before each step, and what "correct" looks like after it.

**Tooling requirements, stated so nothing fails on a tool version.** At the machine: macOS's own
`/bin/bash` (3.2.57 is what the fleet runs; nothing here needs bash 4) and macOS built-ins only —
`pkgutil`, `installer`, `defaults`, `scutil`, `plutil`, `curl`, `launchctl`, `sw_vers`, `uname`,
`system_profiler`. **No Python, no Homebrew, no Munki admin tools** are required on the client. The
*collector* side is a different rule: it runs `/usr/bin/python3` (CommandLineTools) and never
invokes Python on the machine being onboarded.

**No MDM** (ADR 0005). This is driven over SSH plus one privileged step at the machine.

---

## What onboarding is, and what it is not

It is three things: the **Munki tools installed**, the **client endpoint pointed at the T6
repository**, and the machine **resolving its own manifest by its short hostname**. It is not "Munki
has been seen on the machine". A machine that installs the tools and then resolves `site_default` has
**failed** onboarding (see step 6).

Nothing here sets a `ClientIdentifier`. That is deliberate: Munki's client identifier defaults to the
machine's short hostname, which is exactly the name the repository's per-machine manifests carry. A
`ClientIdentifier` that disagrees with the hostname is how a machine ends up reading another
machine's manifest — the failure mode already found on Cyril's Mac mini (`t6-test-client`).

## Before you start

| check | correct looks like |
|---|---|
| the machine answers as the account that exists **on that machine** | `whoami` at the machine names an account; do not assume `t6`. One machine in this fleet runs as `t6macminim4pro01`, and a command naming `~t6` there writes the key into a home no account owns — silently, because the shell reports `no such user or named directory` and the rest of the line never runs |
| SSH key auth to that account works from the collector | `ssh -n -o BatchMode=yes <name> 'printf ok'` prints `ok` |
| the repository serves a manifest named after the machine's short hostname | `curl -sf http://192.168.88.188/MunkiRepo/manifests/<ShortHostName>` returns the file. The script refuses to proceed without this, because installing without it guarantees `site_default` |
| the installer is staged on the machine | `~/munki-bootstrap/munkitools-7.3.0.5808.pkg`, sha256 `4ed826bd32811ef54524a10300f66c9af4c9fdd8c243ada146d468485e1bffcc` |

## The steps

Run all of it as root, at the machine, as one command:

```
sudo bash ~/munki-bootstrap/onboard-munki-client.sh --pkg ~/munki-bootstrap/munkitools-7.3.0.5808.pkg
```

| # | step | correct looks like |
|---|---|---|
| 1a | the installer is the signed Munki build | `pkgutil --check-signature` reports **signed by Mac Admins Open Source** (`T4SK8ZXCXG`) and **notarized by Apple**. The script refuses an installer that is not, so a substituted or corrupt package cannot be installed by this path |
| 1b | the machine's own manifest exists in the repository | `LocalHostName` is set and `manifests/<LocalHostName>` returns 200. Refusal here means "publish the manifest first", never "carry on" |
| 1c | the repo serves the resolution machinery | `manifests/<Short>` , `manifests/all` , `manifests/site_default` all return 200 |
| 2 | the before state is recorded | product version, build, arch, `LocalHostName`, whether the tools were already present, whether client prefs existed, launchd job count |
| 3 | the tools install | `installer` exits 0 and `pkgutil --pkg-info com.googlecode.munki.core` reports the version |
| 4 | the endpoint is set, and no `ClientIdentifier` exists | `SoftwareRepoURL = http://192.168.88.188/MunkiRepo`; the script **removes** a `ClientIdentifier` if it finds one and says so |
| 5 | one check-only run | `managedsoftwareupdate --checkonly` completes and writes `/Library/Managed Installs/ManagedInstallReport.plist` |
| 6 | the resolved manifest is the machine's own | the report's `ManifestName` equals `LocalHostName`. **Anything else is FAILURE**, and `site_default` is the loudest case: it means the machine has no manifest of its own |

The script prints an `ONBOARDING EVIDENCE` block at the end. That block is the ticket's evidence:
resolved manifest, check-only result, tools version, and the machine's identity — recorded against the
machine's name in `docs/role-matrix.csv`.

## Undoing it

Reversible, and the plan is readable before it is carried out:

```
sudo bash ~/munki-bootstrap/onboard-munki-client.sh --undo           # prints the plan, changes nothing, exits 2
sudo bash ~/munki-bootstrap/onboard-munki-client.sh --undo --yes     # carries it out
```

It unloads the six launchd jobs, removes `/usr/local/munki`, `/Applications/Managed Software
Center.app`, `/Library/Managed Installs` and `/Library/Preferences/ManagedInstalls.plist`, and forgets
the package receipts. It **does not** remove anything Munki ever installed — Munki is not an
uninstaller — and it never writes to the repository.

On the collector side, giving up access to a machine is separate and documented in
`data/ssh-access.json`'s note (delete the key line at the machine, the stanza, the `known_hosts`
entry, and the map record).

## Machines this procedure has been exercised on

| machine | before state | after state |
|---|---|---|
| `202-Mac-Pro-3` (`192.168.88.174`, x86_64, macOS 15.6.1) | unmanaged: no `/usr/local/munki`, no receipts, no `/Library/Managed Installs`, no client prefs, 0 launchd munki jobs (measured 2026-09-14) | *pending the privileged run* |
| `202B-Mac-Studio` (`192.168.88.177`, arm64, macOS 26.5) | same four absences (measured 2026-09-14) | *pending the privileged run* |

**Note for `202-Mac-Pro-3`:** it had **4.0 GiB free** when staged. Enrolment is not blocked by that,
but a managed client downloads installers into `/Library/Managed Installs` before installing them, so
free space is now a monitored quantity on that machine rather than a curiosity.
