# 0005: No MDM — onboarding stays scripted and documented

- **Status:** Accepted (2026-09-13). Cyril's decision: T6 does not adopt an MDM.

## Context

Munki distributes software but not its own bootstrap, and it does not deliver configuration
profiles. T6 has no MDM, so installing Munki tools on a Mac, setting the repository URL, and any
future profile (trust anchors, FileVault options, permissions) are all manual today. This is the
chicken-and-egg step that gates every new machine.

## Decision

- **No MDM is adopted.** Onboarding a Mac is a documented, scripted procedure: install Munki
  tools, set the client endpoint, verify manifest resolution with a check-only run, record the
  machine in the inventory and role matrix.
- The procedure is executable over SSH and remote-management tooling the facility already uses,
  and it is the same procedure every time — no per-machine improvisation.
- The procedure ends with evidence: the resolved manifest name and a clean check-only result
  recorded against the machine's name.
- Any future need that genuinely requires profiles (for example TLS trust anchors for the
  repository) is a decision to revisit here first, not a reason to silently add an MDM.

## Consequences

- Every new Mac costs hands-on time. That cost is accepted and budgeted.
- There is no automatic remediation channel: a Mac that drifts can only be corrected when it is
  next reachable.
- Because there is no MDM, the client endpoint must remain simple — plain HTTP on the LAN, no
  certificate trust to bootstrap. This constrains the security posture (ADR 0007).
- Configuration-profile-based enforcement is permanently unavailable; policy is expressed through
  Munki manifests alone.

## Rollback

Adopting an MDM later supersedes this ADR; the onboarding procedure and inventory remain valid
inputs to that migration.
