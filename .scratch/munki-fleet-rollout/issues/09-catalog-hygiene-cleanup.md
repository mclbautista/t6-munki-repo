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

- [x] Duplicate name+version catalog entries are eliminated (the Firefox pair must resolve to exactly
      one entry, so a rebuild can no longer reorder them) → **Firefox done 2026-09-13** on Cyril's
      decision to keep the `.pkg`: `apps/firefox/Firefox-155.0.1.plist` (the `.dmg`, `copy_from_dmg`)
      was retired, `apps/firefox/Firefox-155.0.1__1.plist` (the `.pkg`, one receipt) survives.
      Verified behaviour-preserving: the entry clients receive is byte-identical to what they were
      already getting, and a publish now passes the gate with no declarations at all. **GoogleChrome
      remains duplicated** and still needs the same decision.
- [ ] The retired pkginfo is deleted from the NAS as well as the checkout — it is still served at
      `pkgsinfo/apps/firefox/Firefox-155.0.1.plist`, which is exactly the NAS-only drift ticket 03
      will report. Left deliberately so 03 has a real case to detect and so the deletion happens
      through the reconciling path rather than by hand., with the surviving entry's payload and hash the one that is actually installed.
- [ ] The test artifact item is removed from every manifest section, and its pkginfo is retired from the repository.
- [ ] Deferred vendor suites are removed from `site_default`'s optional list and appear in no manifest section.
- [ ] The staged-but-unmanaged nested `apps` area is resolved: each item is either fully imported into the standard layout or withdrawn, and the decision for each is recorded.
- [ ] All pkginfos follow one declared extension convention, and the nested directories no longer split the repository's layout.
- [ ] The stale, empty NAS share that shadows the repository's name is removed so it cannot be mistaken for the repository.
- [ ] After cleanup the drift check reports clean, both catalogs build, and every manifest's items resolve with an existing payload.
