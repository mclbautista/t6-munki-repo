# Issue Tracker

This repository uses a local Markdown issue tracker.

## Workflow

- Issues live under `.scratch/<feature>/issues/`, one file per ticket.
- Number tickets in dependency order (blockers first).
- Each ticket states what it delivers, its blocking tickets, its status, and acceptance criteria.
- Blocking edges are declared as `Blocked by` references to ticket numbers.
- The open frontier is the set of tickets whose blockers are complete and whose status is
  `ready-for-agent` (or `ready-for-human` for decisions and approvals).
- A ticket is complete only when every acceptance criterion has been verified against the live
  system and the evidence is recorded in the ticket. A command exit code is not evidence.
- Record decisions and implementation evidence in the ticket or an ADR — never secrets,
  credentials, or keys.

## Verification evidence

Acceptance evidence should be reproducible: the command or check, what it returned, and which
system it ran against. Where a client machine is involved, name the machine and the manifest it
resolved.
