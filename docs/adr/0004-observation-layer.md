# 0004: One deterministic observation writer; LLM renders only

- **Status:** Accepted (2026-09-13)

## Context

Verified 2026-09-13: there is no fleet telemetry. No MunkiReport or Sal endpoint, no check-in log
on the repository host. Three machines have been touched by this project
(`202-TOC-M4-Max`, Cyril's Mac mini, and the Mac Mini itself, which silently resolves
`site_default` because it has no machine manifest). For the other 13 Macs nobody can say whether
Munki tools are installed, which manifest would resolve, or what is pending — the only way to
find out is to SSH into each machine.

## Decision

A **deterministic collector** on the admin workstation is the single authoritative writer of
fleet state:

- **Identity** comes from the Apple Remote Desktop machine export (machine name, serial number,
  MAC address, OS version, known network addresses). The export carries **no hardware UUID and no
  architecture**; those arrive from a probe of the machine itself. The T6 operational database's
  Bays records are a *projection* for IP and UUID fields, never the source.
- **State** comes from a per-machine probe of the machine's Munki client: Munki tools version,
  resolved manifest name, pending update count, last check time and result, architecture
  rejections, and warnings.
- Every observation is recorded **append-only** in an observation store on the admin workstation,
  carrying the source's own timestamp *and* the observation timestamp, plus the observer identity
  and the probe's outcome (including failure to reach a machine).
- Each run records its own completeness: which machines were reached, which were not, and how
  old each observation is. **An unreachable machine is recorded as unobserved, never as
  compliant.**
- The **fleet view** is a derived, read-only projection of the observation store.
- **An LLM may only render a bounded, read-only summary from the fleet view.** It may not write to
  the observation store, the metadata tree, the NAS, or any client, and it may not be the thing
  that decides a machine is healthy.

## Consequences

- "What is each Mac running?" is answerable from a record, with provenance and staleness, instead
  of from a live SSH sweep.
- The view can be built, re-read and re-rendered at any time because the observations are durable
  and immutable.
- Reachability becomes first-class: a laptop off-site produces an unobserved row, not a false
  pass.
- The collector must be idempotent per run and must not partially write a run's results.

## Rollback

Delete the observation store and its tooling. Nothing in the fleet depends on it: the store is a
read-only observer, and Munki clients never consult it.

## Amendment, 2026-09-13: what the machine export actually carries

The first bullet of the decision was wrong about the source it names. It read:

> - **Identity** comes from the Apple Remote Desktop machine export (machine name, serial number,
>   hardware UUID, MAC address, OS version, known network addresses). The T6 operational
>   database's Bays records are a *projection* for IP and UUID fields, never the source.

The export was read against that claim when the identity inventory was built (ticket 04). It has
44 columns and carries **no hardware UUID and no architecture** — and the UUID Apple Remote
Desktop does keep per computer is ARD's own identifier, not the machine's: verified on the admin
workstation, whose ARD record is `0B1919E6-1503-49DC-A573-DA2DA06A78AE` while the machine reports
`CB3D4672-22E7-573F-9CD2-5F1D2A6BEC0F` (commands and outputs in
`docs/evidence/04-uuid-source-check-2026-09-13.txt`). Taking ARD's value as a hardware UUID would
have written sixteen wrong identifiers into the fleet record.

The bullet now states what the export carries and where the UUID and architecture come from
instead: the probe of the machine, which this ADR already makes the source of state. **The
decision is unchanged** — identity still comes from the export, the Bays records are still only a
projection, and the probe is still the machine's own word — only the description of what the
export contains is corrected. Accepted by Cyril on 2026-09-13.
