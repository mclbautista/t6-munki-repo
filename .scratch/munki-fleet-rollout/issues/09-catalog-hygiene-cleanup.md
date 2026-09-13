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

- [x] Duplicate name+version catalog entries are **eliminated**. Both pairs are resolved: Firefox
      2026-09-13 (kept the `.pkg`) and GoogleChrome 2026-09-13 (kept the `.dmg`), each on Cyril's
      decision and each verified behaviour-preserving against a committed pre-image of the served
      catalog. Checkable from here on: the integrity check now reports
      `no integrity findings (membership checked against the served catalogs)` — no duplicate names
      anywhere in the served catalogs.
- [~] …with the surviving entry's payload and hash the one **that is actually installed**.
      - **GoogleChrome: verified** on the pilot Cyril's Mac mini (202) — Chrome 153.0.8010.37 is
        installed, matching the surviving `.dmg` entry's `installs`, and the retired `.pkg`'s receipt
        `com.google.Chrome` is absent, so the retired entry would have re-installed over a current
        copy. Not verified fleet-wide: only one machine was checked, and `202-TOC-M4-Max` has no
        Chrome installed.
      - **Firefox: not verified.** The pilot `202-TOC-M4-Max` runs Firefox 154.0 with no
        `org.mozilla.firefox` receipt, so neither pkginfo's install path put Firefox there. What is
        verified is narrower: the entry clients are *offered* is unchanged, and both entries install
        155.0.1 while differing in detection mechanics (`installs` vs `receipts`).
      - Evidence: `docs/evidence/09-firefox-retirement.txt`, `docs/evidence/09-googlechrome-retirement.txt`.
- [x] The retired pkginfos are **_detected_** as NAS-only drift. Ticket 03's live run reported exactly
      two drift findings, naming them: `pkgsinfo/apps/firefox/Firefox-155.0.1.plist` and
      `pkgsinfo/apps/Google/GoogleChrome-153.0.8010.37.plist`, both present on the NAS and absent from
      the checkout, both still served over HTTP (200). Detecting them was the point of leaving them.
- [x] The retired pkginfos are **_deleted_** from the NAS, on Cyril's approval (2026-09-13). Verified
      in both directions: each NAS file's sha256 matched its committed pre-image exactly before
      removal, and after removal both are **absent on the NAS and return HTTP 404**. `check` now
      reports `drift: missing on the target 0, only on the target 0, differing 0, unreadable 0` and
      `no integrity findings` — exit 0.
- [ ] The two payloads those pkginfos referenced are still on the NAS, referenced by nothing:
      `pkgs/apps/firefox/Firefox-155.0.1.dmg` (159,394,794 bytes) and
      `pkgs/apps/Google/GoogleChrome-153.0.8010.37.pkg` (263,986,305 bytes) — ~423 MB between them.
      Cyril approved deleting the pkginfos, not the payloads, so they stay until that is decided.
      Nothing references them, so they affect neither clients nor the catalogs.
- [ ] Deferred vendor suites are removed from `site_default`'s optional list and appear in no manifest section.
- [ ] The staged-but-unmanaged nested `apps` area is resolved: each item is either fully imported into the standard layout or withdrawn, and the decision for each is recorded.
- [ ] All pkginfos follow one declared extension convention, and the nested directories no longer split the repository's layout.
- [ ] The stale, empty NAS share that shadows the repository's name is removed so it cannot be mistaken for the repository.
- [ ] After cleanup the drift check reports clean, both catalogs build, and every manifest's items
      resolve with an existing payload. **Partially satisfied today:** the drift check reports clean
      and reports no integrity findings (2026-09-13), but "after cleanup" means after the deferred
      suites, the nested `apps` area, the extension convention and the stale share are dealt with —
      none of which is done, so this stays open.
