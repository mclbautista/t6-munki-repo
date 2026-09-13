# 15: Alert on repository and fleet problems through Kulit, and stay silent otherwise

**What to build:** Repository drift, integrity failures, and fleet compliance regressions reaching Cyril through the alert transport T6 already uses, with enough context to verify each claim and with no message when nothing is actionable.

**Blocked by:** 03, 05

**Status:** ready-for-agent

**Notes:** Freshness is part of the alert: failing to observe the fleet is itself an actionable condition, and a stale observation must never be alerted on as if it were current.

## Acceptance criteria

- [ ] Alerts are delivered through Kulit — the existing owner of T6 alert delivery — and not through a new sender or a second bot identity.
- [ ] Only actionable, ORANGE/RED-level conditions trigger delivery; a healthy check produces no message at all, including no summary and no "no alert" filler.
- [ ] Every alert includes the source it is grounded in and a direct link or path to that source, so the claim can be checked without asking.
- [ ] Alert state is durable across runs: a condition that persists does not re-alert every cycle, and a condition that clears resets the state.
- [ ] Delivery failure is visible: an alert that could not be delivered is recorded as undelivered, and the run does not report success.
- [ ] A healthy period and a failing period are both exercised, with the resulting (absent or present) messages recorded as evidence.
- [ ] The alerting path is verified to be the single authoritative one — any superseded or duplicate monitor for the same condition is identified and removed.
