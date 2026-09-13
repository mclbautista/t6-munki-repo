# 05: Deterministic per-machine state probe and an append-only observation store

**What to build:** The single authoritative record of what state each Mac is in: a deterministic probe of each machine's Munki client, written append-only with provenance, so that fleet state is read from a record with a known age instead of from a live sweep.

**Blocked by:** 04

**Status:** ready-for-agent

**Notes:** The store holds fleet state, not the fleet. It must not hold credentials, and it must not be a prerequisite for any Mac receiving software: if the observer is down, software delivery is unaffected.

## Acceptance criteria

- [ ] For each reachable machine the probe records: Munki tools version, resolved manifest name, pending update count, last check time and result, architecture rejections, and client warnings.
- [ ] Every observation carries the source's own timestamp, the observation timestamp, the observer identity and the machine's identity (serial) — never a name alone.
- [ ] A machine that cannot be reached produces an explicit unobserved record for that run; no code path can write a compliant-looking row for an unreached machine.
- [ ] The store is append-only: no run modifies or deletes a prior observation. Asserted by a test.
- [ ] Each run records its own completeness — how many machines were targeted, reached, and unobserved.
- [ ] Observation age is computed per machine and exposed as staleness, so a stale reading cannot be presented as current.
- [ ] Tests run against recorded fixture report payloads covering: a healthy machine, an unreachable machine, a machine with an architecture rejection, and a stale observation.
