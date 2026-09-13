# 11: One documented onboarding procedure, no MDM

**What to build:** A repeatable, scripted way to bring a new Mac into the fleet: Munki tools installed, the client endpoint set, the machine assigned a manifest, resolution verified, and the machine recorded in the inventory.

**Blocked by:** 04, 07

**Status:** ready-for-agent

**Notes:** No MDM (ADR 0005). The procedure is expected to be driven over SSH and the facility's existing remote-management tooling.

## Acceptance criteria

- [ ] The procedure exists as executable steps plus a checklist, and states what "correct" looks like after each step so the operator can confirm before continuing.
- [ ] It deliberately does not set a ClientIdentifier; the machine resolves by its own short hostname.
- [ ] It ends with recorded evidence: the resolved manifest name, a clean check-only result, and the machine's Munki tools version, recorded against the machine's name in the inventory.
- [ ] A machine that resolves `site_default` at the end of onboarding is treated as a failure of the procedure, not a warning.
- [ ] The procedure states the admin workstation's interpreter and tooling requirements explicitly, so it does not fail on a step that depends on a specific tool version.
- [ ] Performing the procedure on at least one machine that is not currently enrolled is the ticket's acceptance evidence, with the before state (unmanaged) and after state (resolving its machine manifest) recorded.
- [ ] The procedure documents how to undo what it did, so onboarding is reversible.
