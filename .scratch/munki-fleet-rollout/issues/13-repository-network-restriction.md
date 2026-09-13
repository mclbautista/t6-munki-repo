# 13: Restrict the client endpoint to the fleet, and record the residual risk

**What to build:** The repository reachable only from T6's own network path: an explicit allowlist at the NAS firewall for the repository port, verified by a refused connection from outside it, with the accepted residual risk written down where an auditor would look.

**Blocked by:** None (can start immediately)

**Approval gate:** Changing the NAS firewall is a system change and requires Cyril's approval before execution.

**Status:** ready-for-agent

## Acceptance criteria

- [ ] An allowlist restricting the repository's port to T6's own addresses is configured at the NAS.
- [ ] The restriction is verified by a refused connection from an address outside the allowlist — the actual attempt, its result, and its source recorded. If no such source can be used, the ticket records that the negative case was not verified by us and states exactly what remains unverified, rather than claiming it.
- [ ] A client inside the allowlist still fetches its artifacts over HTTP afterwards, recorded by machine name.
- [ ] The evidence that this restriction is what stands between the repository and the wider network is stated explicitly, including that the repository must never be internet-reachable.
- [ ] The residual risk of an unauthenticated metadata path is recorded per ADR 0007, with the revisit trigger (a profile delivery channel, or any change in reachability).
