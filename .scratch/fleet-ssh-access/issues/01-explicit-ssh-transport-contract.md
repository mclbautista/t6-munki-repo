# 01: Resolve observation targets through an explicit SSH transport contract

**What to build:** The collector observes a machine through an explicit, non-secret SSH access record rather than assuming the inventory address is also a complete login path. The complete path is proven on the admin workstation using its existing working access: resolve target, connect, run the read-only Munki probe, append the observation, and read it back.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

**Claimed by:** hermes-desktop (Cyril's Mac mini, /Users/cyrilbautista/Projects/t6-munki-repo) 2026-09-14T21:22+0800

**Boundary:** This ticket installs no keys, enables no services, and changes no client or admin-workstation authentication settings.

- [ ] An observation target can declare its SSH destination separately from its inventory address, machine name, and serial; no credential or private-key material is stored in the repository or observation store.
- [ ] Inventory-driven probing uses the explicit SSH destination when one is present and does not silently fall back to `t6@<primary_ip>` for a target that requires an access record.
- [ ] A missing, malformed, duplicate, or serial-mismatched access record is reported deterministically and cannot produce a compliant-looking observation.
- [ ] Existing targets without an access record retain an explicit unobserved result with the transport reason preserved; they are never omitted from run completeness.
- [ ] Tests cover an SSH alias, a distinct username/destination, an absent mapping, a serial mismatch, and proof that secrets are neither required in nor written to repository data.
- [ ] A live run reaches `Sixto-5` through the already-working `t6-mac-mini` access path, appends an observation to an explicitly named store outside the checkout, and reads back the matching serial, resolved manifest, and observation timestamp.
- [ ] The full test suite passes, and the ticket records the exact live command, system, observation-store location, and returned result.
