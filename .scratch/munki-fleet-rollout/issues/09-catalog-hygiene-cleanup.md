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

## Acceptance criteria

- [ ] Duplicate name+version catalog entries are eliminated, with the surviving entry's payload and
      hash the one that is actually installed.
      → **Firefox: done 2026-09-13.** On Cyril's decision the `.dmg` pkginfo
      (`apps/firefox/Firefox-155.0.1.plist`) was retired and the `.pkg`
      (`apps/firefox/Firefox-155.0.1__1.plist`) survives. **Verified:** the surviving entry is
      byte-identical to the entry the fleet was already being served (Munki takes the first match),
      so the installer clients are offered does not change — re-derivable from the committed
      pre-image at `docs/evidence/09-catalog-before-firefox-retirement/`. **Not verified:** the
      "actually installed" half of this criterion. The pilot `202-TOC-M4-Max` runs Firefox 154.0
      with no `org.mozilla.firefox` receipt, so neither pkginfo's install path put Firefox there.
      Both entries install 155.0.1 and differ in detection mechanics (`installs` vs `receipts`), so
      retiring one removes an ambiguity rather than being a no-op. Details:
      `docs/evidence/09-firefox-retirement.txt`.
      **GoogleChrome remains duplicated and still needs the same decision**, which is why this
      criterion is unticked.
- [x] The retired pkginfo is **_detected_** as NAS-only drift. Ticket 03's live run reports exactly
      one drift finding: `pkgsinfo/apps/firefox/Firefox-155.0.1.plist`, present on the NAS and not in
      the checkout, still served over HTTP. It was left deliberately so the detection had a real case
      and so the deletion happens through the reconciling path rather than by hand.
- [ ] The retired pkginfo is **_deleted_** from the NAS. This is a deletion on the NAS and needs
      Cyril's approval; the check that detects it exists, the reconciler that removes it does not., with the surviving entry's payload and hash the one that is actually installed.
- [ ] The test artifact item is removed from every manifest section, and its pkginfo is retired from the repository.
- [ ] Deferred vendor suites are removed from `site_default`'s optional list and appear in no manifest section.
- [ ] The staged-but-unmanaged nested `apps` area is resolved: each item is either fully imported into the standard layout or withdrawn, and the decision for each is recorded.
- [ ] All pkginfos follow one declared extension convention, and the nested directories no longer split the repository's layout.
- [ ] The stale, empty NAS share that shadows the repository's name is removed so it cannot be mistaken for the repository.
- [ ] After cleanup the drift check reports clean, both catalogs build, and every manifest's items resolve with an existing payload.
