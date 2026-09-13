# 12: Snapshots, an off-NAS copy of what cannot be recreated, and a proven restore

**What to build:** The repository recoverable after a bad import or a wrong delete: a snapshot schedule on the repository volume, an off-NAS copy of the metadata and the payloads whose acquisition cannot be repeated, and one restore actually performed and verified.

**Blocked by:** 01

**Approval gate:** Configuring NAS snapshots and backup jobs is a system change on the NAS and requires Cyril's approval before execution.

**Status:** ready-for-agent

**Notes:** Verified 2026-09-13: zero backup jobs and no snapshots existed for the repository volume.

## Acceptance criteria

- [ ] A snapshot schedule with bounded retention is configured on the repository volume, with the policy recorded (frequency, retention, what is covered).
- [ ] The metadata tree is pushed to a second device, so repository history exists off the admin workstation.
- [ ] Every payload in the repository is classified as re-fetchable or non-reproducible; each non-reproducible payload is either copied off-NAS or has its exclusion reason recorded.
- [ ] A restore drill is performed: metadata restored from the backup, payload checksums verified, and a catalog rebuild from the restored metadata compared against the live catalogs.
- [ ] The drill's result is recorded with what was restored, where, and any difference found.
- [ ] The recovery procedure is written down so it can be followed under pressure, including how to restore a single deleted file rather than the whole repository.
