# 14: Specify the fleet view's user-facing shape by grilling

**What to build:** A specification for how fleet state is presented to a human: what a person sees when they ask what the fleet is running, produced by an adversarial design interview grounded in the real observation data rather than by assumption.

**Blocked by:** 05

**Status:** ready-for-agent

**Notes:** Requested by Cyril: the UI shape is to be grilled, not assumed. No implementation in this ticket — it produces a specification and its decisions.

## Acceptance criteria

- [ ] The design session is run against the real observation model and a real sample of observed data — never against invented examples — and the sample used is recorded.
- [ ] The specification states, for the view: its audience, the questions it must answer, its source snapshot and version, its assumptions, and its confidence and staleness language.
- [ ] The specification states explicitly that the view is read-only, what it cannot change, and what it must never claim — in particular, it may not present an unobserved machine as compliant.
- [ ] The specification defines the module boundary for the view and its public interface, and states whether it is a new module or an adaptation of an existing one.
- [ ] The specification defines what freshness looks like: how the age of an observation is shown, and what a stale view says.
- [ ] Decisions are recorded as settled, open, or out of scope, and Cyril confirms alignment before implementation begins.
- [ ] The specification is published alongside the existing specification and respects the vocabulary in `CONTEXT.md`.
