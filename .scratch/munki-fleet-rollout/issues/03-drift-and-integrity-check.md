# 03: Detect drift and integrity gaps instead of discovering them

**What to build:** A check that answers "is the NAS serving exactly what Git says it should, and can
every item in every manifest actually be installed?" — reporting differences and missing payloads as
classified findings rather than as a silent state.

**Blocked by:** 02

**Status:** done (2026-09-13)

**Notes:** Detection and reporting only. This ticket does not repair drift — repairing from Git is
the documented direction (ADR 0001) and is performed deliberately. Alert delivery is ticket 15.

**Verification:** `python3 -m pytest` → **76 passed, 0 failed** (counts as measured, not recalled —
the previous commit of this ticket claimed 80, which was wrong). Live read-only run against the real
repository: exit 1 with exactly two findings, in ~6 seconds. Raw output committed at
`docs/evidence/03-check-live-raw.txt`.

## Acceptance criteria

- [x] A drift report classifies, separately: files present in the checkout but missing on the NAS,
      files present on the NAS but not in the checkout, and files present in both with differing
      checksums.
- [x] An in-sync repository reports clean, and the clean case is asserted by a test, not by
      inspection.
- [x] Every item reachable in any machine manifest's catalog chain is checked for an existing
      payload and an existing pkginfo; missing ones are listed with the manifest that references
      them. Findings carry the referencing manifest name, and the live run found none missing.
- [x] Catalog membership is checked against each pkginfo's declared catalog, so an item declaring
      `testing` while a production-only manifest references it is reported.
- [x] The check exits non-zero on any finding. Measured without a pipe: `exit=1`. It needs no
      **interactive** credential — it uses the existing key-based `t6-nas` SSH alias, which is the
      same access the publish path already has.
- [x] All of the above are exercised against fixtures by tests that never touch the live NAS.

## What it found on the real repository

- **No payload is missing, and no pkginfo is missing.** Every item any machine manifest offers
  resolves to a pkginfo and to payloads that exist on the NAS. (Stated precisely after review: this
  now includes the pkginfo half of the check and every payload location of a duplicate-named item;
  before the review it did not.) This had never been checkable before.
- **Catalog membership is consistent**, and **no manifest chain is broken**.
- **Drift is exactly one file**: `pkgsinfo/apps/firefox/Firefox-155.0.1.plist`, the Firefox duplicate
  retired in ticket 09 on Cyril's decision. It left the checkout, so the publish did not remove it
  from the NAS — and it is still served (HTTP 200). Reconciling it is a deletion on the NAS and
  needs approval; it is left deliberately so that deletion happens through this detecting path
  rather than by hand.
- **The remaining real defect is the GoogleChrome duplicate**, which carries the same ordering
  hazard the Firefox pair did. Its order happens to match under 6.6.0 and 7.3.0 today; nothing
  guarantees that.

## Two faults this ticket found and fixed

1. **Payload existence was asking for a hash.** The first live run timed out on the 6.87 GB DaVinci
   Resolve payload. The target gained `exists()` — is the path there, without reading it — and the
   run went from a 60-second timeout to 5.7 seconds. A test asserts payload checks issue no
   `sha256sum`.
2. **A published filename with a space broke HTTP verification.** `manifests/303B iMac` produced
   `URL can't contain control characters`; URLs are now percent-encoded by one shared helper, and
   `verify` reports 104/104 over HTTP.

## Review findings closed (two-axis review of the first version of this commit)

- **The "existing pkginfo" half was not built.** The criterion asks that every referenced item is
  checked for an existing payload **and an existing pkginfo**; the code read a name→location map and
  `continue`d when the name was absent, so an item referenced by a manifest and served by a catalog
  but with no pkginfo in the checkout produced **no finding at all** — a fixture proved it returned
  clean. Now reported as `pkginfo_missing`, carrying the manifest that wants it, with a test.
- **Three manifest sections were not followed.** `default_installs`, `forced_installs` and
  `conditional_items` can each reference an item, so "every item reachable in any machine manifest"
  was false in general. All are followed now, conditional items included, with tests.
- **Only one payload per name was checked.** `item_locations` used first-wins, and the repository
  has two pkginfos for GoogleChrome, so one of its two installer items was never verified — which
  made the "no payload is missing" claim broader than the check. It now returns every location and
  checks all of them; a test removes one of a duplicate pair's payloads and asserts it is caught.
- **A failed read was reported as absent.** Drift now classifies a target file it cannot read as
  `unreadable`, and the report is not `ok` — the ADR 0009 fail-closed principle, with a test.
- **Membership was judged against an untracked build.** Integrity read catalogs from the checkout,
  so "membership is consistent" described something clients do not receive. It now reads the
  **served** catalogs from the target and says which source it used (`membership checked against the
  served catalogs` in the live output); with an empty target it falls back to the build and says so.
- **A stale served entry was skipped.** An entry in a served catalog with no pkginfo in the checkout
  was silently dropped; it is now `catalog_entry_without_pkginfo`.
- **An unreadable catalog was skipped**, so integrity could report clean on a catalog it could not
  parse. It is now `catalog_unreadable`, and `_load_items` and `compare_catalogs` are reused instead
  of a fourth re-implementation of parsing and duplicate detection.
- **`check` had no test at all**, and a field rename in this same commit crashed it
  (`AttributeError: 'DriftReport' object has no attribute 'missing_in_checkout'`) — caught only when
  the live run was re-executed. Two CLI tests now cover `check`: one asserting a finding and a
  non-zero exit, one asserting a clean report.
- **Duplicated listing logic removed.** `drift()` had a local branch re-implementing the checkout
  listing and `LocalDirTarget`; the target is now read only through its own interface, so one code
  path covers a local directory and the NAS.
- **Unused parameters removed** (`integrity(..., catalogs_dir=)`), and `missing_in_checkout` renamed
  to `only_on_target` because that is what it means.
- Considered and deliberately not changed: the four duplicate-related fields on `CatalogDiff` are
  each read independently by the gate (names, order, resolved, gained) and grouping them would
  churn the gate and its tests for no behavioural gain. Recorded here rather than left silent.

## Design notes

- **Drift and integrity are separate questions** held in one module: drift is about the target
  matching the checkout, integrity is about whether an install would work. They fail for different
  reasons and are reported separately, even though one command runs both.
- **Machine manifests are identified as the manifests nothing else includes**, not by their shape.
  A shape-based filter silently skipped chains whose root declares no catalogs of its own, which is
  how the first version of this check missed the fixture that should have failed.
- **Reading the target goes through the same `Target` seam** as publishing, so the drift check is
  tested against the fake SSH shell without a network.
- Drift covers `pkgsinfo`, `manifests`, `icons` and `catalogs`. Payloads are excluded from drift
  deliberately: hashing 13 GB on every run is not the point, and payload existence is integrity's
  question, answered without reading the file.
