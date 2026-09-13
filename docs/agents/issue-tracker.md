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

## Working in this repository alongside another agent

More than one agent can be working this repository at the same time, and more than one has.

- **Never `git add -A` or `git add .`.** Stage the paths you changed. A blanket add swept another
  session's in-flight ticket work into an unrelated commit here once already (see the git note on
  that commit), which misattributes the work and puts a half-finished suite in the history.
- **Confirm your own tests before committing, and never through a pipe.** `python3 -m pytest | tail`
  reports the pipe's status, not pytest's; a failing suite was committed and pushed that way.
- **A failing test in another session's file is not yours to fix mid-flight.** Report it; do not
  edit a file someone else is actively writing.
- **Do not rewrite shared history** to correct a mistake: annotate the commit with `git notes` and
  record the correction in a follow-up commit.
- **Check the count before citing it.** Test counts and hashes in tickets are read from command
  output, never recalled.
