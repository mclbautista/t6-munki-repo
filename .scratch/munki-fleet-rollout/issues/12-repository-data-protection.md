# 12: Snapshots, an off-NAS copy of what cannot be recreated, and a proven restore

**What to build:** The repository recoverable after a bad import or a wrong delete: a snapshot schedule on the repository volume, an off-NAS copy of the metadata and the payloads whose acquisition cannot be repeated, and one restore actually performed and verified.

**Blocked by:** 01

**Approval gate:** Configuring NAS snapshots and backup jobs is a system change on the NAS and requires Cyril's approval before execution. **Approved 2026-09-13** — the decision packet `.scratch/munki-fleet-rollout/approvals/12-and-13-nas-system-changes.md` records 12A, 12B and 12C as approved as recommended.

**Status:** done (2026-09-13) — five criteria by doing them, the sixth closed by an explicit decision not to, with the residual risk recorded.

**Notes:** Verified 2026-09-13: zero backup jobs and no snapshots existed for the repository volume.

## Acceptance criteria

- [x] **Snapshotting: decided against, and the decision is the recorded policy.**
  - **Cyril, 2026-09-13: "I don't want to enable snapshotting on the NAS. I'm okay with this as is."** The criterion asks for a schedule *with the policy recorded*; the policy of record is therefore **no snapshots on the repository volume**, stated here and in `docs/recovery.md` so a future reader finds a decision rather than an omission.
  - **Residual risk accepted:** the served tree on the NAS has no point-in-time recovery. A bad import or a wrong delete on the served copy is recoverable for the **metadata** (Git history, on this machine and off-site) but not for the **payloads**, whose only other copy is the one this ticket placed on the admin workstation. Deleting both the NAS payload and that copy loses the non-reproducible item for good; the account-gated ones need the vendor account again.
  - **What that leaves as the protection path:** the recovery procedure in `docs/recovery.md`, the drill in `docs/evidence/12-drill-2026-09-13.txt`, and the off-NAS payload copy. The revisit trigger, should the calculus change: a second copy target existing, or a payload whose re-acquisition turns out to be impossible.
  - For the record, had it been enabled it would have been a QTS UI action — no snapshot capability exists in the QNAP MCP tool set and the NAS shell is read-only. Current state re-read 2026-09-13: only installation-time `@:init:` snapshots (30 May 2026, 174 KB each) exist on the pool's datasets. No snapshot capability exists in the QNAP MCP tool set, and the NAS shell is read-only for this user, so snapshots are a QTS UI action. Current state, re-read 2026-09-13: `zfs list -t snapshot` shows only the installation-time `@:init:` snapshots from 30 May 2026 (174 KB each) on the pool's datasets — nothing scheduled, nothing since.
  - **Settings proposed for the `Web` volume** (this is what the UI needs): a daily schedule, keeping 7 daily plus 4 weekly snapshots (~11 kept), snapshot space reserved explicitly rather than left to the default, and the schedule covering the whole `Web` share because the repository is a path inside it — `Web/MunkiRepo` cannot be snapshotted separately from `Web`.
  - **Verify after enabling:** `ssh t6-nas 'zfs list -t snapshot -o name,creation,used'` should show dated snapshots after the first run, and Storage & Snapshots → Snapshots should list them for the volume.
- [x] **The metadata tree is pushed to a second device, so repository history exists off the admin workstation.**
  - The private GitHub remote `mclbautista/t6-munki-repo` (visibility PRIVATE, checked) holds the history, and the local branch is pushed to it. Verified the other way round: the restore drill **cloned from that remote** and got this commit, so the copy is real and current rather than assumed.
  - This is the "pushed Git history" half of 12B. The HBS-job half was not needed for the metadata: GitHub *is* the second device for it.
- [x] **Every payload in the repository is classified as re-fetchable or non-reproducible; each non-reproducible payload is either copied off-NAS or has its exclusion reason recorded.**
  - Classification of all 28 payloads (10.76 GB) in `docs/evidence/12-payload-classification-2026-09-13.tsv`, from the pkginfos' own `installer_item_location` plus the vendor's distribution model as the stated basis:
    | class | items | bytes | outcome |
    |---|---|---|---|
    | re-fetchable from the vendor | 20 | 1.92 GB | exclusion reason recorded: re-downloadable, so no copy is kept |
    | re-fetchable only with a vendor account | 7 | 8.74 GB | **copied off-NAS**, sha256 verified |
    | non-reproducible (packaged in house) | 1 | 0.10 GB | **copied off-NAS**, sha256 verified |
  - The copy is on the **admin workstation** (`Sixto-5`, `~/munki-offnas-copy/`, 8.3 GiB), a different device from the NAS: each file's sha256 on the target equals the `installer_item_hash` its pkginfo declares. SCP/SFTP is unavailable to the NAS SSH user, so the files were streamed over the shell and verified after writing.
  - The 20 re-fetchable rows are an explicit, recorded exclusion, not an omission: the point of the copy is the payloads whose acquisition cannot be repeated, and 12B approved exactly that.
  - **Durability caveat, recorded rather than glossed:** the admin workstation is one device, and it is not itself backed up by this ticket. The copy survives a NAS failure; it does not survive both. A better home (an external drive or a second NAS) is a further decision, and the copy is small enough to move when one exists.
- [x] **A restore drill is performed: metadata restored from the backup, payload checksums verified, and a catalog rebuild from the restored metadata compared against the live catalogs.**
  - Drill: `docs/evidence/12-drill-2026-09-13.txt`.
  - Metadata **restored from the off-NAS copy** (clone of the private GitHub remote into `/tmp`; the live checkout and the NAS untouched): 183 tracked files, 29 manifest files, 28 pkginfos, all parsing.
  - Comparison against the live catalogs: restored metadata 28 items, the checkout's catalog 28, the **served catalog on the NAS 28** — the checkout's catalog and the served one are identical, nothing is only in one side, and **no entry's payload hash differs**.
  - Payload checksums verified on the NAS (read-only, 48 s): 28 of 28 match the hash their pkginfo declares; no declared payload is missing (and one stray `.DS_Store` sits in the served `pkgs/` — junk, left in place because deleting on the NAS needs approval).
  - The rebuild itself is the drill's finding: `makecatalogs` from the restored metadata alone emits **an empty catalog**, because payloads are not in Git. The metadata is fully recoverable; the payloads were the unprotected part — which is what the criterion above now fixes.
- [x] **The drill's result is recorded with what was restored, where, and any difference found.**
  - `docs/evidence/12-drill-2026-09-13.txt`: source, path, counts, the comparison table, the payload verification, and the difference stated plainly ("the metadata is protected; the payloads are not").
- [x] **The recovery procedure is written down so it can be followed under pressure, including how to restore a single deleted file rather than the whole repository.**
  - `docs/recovery.md`: what exists where; the single-file restore (metadata file, and payload variant by class) with the commands actually exercised; the whole-metadata restore; the NAS-side restore including the snapshot path once criterion 1 exists; the verification steps; and what is not protected today.
  - Two operational facts came out of doing this and are in the doc: payloads are not in Git, so a metadata restore cannot rebuild catalogs where the payloads are invisible; and the served tree is what clients read, so a file restored into the checkout changes nothing until it is published.

## What remains

1. ~~The snapshot schedule~~ — **closed by Cyril's decision not to snapshot the NAS, 2026-09-13.** No further action, and the residual risk is recorded above.
2. **Where the payload copy should durably live** — today it is on the admin workstation. The non-reproducible item is 100 MB and the account-gated set 8.3 GiB, so both fit on an external drive or a second NAS whenever one is chosen.
3. **Nothing to decide about the re-fetchable 20** — they are an explicit recorded exclusion.
