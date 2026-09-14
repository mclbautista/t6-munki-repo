# 04: Establish SSH access for the remaining fleet

**What to build:** The approved collector access method is extended to every remaining T6 Mac, and one fleet run reconciles all 17 expected observation targets into observed, partial, or unobserved outcomes with exact transport evidence. Authentication failures are findings, not a completed access rollout.

**Blocked by:** 03: Establish SSH access for rollout wave 1

**Status:** ready-for-human

**Approval gate:** Enabling Remote Login or authorizing a collector key fleet-wide changes authentication on facility Macs and requires Cyril's confirmation of the remaining wave before execution.

- [ ] The remaining wave is enumerated from the current authoritative inventory and role matrix immediately before execution; additions, removals, stale addresses, unknown serials, and name disagreements are reported rather than silently normalized.
- [ ] Every expected machine has one explicit SSH access disposition: already authorized, approved change required, intentionally unavailable, off-site/unreachable, missing identity, or another source-grounded reason.
- [ ] Cyril approves the exact remaining machine set and authentication changes before execution.
- [ ] The same least-privileged, no-root probe access proven on the pilot and wave 1 is used; no password, private key, or secret enters Git, the access inventory, logs, tickets, or the observation store.
- [ ] A single recorded fleet run targets all 17 expected machines and reconciles the run totals programmatically against the inventory and role matrix.
- [ ] Every reachable machine is observed with matching serial and records its Munki version, resolved manifest, pending state, last-check result, warnings, architecture rejections, source timestamps, and observation timestamp.
- [ ] Every partial or unobserved machine retains the exact reason and is named individually; authentication refusal is not accepted as finished SSH access unless Cyril explicitly chooses and records an exception.
- [ ] Manifest-name and identity disagreements discovered by the machines' own reports are recorded as findings for the existing manifest-resolution and inventory tickets, not corrected by guesswork in this ticket.
- [ ] Each changed machine has a recorded rollback path, and the final report distinguishes access established, machine observed, and unresolved exceptions.
