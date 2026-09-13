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
  - For the record, had it been enabled it would have been a QTS UI action: no snapshot capability exists in the QNAP MCP tool set, and the NAS shell is read-only for this user. **Current state, re-read by the review and again here:** the repository volume `zpool1/zfs23` carries **only** its installation-time `@:init:` snapshot (10 Sep 2026, 166 KB) — nothing scheduled, nothing since. The NAS holds 18 snapshots in total, but the others belong to other datasets, mostly per-app filesystems under `zpool1/zfs530/zfs5300002` that are the App Center's rather than this repository's. An earlier version of this bullet generalised from a truncated listing and said "30 May 2026, 174 KB each"; that was wrong and is corrected here.
  - **Settings proposed for the `Web` volume** (this is what the UI needs): a daily schedule, keeping 7 daily plus 4 weekly snapshots (~11 kept), snapshot space reserved explicitly rather than left to the default, and the schedule covering the whole `Web` share because the repository is a path inside it — `Web/MunkiRepo` cannot be snapshotted separately from `Web`.
  - **Verify after enabling:** `ssh t6-nas 'zfs list -t snapshot -o name,creation,used'` should show dated snapshots after the first run, and Storage & Snapshots → Snapshots should list them for the volume.
- [x] **The metadata tree is pushed to a second device, so repository history exists off the admin workstation.**
  - The private GitHub remote `mclbautista/t6-munki-repo` (visibility PRIVATE, checked) holds the history, and the local branch is pushed to it — checked with `git rev-list --count origin/main..HEAD` (0) after the closing commit, because "pushed" is only true until the next local commit. Verified the other way round: the restore drill **cloned from that remote** and got this commit, so the copy is real and current rather than assumed.
  - This is the "pushed Git history" half of 12B. **The other half — an HBS job — is not implemented, and that is an open item rather than a dismissal.** 12B was approved as "an HBS job *and* a pushed Git history, because they cover different failures". For the *metadata*, the Git remote is the second device and an HBS job would add nothing; for the *payloads*, an HBS job is exactly the automation that would keep the copy current, and today that copy is a manual one-off. Recorded as outstanding.
- [x] **Every payload in the repository is classified as re-fetchable or non-reproducible; each non-reproducible payload is either copied off-NAS or has its exclusion reason recorded.**
  - Classification of all 28 payloads (10.76 GB) in `docs/evidence/12-payload-classification-2026-09-13.tsv`, from the pkginfos' own `installer_item_location` plus the vendor's distribution model as the stated basis:
    | class | items | bytes | outcome |
    |---|---|---|---|
    | re-fetchable from the vendor | 20 | 1.92 GB | exclusion reason recorded: re-downloadable, so no copy is kept |
    | re-fetchable only with a vendor account | 7 | 8.74 GB | **copied off-NAS**, sha256 verified |
    | non-reproducible (packaged in house) | 1 | 0.10 GB | **copied off-NAS**, sha256 verified |
  - The copy is on the **admin workstation** (`Sixto-5`, `~/munki-offnas-copy/`, **9 files, 8.4 GiB** — the ninth is `FrameioTransfer-1.12.0.dmg`, reclassified by the review and copied), a different device from the NAS: each file's sha256 on the target equals the `installer_item_hash` its pkginfo declares. SCP/SFTP is unavailable to the NAS SSH user, so the files were streamed over the shell and verified after writing.
  - The 20 re-fetchable rows are an explicit, recorded exclusion, not an omission: the point of the copy is the payloads whose acquisition cannot be repeated, and 12B approved exactly that.
  - **Review correction:** `FrameioTransfer-1.12.0.dmg` was classed re-fetchable while its sibling `FrameioDrive-1.12.0.pkg` was classed account-gated — the same vendor, the same gate. It is now classed account-gated and copied, which is why the copy is nine files rather than eight.
  - **Not part of this ticket, for the record:** `c29821b` also carries two machine manifests (`303A-Mac-Mini-M4-Pro`, `Sixto-5`) from the recorded role-matrix work. They are not this ticket's deliverable; the review flagged the mixture and this is the cross-reference that settles it.
  - **Durability caveat, recorded rather than glossed:** the admin workstation is one device, and it is not itself backed up by this ticket. The copy survives a NAS failure; it does not survive both. A better home (an external drive or a second NAS) is a further decision, and the copy is small enough to move when one exists.
- [x] **A restore drill is performed: metadata restored from the backup, payload checksums verified, and a catalog rebuild from the restored metadata compared against the live catalogs.**
  - Drill: `docs/evidence/12-drill-2026-09-13.txt`.
  - Metadata **restored from the off-NAS copy** (clone of the private GitHub remote into `/tmp`; the live checkout and the NAS untouched): **182 tracked files at `c29821b`** (the commit the clone was taken at — 203 at `HEAD` the same evening, so the count belongs with its commit), 29 manifest files, 28 pkginfos, all parsing.
  - Comparison against the live catalogs: restored metadata 28 items, the checkout's catalog 28, the **served catalog on the NAS 28** — the checkout's catalog and the served one are identical, nothing is only in one side, and **no entry's payload hash differs**.
  - **The rebuild itself, done properly:** `munki_fleet.catalogs.build_catalogs` (which runs `makecatalogs --skip-pkg-check`) rebuilt both catalogs **from the restored metadata alone, with no payloads present**, and the rebuilt `all` is **byte-identical to the served catalog** — 41,135 bytes, 28 items. That is ADR 0006's own wording, satisfied. **Correction:** the first version of this record ran *bare* `makecatalogs`, saw an empty catalog, and wrongly concluded that a metadata-only tree cannot rebuild catalogs. Bare `makecatalogs` skips every item whose payload is absent, warns once per item, and exits **0**. The trap is now a warning in the recovery procedure, because a restore performed that way would publish an empty catalog.
  - Payload checksums verified on the NAS (read-only, 48 s): 28 of 28 match the hash their pkginfo declares; no declared payload is missing (and one stray `.DS_Store` sits in the served `pkgs/` — junk, left in place because deleting on the NAS needs approval).
  - The metadata is fully recoverable, catalogs included, from the off-NAS copy alone.
- [x] **The drill's result is recorded with what was restored, where, and any difference found.**
  - `docs/evidence/12-drill-2026-09-13.txt`: source, path, counts, the comparison table, the payload verification, and the difference stated plainly ("the metadata is protected; the payloads are not").
- [x] **The recovery procedure is written down so it can be followed under pressure, including how to restore a single deleted file rather than the whole repository.**
  - `docs/recovery.md`: what exists where; the single-file restore (metadata file, and payload variant by class) with the commands actually exercised; the whole-metadata restore; the NAS-side restore including the snapshot path once criterion 1 exists; the verification steps; and what is not protected today.
  - Two operational facts came out of doing this and are in the doc: payloads are not in Git, so a metadata restore cannot rebuild catalogs where the payloads are invisible; and the served tree is what clients read, so a file restored into the checkout changes nothing until it is published.

## What remains

1. ~~The snapshot schedule~~ — **closed by Cyril's decision not to snapshot the NAS, 2026-09-13.** No further action, and the residual risk is recorded above.
2. **Where the payload copy should durably live** — today it is on the admin workstation: **9 files, 8.4 GiB**. The non-reproducible item is 100 MB and the account-gated set 8.4 GiB, so both fit on an external drive or a second NAS whenever one is chosen.
3. **Nothing to decide about the re-fetchable 20** — they are an explicit recorded exclusion.
## Review disposition (2026-09-13)

A two-axis review verified this ticket's claims independently (read-only, against the NAS, the
GitHub clone and the copy on the admin workstation). Every finding and what happened to it:

| finding | disposition |
|---|---|
| "183 tracked files" does not reproduce (189 at the commit; 193 in a fresh clone) | **corrected.** A file count means nothing without its commit: it is 182 at `c29821b` (what the drill cloned), 189 at `71e9e43`, 203 at `HEAD` that evening. The record now carries the commit with the count, and the clone's own one-file discrepancy is not papered over. |
| `recovery.md` contradicts itself: "one NAS volume, no off-NAS copy" against its own line saying payloads are NAS-only | **fixed in both places.** The table and the "not protected today" summary now state the nine-file, 8.4 GiB copy and that it is itself unprotected. |
| `recovery.md`'s single-file restore publishes with `scp`, which cannot work (SCP/SFTP is refused for the NAS SSH user) | **fixed.** It now uses the repository's publish path, `python3 -m munki_fleet.cli publish --target t6-nas:<path>`, with the reminder that the pre-publish gate refuses an undeclared change (ADR 0009). |
| the drill's conclusion that a metadata-only tree cannot rebuild catalogs | **the reviewer was right that the claim did not reproduce, and wrong about what it meant.** The cause was my invocation: **bare** `makecatalogs` skips every item whose payload is absent, warns once per item, and exits 0 with an empty catalog. The repository's own builder passes `--skip-pkg-check`, and with it the rebuild from the restored metadata **alone** is byte-identical to the served catalog: 41,135 bytes, 28 items. So ADR 0001's "does not require the package payloads" holds, the empty catalog was mine, and the real finding is the trap — now the first rule in `recovery.md`, because a restore done bare would publish an empty catalog. |
| "Every command here has been exercised" | **fixed.** The doc now marks which commands were exercised, and two more were exercised for real during this pass: `git checkout <commit> -- <path>` and `plutil -lint`. |
| criterion 2's "the local branch is pushed to it" was false at review time (one unpushed commit) | **fixed.** Re-checked with `git rev-list --count origin/main..HEAD` (0), and the ticket now records that "pushed" is a state to re-check rather than a permanent property. |
| 12B's HBS-job half is missing while the approval named both | **recorded as an open item**, with why: for the metadata the Git remote is the second device, but for the payloads an HBS job is exactly the automation that would keep the copy current, and that copy is a manual one-off today. |
| ADR 0006's rebuild clause was ticked on a weaker comparison | **now satisfied properly** — the byte-identical rebuild above is exactly ADR 0006's wording, from a metadata-only tree. |
| the no-snapshots policy lives only in the ticket and the recovery doc; ADR 0006 still calls for scheduled snapshots | **recorded as an ADR 0006 amendment for Cyril, not applied** — a design record is not mine to rewrite. Proposed: *"Amendment, 2026-09-13: the snapshot half of protection (1) is declined by decision — the repository volume carries no scheduled snapshots, so there is no point-in-time recovery of the served tree. Protection rests on the Git history (this machine and a second device), the off-NAS copy of the payloads that cannot be re-acquired, and the procedure in `docs/recovery.md`. Revisit when a second copy target exists, or a payload turns out to be un-re-acquirable."* |
| the snapshot claim "30 May 2026, 174 KB each" was generalised from a truncated listing | **fixed** with the accurate listing: `zpool1/zfs23@:init:` only (10 Sep 2026, 166 KB) for the repository volume, 18 across the NAS, the rest belonging to App Center datasets. |
| `FrameioTransfer-1.12.0.dmg` classed re-fetchable while its sibling is account-gated | **fixed and made real:** reclassified as account-gated, copied to `~/munki-offnas-copy/`, sha256 verified. Nine files now, not eight. |
| ticket 12's change set carried two machine manifests from the role-matrix work | **clarified** with a cross-reference: they belong to tickets 04/05's story, not this deliverable. |

What the review confirmed as reproducing: the 28/28/28 catalog comparison with the checkout's
catalog byte-identical to the served one, the payload hash verification (28 of 28; 51 s on the
reviewer's run against 48 s on mine), the classification's row-by-row byte agreement with `ls -l`
and the 20/7/1 split, and that the off-NAS copy holds exactly the files it claims with matching
hashes.
