# 02: Authorize and observe the TOC pilot

**What to build:** `202-TOC-M4-Max` gains one approved SSH access path from the collector host, and the existing read-only probe records the pilot's actual Munki state. The prior public-key refusal is retained as before-state evidence so the change is demonstrated rather than assumed.

**Blocked by:** 01: Resolve observation targets through an explicit SSH transport contract

**Status:** ready-for-human

**Approval gate:** Enabling Remote Login, changing SSH authentication, or adding an authorized public key changes authentication on a facility Mac and requires Cyril's confirmation before execution.

- [ ] Before any system change, the current state is recorded from the pilot: network reachability, SSH service response, attempted destination and username, and the transport's exact authentication result.
- [ ] The proposed authentication change names the affected machine, collector host, public-key identity, dependencies, rollback steps, and recovery path; Cyril approves that exact scope before execution.
- [ ] Only the approved public key and least-privileged account are authorized; no password, private key, or secret is committed, logged, or copied into the observation store.
- [ ] The resulting access path is non-interactive from the collector host and permits the read-only probe without root or a client-side write.
- [ ] A live observation records serial `RW3HL9FL4M`, Munki tools version, resolved manifest, pending count, last-check result, architecture rejections, warnings, source timestamps, and observation timestamp.
- [ ] A serial mismatch, fallback manifest, partial payload, or authentication failure leaves the ticket incomplete and is reported with its source evidence.
- [ ] Rollback is exercised or independently verified: removing the approved authorization returns the access path to its prior state without altering Munki client data.
- [ ] The ticket records before/after evidence and reads the exact access target and observation back before claiming completion.
