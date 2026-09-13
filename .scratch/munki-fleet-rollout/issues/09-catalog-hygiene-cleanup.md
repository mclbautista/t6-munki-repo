# 09: Clean the repository's inherited mess

**What to build:** The repository's pre-existing defects removed at the source, so what is served matches what is intended: duplicate catalog entries, mixed pkginfo conventions, a test artifact in a client-facing manifest, deferred software offered to every client, and the stale share that shadows the repository's name.

**Blocked by:** 07

**Approval gate:** Every deletion in this ticket requires Cyril's approval before execution (ADR 0008), and the share removal is a NAS configuration change.

**Status:** ready-for-human (Firefox duplicate resolved 2026-09-13; the rest is outstanding)

**Notes:** Cleanup runs after the promotion path exists so nothing reaches the fleet mid-cleanup.

**Evidence added by ticket 02 (2026-09-13) — this is no longer hygiene, it is a live defect:**

- The duplicate Firefox pair is two *complete* pkginfos for the same name and version pointing at
  different installer items: `apps/firefox/Firefox-155.0.1.plist` → `.dmg` (`copy_from_dmg`, one
  `installs` entry) and `apps/firefox/Firefox-155.0.1__1.plist` → `.pkg` (one `receipts` entry).
  GoogleChrome's duplicate is the same pattern across directories (`apps/…` `.dmg`,
  `apps/Google/…` `.pkg`).
- **Catalog output is tool-version dependent because of them.** A `makecatalogs` 6.6.0 build writes
  the Firefox pair as `[.pkg, .dmg]`; a 7.3.0 build writes `[.dmg, .pkg]` (both builds
  reproducible). Since Munki takes the first entry matching a name, the first publish from the
  newer toolchain changes which Firefox installer the fleet receives.
- The pre-publish gate now blocks that by default (ADR 0009), so **routine publishing is blocked
  until this ticket resolves the duplicate**. Confirmed against the live repository: a fresh build
  of the current checkout differs from what is served in exactly one way — the Firefox entry
  order — with no item-level changes at all. Which of the two survives is a decision for Cyril, and it is a
  deletion (ADR 0008).
- Moving the surviving pkginfo to the standard layout (top-level `pkgsinfo/`, one extension
  convention) removes the ordering question entirely, because there is then only one entry.

**Status:** ready-for-human (implementation done; three NAS/client actions await Cyril)

## Acceptance criteria

- [x] Duplicate name+version catalog entries are **eliminated**. Both pairs are resolved: Firefox
      2026-09-13 (kept the `.pkg`) and GoogleChrome 2026-09-13 (kept the `.dmg`), each on Cyril's
      decision and each verified behaviour-preserving against a committed pre-image of the served
      catalog. Checkable from here on: the integrity check reports
      `no integrity findings (membership checked against the served catalogs)`.
- [~] …with the surviving entry's payload and hash the one **that is actually installed**.
      - **GoogleChrome: verified** on Cyril's Mac mini — Chrome 153.0.8010.37 is installed,
        matching the surviving `.dmg` entry's `installs`, and the retired `.pkg`'s receipt
        `com.google.Chrome` is absent, so the retired entry would have re-installed over a current
        copy. Not verified fleet-wide: only one machine was checked.
      - **Firefox: not verified, and now moot.** The pilot ran Firefox 154.0 with no
        `org.mozilla.firefox` receipt, so neither entry's install path put it there. Firefox was
        withdrawn on Cyril's 2026-09-13 decision, so no Firefox entry survives to be wrong.
      - Evidence: `docs/evidence/09-firefox-retirement.txt`, `docs/evidence/09-googlechrome-retirement.txt`.
- [x] The retired pkginfos were **_detected_** as NAS-only drift, and **_deleted_** from the NAS on
      Cyril's approval. Verified in both directions: each NAS file's sha256 matched its committed
      pre-image exactly before removal, and after removal both are absent and return HTTP 404.
- [x] Deferred vendor suites are removed from `site_default`'s optional list and appear in no
      manifest section. Verified across all 27 manifests: zero occurrences of
      `davinci-resolve-studio` or `davinci-resolve-project-server`. Their pkginfos stay parked in
      `testing`, and are **declared** promotion exclusions in `data/rings.json` so a future plan
      does not silently promote them.
- [x] The staged-but-unmanaged nested `apps` area is resolved: each item is either fully imported
      into the standard layout or withdrawn, and the decision for each is recorded.
      All 9 items resolved — **7 withdrawn** (Cyberduck, Dropbox, Firefox, MSAutoUpdate, MSEdge,
      MSTeams, Spotify: outside the documented baseline, no recorded decision to offer them, Cyril
      2026-09-13) and **2 imported to the standard layout** (GoogleChrome, VLC, moved by `git mv`).
      Every withdrawal carries a record in `data/withdrawals.jsonl` with the item, version,
      timestamp, approver, reason, source path and source sha256 — 9 records written.
- [x] All pkginfos follow one declared extension convention, and the nested directories no longer
      split the repository's layout. **36 → 28 pkginfos, all `.pkginfo`, all at `pkgsinfo/` top
      level**; `remaining non-standard paths: []`. The convention is declared in `CONTEXT.md` as
      the repository layout convention, in the glossary and in the boundaries.
- [x] The **catalog** half of the cleanup is live: the served catalog is now 28 items, 28 unique
      names, published with 8 declared removals and 3 declared file changes, verified
      `94/94` over both the filesystem and HTTP.
- [x] The retired files are **removed from the NAS** — done 2026-09-13 on Cyril's approval, with the
      `reconcile` command. All 11 declared paths were removed and every one **hash-matched its
      record** (9 against `data/withdrawals.jsonl`, 2 against the checkout's new paths); the run
      refused the same request undeclared, first. After: drift `0/0/0/0`, `verify` 94/94 over both
      filesystem and HTTP, integrity clean. Evidence: `docs/evidence/09-reconcile-plan.txt`.
      Superseded text: [ ] The retired files are **removed from the NAS**. Eleven files are present only on the target
      and are declared, dry-run, and **hash-verified for removal**: 9 against
      `data/withdrawals.jsonl`, 2 against the checkout's new paths. Plan:
      `docs/evidence/09-reconcile-plan.txt`. Command ready:
      `munki_fleet.cli reconcile --expect-remove-file …`. **Awaiting Cyril: this is a deletion on
      the NAS.** Until it runs, `check` reports drift 11 by design.
- [x] The payloads nothing referenced were **removed from the NAS** — done 2026-09-13 on Cyril's
      approval. 10 orphans (the 11th was a 0-byte `.DS_Store`, skipped by design), **2,229,887,796
      bytes**, each recorded with its sha256 in `data/payload-removals.jsonl` before deletion and
      verified absent after. Measured effect: volume used **12.1 GB → 10.2 GB**, `pkgs/` 13 GB → 11 GB.
      The retained payloads still serve (spot-checked HTTP 200). Evidence:
      `docs/evidence/09-payload-removal.txt`. Superseded text: the payloads were described as
      still present: **11 files, 2,229.9 MB** —
      MSEdge 432.3 MB, Dropbox 398.3 MB, MSTeams 355.4 MB, the retired GoogleChrome `.pkg`
      264.0 MB, Cyberduck 181.4 MB, Spotify-arm64 165.5 MB, both Firefox payloads 159.4 + 144.4 MB,
      `Telegram-1.0.dmg` 124.7 MB (a stray beside the live 12.10), MSAutoUpdate 4.5 MB,
      `.DS_Store`. Of 39 payloads / 13.0 GB, **28 remain referenced**. Cyril approved the
      withdrawals, not the payload deletions, so they stay until that is decided.
- [ ] **CORRECTED — the stale NAS path is a configured share, and it is not empty.** Read from the
      NAS itself: share `MunkiRepo`, **volume 7** (ZFS22), not hidden, **allocated 284,240 bytes**,
      6 directories, 2 files, and `guest` has **read-only** access. Its removal leaves the fleet
      untouched: nothing mounts it (`/etc/fstab` on the Mac Mini mounts the `Web` share), Munki's
      `SoftwareRepoURL` is `http://192.168.88.188/MunkiRepo` served from `Web`, and `munkiimport`
      uses `file:///Users/t6/Mnt/Web/MunkiRepo` — all verified 2026-09-13. The ticket
      used to call it "the stale, empty NAS share". It is `[MunkiRepo]` in
      `/etc/config/smb.conf`, `path = /share/ZFS22_DATA/MunkiRepo`, `browsable = yes`, with a
      recycle bin. It holds a **hollow skeleton** — empty `catalogs/ icons/ manifests/ pkgs/
      pkgsinfo/` from 2026-09-10, a `.DS_Store` and `@Recycle`, 69 KB, no metadata and no payloads.
      That is the "can be mistaken for the repository" hazard, and worse than empty precisely
      because it is browsable and looks right. The `Web` share root also carries three stray empty
      directories (`catalogs/ icons/ manifests/`, 2026-09-10) beside the live `MunkiRepo/`.
      **Removal is a NAS share-configuration change and a WebUI action** — the QNAP MCP exposes no
      share-deletion tool, and the NAS shell is read-only by design. **Awaiting Cyril.**
- [ ] After cleanup the drift check reports clean — **blocked by another session's in-flight work,
      not by this ticket.** It reported `0/0/0/0` immediately after the reconcile; it now reports two
      *missing-on-target* findings, `manifests/303A-Mac-Mini-M4-Pro` and `manifests/Sixto-5`, which
      that session committed (`c29821b`) to give the two manifest-less machines their own manifests.
      Publishing them is their declared change to make, not mine to sweep up. Everything this ticket
      owns is clean. both catalogs build, and every manifest's items
      resolve with an existing payload. Current state: **both catalogs build** (41,135 bytes each),
      **every manifest item resolves to an existing payload** (28/28 referenced), integrity clean;
      drift is the 11 declared files above. This closes when the reconcile runs and the payload
      decision is made.

## Loose end I introduced, and what it needs

Deleting the `t6-test-client` manifest left **Cyril's Mac mini (`202`) pointing at a manifest that
no longer exists** — it still carries `ClientIdentifier = t6-test-client` (read on the machine
2026-09-13). Munki falls back to `site_default`, so it keeps receiving software, but until the
override is removed it cannot be pilot #2: it resolves to the wrong manifest and would never read
the `testing` ring. The one-line fix, which is a change to a Mac and therefore Cyril's call:

```bash
sudo defaults delete /Library/Preferences/ManagedInstalls ClientIdentifier
```
