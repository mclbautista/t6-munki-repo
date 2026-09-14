# 13: Restrict the client endpoint to the fleet, and record the residual risk

**What to build:** The repository reachable only from T6's own network path: an explicit allowlist at the NAS firewall for the repository port, verified by a refused connection from outside it, with the accepted residual risk written down where an auditor would look.

**Blocked by:** None (can start immediately)

**Approval gate:** Changing the NAS firewall is a system change and requires Cyril's approval before execution.

**Status:** ready-for-agent

**Claimed by:** hermes-desktop (Cyril's Mac mini, /Users/cyrilbautista/Projects/t6-munki-repo) 2026-09-14T08:20+08:00

## Acceptance criteria

- [ ] An allowlist restricting the repository's port to T6's own addresses is configured at the NAS.
- [ ] The restriction is verified by a refused connection from an address outside the allowlist — the actual attempt, its result, and its source recorded. If no such source can be used, the ticket records that the negative case was not verified by us and states exactly what remains unverified, rather than claiming it.
- [ ] A client inside the allowlist still fetches its artifacts over HTTP afterwards, recorded by machine name.
- [ ] The evidence that this restriction is what stands between the repository and the wider network is stated explicitly, including that the repository must never be internet-reachable.
- [ ] The residual risk of an unauthenticated metadata path is recorded per ADR 0007, with the revisit trigger (a profile delivery channel, or any change in reachability).

## Decisions (2026-09-13)

The acceptance criteria above are left exactly as written. These are the decisions that determine *how* they are met, so that a divergence is visible rather than silently absorbed into the criterion text.

- **13A — network segregation, not a firewall.** No firewall app is to be installed on the NAS. Criterion 1's "allowlist restricting the repository's port … configured at the NAS" is therefore met by the **network path**: the restriction comes from where clients can reach the NAS, not from a rule on it. Consequences to carry into the work: there is no rule to point at, no default-deny posture to preserve, and nothing to roll back on the NAS; whatever segments the network is where the change lands, and that has its own blast radius. It also means the other things sharing port 80 (the whole `Web` share) are **not** restricted by this work — a deliberate narrowing to state explicitly.
- **13B — one subnet: `192.168.88.0/24`.** The two Wi-Fi ranges in the inventory (`192.168.254.x`, `192.168.0.x`) are treated as a network-path defect to fix, not as holes to allowlist. A client that runs its check while on Wi-Fi must not be silently cut off; it must be moved to the fleet path.
- **13C — the negative case is recorded as not verified by us.** Cyril's decision: there is no source to attempt the refusal from. Criterion 2's own escape hatch applies, and the ticket must state exactly what remains unverified: reachability of the metadata endpoint from an address outside the fleet's path — a routing fact after 13A, not a firewall refusal.
- **13D — `myQNAPcloud` verified read-only from the NAS, 2026-09-13.** Installed and enabled, but no QNAP ID linked, no service published, no DDNS name of our own, and Auto Router Configuration force-disabled: nothing on the NAS side creates an internet path. Full sources: `docs/evidence/13-myqnapcloud-and-reachability-state-2026-09-13.txt`. What remains unverified is gateway-side only (a hand-made port-forward, and whether the ISP address is public or carrier-shared).

