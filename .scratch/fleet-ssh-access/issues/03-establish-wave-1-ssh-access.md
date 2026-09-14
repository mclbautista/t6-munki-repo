# 03: Establish SSH access for rollout wave 1

**What to build:** Every confirmed TOC and war-room machine receives an explicit, approved SSH access disposition and is included in one recorded observation run, supplying the client-state prerequisite for the existing first-wave Munki rollout without changing Munki policy.

**Blocked by:** 02: Authorize and observe the TOC pilot

**Status:** ready-for-human

**Approval gate:** Enabling Remote Login or authorizing a collector key on additional facility Macs changes fleet authentication and requires Cyril's confirmation of the named wave before execution.

- [ ] The wave is fixed before execution as `202-Mac-Pro-3`, `202-TOC-M4-Max`, `202A-Mac-Mini-M4`, and `202B-Mac-Studio`, with each machine's known serial, address, username, and SSH destination listed; unknown identity fields remain explicit gaps.
- [ ] Current network, SSH-service, and authentication state is recorded per machine before any change, preserving whether the result is timeout, connection refused, authentication refusal, or success.
- [ ] Cyril approves the exact machine set and authentication change before keys are authorized or Remote Login is enabled.
- [ ] Each machine receives only the approved least-privileged access needed to run the existing no-root, read-only probe; credentials and private keys remain outside Git and the observation store.
- [ ] One observation run targets all four machines and records each as observed, partial, or unobserved without dropping an unresolved machine from completeness.
- [ ] Every observed machine reports a serial matching the inventory or role-matrix record and carries its resolved manifest, Munki version, pending state, warnings, rejections, and timestamps.
- [ ] `202B-Mac-Studio` is not guessed into compliance: if its serial or address is still unknown, the run and ticket preserve that exact unresolved state and identify the authoritative evidence needed to close it.
- [ ] The access change has a recorded per-machine rollback, and the ticket reads back both the live authorization target and the appended observations before claiming completion.
