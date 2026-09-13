# 0006: Snapshot everything, back up metadata and non-reproducible payloads

- **Status:** Accepted (2026-09-13)

## Context

Verified 2026-09-13: the repository is ~13 GB on `zpool1/zfs23`. The NAS reports **zero HBS
(backup) jobs**, and the volume's only snapshot is the initial `@:init:` marker. The imported
payloads — including a 6.87 GB DaVinci Resolve Studio DMG and curated tools whose vendor URLs are
unstable, login-gated, or rotate behind landing pages — exist in exactly one place. A bad import,
a wrong delete, or a volume event destroys the repository with no recovery path.

## Decision

Two layers of protection, plus a proven restore:

1. **ZFS snapshots on the repository volume**, on a schedule with bounded retention. Cheap,
   fast, and covers accidents and bad imports. Snapshot configuration is a NAS system change
   requiring Cyril's approval before execution.
2. **Off-NAS backup of what cannot be recreated:** the metadata tree (already versioned in Git —
   pushed to a second device) and the payloads whose acquisition cannot be repeated reliably.
   Re-downloadable vendor artifacts are not copied; the decision to exclude any payload is
   recorded with the reason.
3. **A restore drill is mandatory.** Protection is unproven until a restore has reproduced the
   metadata tree and verified payload checksums from the backup, and `makecatalogs` has
   regenerated catalogs identical to the live ones. A backup job that exists but has never been
   restored counts as incomplete.

## Consequences

- Accidental deletion or a bad import becomes recoverable within the snapshot window.
- Backup storage cost stays low because the bulk of the payload set is excluded by policy.
- The excluded-payload policy must be revisited whenever a new item's source is not reliably
  re-fetchable; recording that reason is part of importing it.
- The restore drill is recurring work, not a one-off.

## Rollback

Snapshots can be disabled and the backup job removed. The metadata tree's Git history still
provides metadata recovery, but payload recovery would be lost — so this rollback requires an
explicit decision (ADR 0008).
