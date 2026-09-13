# Triage Labels

This repository uses these canonical local ticket states:

| State | Meaning |
|---|---|
| `needs-triage` | New or insufficiently classified ticket |
| `needs-info` | Blocked on missing evidence, decision, or reproduction |
| `ready-for-agent` | Scope and acceptance criteria are clear for implementation |
| `ready-for-human` | Requires Cyril's product, credential, or operational decision |
| `wontfix` | Explicitly outside the current plan |

Use one state per ticket. Category labels, when needed, are `bug` and `enhancement`.

## Approval gate

Tickets that change system-level configuration (NAS firewall, NAS snapshots or backup jobs,
Munki tool versions on the admin workstation, forced-core policy, promotions to `production`,
or any deletion in the repository) carry an explicit `ready-for-human` step for Cyril's
approval in addition to their state. See ADR 0008.
