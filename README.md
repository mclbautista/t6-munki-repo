# T6 Munki Fleet

Git-owned source of truth for the T6 macOS fleet's Munki repository metadata, and the
deterministic tooling that observes fleet state.

- **What this repository owns:** `pkginfo` metadata, `manifest` files, icons, catalog
  build + publish, and the fleet observation store's schema and tooling.
- **What this repository does not own:** the package payloads (they live on the T6 NAS
  Web share) and the Macs themselves.
- **Client endpoint:** `http://192.168.88.188/MunkiRepo` (T6 NAS, QTS Web Server).
- **Live repository on the NAS:** `/share/ZFS23_DATA/Web/MunkiRepo`.

Read `CONTEXT.md` before planning or changing behaviour, then the applicable ADR under
`docs/adr/` and the specification under `docs/specs/`.

## Agent skills

This repository is configured for the Matt Pocock engineering skills pack:

- Issue tracker: local Markdown — `docs/agents/issue-tracker.md`
- Triage labels: `docs/agents/triage-labels.md`
- Domain docs: `docs/agents/domain-docs.md`
- Tickets live under `.scratch/<feature>/issues/`, numbered in dependency order.
- Tickets declare `Blocked by` edges; work the frontier (tickets whose blockers are done).
- Verify acceptance criteria against the live system; a command exit code is not evidence.

## Workflow

Work moves through five separate stages: grill, spec, tickets, implement, code review. Finish one before starting the next. Work is tracked in GitHub Issues and sub-issues (spec as one issue, tickets as its sub-issues). Agent instructions: see `the Agent skills section above`.

The tracker named above is local Markdown for now. The stages apply either way, and GitHub Issues is the target tracker.
