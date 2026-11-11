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

## Dependency

`munki-fleet` requires Python 3.11 or newer and the `notion` extra of
[`t6-core`](https://github.com/mclbautista/t6-core), pinned to its `v0.3.0` release tag. It does
not install the other `t6` extras. The approved interpreter on Sixto-5 is recorded in
`docs/procedures/client-onboarding.md`.

## Bays write-back

Provide the Notion integration token in `NOTION_TOKEN` without placing it in a command or Git, and
pass the verified Bays **data source ID** with `--data-source`. From the repository root:

```sh
python -m munki_fleet.cli bays-writeback --data-source "$BAYS_DATA_SOURCE_ID"
```

The command defaults to a preview; add `--apply` only after reviewing the matched rows and changes
and obtaining the required approval. Unmatched, ambiguous and changed-since-query rows are skipped.
The caller must verify the data source ID: a matching schema alone does not prove the source is Bays.
The tool re-reads each row before writing, but this is not an atomic concurrency guard. Review the
age and accuracy of the inventory and ring declarations before applying, and read back the result.

## Agent skills

This repository is configured for the Matt Pocock engineering skills pack:

- Issue tracker: GitHub Issues for specs and tickets from spec #3 on; local Markdown for the
  earlier rollout tickets — `docs/agents/issue-tracker.md`
- Triage labels: `docs/agents/triage-labels.md`
- Domain docs: `docs/agents/domain-docs.md`
- Local tickets live under `.scratch/<feature>/issues/`, numbered in dependency order.
- Tickets declare `Blocked by` edges; work the frontier (tickets whose blockers are done).
- Verify acceptance criteria against the live system; a command exit code is not evidence.
