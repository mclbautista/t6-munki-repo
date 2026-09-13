# Domain Documents

## Context

`CONTEXT.md` at the repository root is the authoritative glossary and boundary document. Read it
before planning or changing behaviour.

## Architecture decisions

ADRs live in `docs/adr/`. Each ADR documents one durable decision with status, context,
decision, consequences, and a rollback or supersession path. Decisions that constrain what an
agent may do without approval are ADRs, not conventions.

## Specifications

Specifications live in `docs/specs/`. They are the implementation authority for the scope they
describe. A specification that contradicts an ADR is wrong; fix the specification.

## Agent behaviour

- Read `CONTEXT.md`, the relevant ADRs, and the applicable specification before implementing.
- Use T6 domain terms in tickets, code, tests, and documentation.
- Keep secrets, credentials, and runtime state outside Git.
- Treat the NAS repository, the observation store, and every Mac as external systems: inspect
  them, verify every claim about them, and never narrate a result you did not read back.
- Distinguish planned, attempted, completed, and verified work in every ticket.
