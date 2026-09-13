# 02: Publish path tracer bullet: Git edit to a client-visible change over HTTP, with no SMB mount

**What to build:** One narrow end-to-end proof of the new administration path: change one
non-behavioural attribute of one existing pkginfo in the Git checkout, build catalogs locally,
publish over the NAS SSH path, and confirm a pilot client's check-only run reflects the change —
with the SMB mount demonstrably absent the whole time.

**Blocked by:** 01

**Status:** done (2026-09-13)

**Approval gate:** None for the publish itself — publishing checksum-verified metadata is autonomous
(ADR 0008) **when the pre-publish gate passes** (ADR 0009). The published change was `display_name`
on one pkginfo: display-only, no install semantics.

**Verification:** `python3 -m pytest` → **51 passed**. Live: three files published and verified over
both filesystem and HTTP; pilot check-only run on `202-TOC-M4-Max` resolved its own manifest,
processed the changed item from `catalog testing` and installed nothing; the pre-images were then
restored and the original served checksums confirmed over filesystem and HTTP.

## Acceptance criteria

- [x] The SMB mount to the NAS Web share is confirmed absent before, during and after the run; the
      evidence is recorded. → **`docs/evidence/02-mount-absent.txt`.** Honest scope: checks were run
      at the start and at the end; there is no discrete *during* artifact. What bounds the window is
      that nothing in this ticket mounts anything — `grep -rniE mount munki_fleet/` returns no
      matches at all, and the mount point was empty at both ends.
- [x] The change is made only in the Git checkout — no file is edited on the NAS by hand.
- [x] `makecatalogs` runs against the checkout and produces the catalogs without error.
- [x] Publishing transfers metadata and catalogs over the NAS SSH path, writes to temporary names,
      verifies checksums, then renames into place — no partial file is ever visible to a client.
      **Strengthened after review:** the plan is validated before anything is written, and a failure
      part-way rolls back what this publish already wrote, so a failed publish is not a partial
      publish either.
- [x] The changed attribute is verifiably served: the served artifact's checksum matches the
      checkout's. → `docs/evidence/02-publish-and-restore.txt`
- [x] A pilot machine run in check-only mode reports the item, with the resolved manifest name and
      clean result recorded against the machine's name. → `docs/evidence/02-pilot-checkonly-excerpt.log`
- [x] Reverting the change restores the original served checksum, recorded as a second run.

## What was built

The first code in this repository, and the reason this ticket's scope is wider than its title.

**The publish path** (`munki_fleet/`):

- `targets.py` — a `Target` seam with one shared `write_atomic`: put bytes at a hash-derived
  temporary name, read that back comparing hash *and* size, then replace the destination; on any
  mismatch remove the temporary file and leave the destination untouched. `LocalDirTarget` (tests,
  dry runs, pre-image capture) and `SshTarget` (the NAS over the `t6-nas` alias, SSH connections
  multiplexed because a publish stats ~200 paths) implement only the transport primitives.
- `catalogs.py` — `build_catalogs` runs `makecatalogs --skip-pkg-check` against the checkout;
  `compare_catalogs` diffs two catalogs item by item, treating a duplicate-name **reordering** as
  its own finding rather than a dozen changed keys.
- `publish.py` — `publish` (pre-flight, temp-verify-rename, optional pre-image capture) and
  `verify_served`. A failure after anything has been written raises `PublishAborted` carrying the
  report, so the rollback outcome is never lost.
- `gate.py` + `cli.py` — the pre-publish gate and its command line.

`catalogs/` is generated and gitignored; the metadata tree stays `pkgsinfo/`, `manifests/`, `icons/`.

## The gate exists because of what happened in this ticket

The first live publish carried an **unintended** second change, because the tool then offered
`--allow-changes` — a bare bypass — and I passed it without reading the diff first. That flag is
gone. The decision is recorded as **ADR 0009**, and the replacement is a declaration:

| Change class | Declaration |
|---|---|
| item key changed | `--expect-change ITEM:KEY` (or `ITEM:*`) |
| item added / removed | `--expect-add`, `--expect-remove` |
| duplicate-name entry reordered | blocks by default; `--allow-duplicate-order-change` accepts it loudly |
| any non-catalog file changed | `--expect-file PATH` |

A declaration that does not come true is also refused, and an unreadable target file is refused
rather than treated as absent. Refusal was exercised against the live repository, not only in tests
(`docs/evidence/02-dryrun-gate.txt`).

## Findings (escalated, not fixed here)

1. **The duplicate entries make a catalog rebuild change client behaviour.** Two complete pkginfos
   exist for Firefox 155.0.1 (`.dmg` `copy_from_dmg`, `.pkg` with a receipt) and two for
   GoogleChrome 153.0.8010.37. `makecatalogs` **6.6.0** writes the Firefox pair as `[.pkg, .dmg]`;
   **7.3.0** writes `[.dmg, .pkg]`. Munki takes the first entry matching a name, so the fleet's
   Firefox installer flips on the first publish from the newer toolchain. GoogleChrome's order is
   unaffected.
2. **Both builds are individually reproducible** — two independent 7.3.0 builds in separate copies
   of the metadata tree produced byte-identical catalogs. This is a tool-version difference, not
   build-to-build randomness.
3. **Routine publishing is blocked until the duplicate is resolved.** A fresh build of the current
   checkout differs from what the fleet is served in **exactly one way**: the Firefox entry order.
   There are no item-level changes at all. So the checkout cannot currently reproduce the served
   catalogs byte for byte — the tracked metadata matches, the generated catalogs cannot — and every
   publish from this toolchain needs the order change accepted explicitly. The gate is right to
   block it. Resolving it is ticket 09 (which Firefox pkginfo survives is Cyril's decision, and it
   is a deletion), or ticket 10 if the toolchain is aligned first.
4. **`makecatalogs` rewrites the tracked `icons/_icon_hashes.plist`.** After a 7.3.0 rebuild it is
   byte-identical to the copy imported under ticket 01, so it is stable across both tool versions
   and safe to keep tracked — but a future tool version could change it silently.

## Review findings closed (two-axis review of the first version of this commit)

Both axes ran against the first implementation; every finding was either fixed or answered:

- **The gate did not gate membership.** `_observed_changes` read only changed keys, so an added or
  removed item published silently — the spec's "a build that changes membership unexpectedly is
  reported before publish" invariant was not held. Now `--expect-add` / `--expect-remove`, with
  tests for undeclared, declared, and declared-but-absent cases.
- **A manifest edit produced no catalog diff and published undeclared.** Now a file-level check:
  an undeclared changed file is refused, an unreadable one is refused even when declared.
- **A failure part-way was a partial publish.** Now pre-flight validation plus rollback, asserted by
  tests that check the earlier file is restored and a newly created file is removed.
- **`SshTarget` had no tests, and the CLI was untested**, so the gate could have been unwired while
  32 tests stayed green. The remote target now takes an injected command runner and the CLI takes
  its target and catalog runner as dependencies; there are tests for the SSH write sequence, its
  failure paths, path quoting, a refusal that must publish nothing, and a dry run.
- **Dead and malformed code** (`_items_by_name`, the unused `has_item_changes`, the never-false
  `skip_pkg_check` parameter) removed; **the production test hook** `corrupt_on_write` replaced by
  test-side doubles.
- **The CLI docstring still advertised the deleted `--allow-changes` flag** — exactly the failure
  mode this commit exists to close. Rewritten.
- **Spec interface drift** (`DriftReport`, `CatalogSet`, `Gap`): the specification now records the
  signatures as shipped, and gains the gate as a module.
- **Duplicated test helpers** moved to `conftest.py`.
- **A false claim** ("the checkout now equals what the fleet is served") is corrected in
  Findings 3: the *tracked metadata* matches; the *generated catalogs* cannot, and why.

## What this ticket does not do

No promotion, no manifest or policy change, and no client install ran. The fleet is served exactly
the bytes it was served before the ticket started. Ticket 03 (drift and integrity) and the duplicate
resolution stand between this tracer bullet and routine publishing.
