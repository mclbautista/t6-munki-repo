# 02: Publish path tracer bullet: Git edit to a client-visible change over HTTP, with no SMB mount

**What to build:** One narrow end-to-end proof of the new administration path: change one
non-behavioural attribute of one existing pkginfo in the Git checkout, build catalogs locally,
publish over the NAS SSH path, and confirm a pilot client's check-only run reflects the change —
with the SMB mount demonstrably absent the whole time.

**Blocked by:** 01

**Status:** done (2026-09-13)

**Approval gate:** None — publishing checksum-verified metadata is autonomous (ADR 0008). The
change published was `display_name` on one pkginfo: display-only, no install semantics.

**Verification:** `python3 -m pytest` → 32 passed. Live: three files published and verified over
both filesystem and HTTP; pilot check-only run on `202-TOC-M4-Max` resolved its own manifest,
processed the changed item from `catalog testing` and installed nothing; the pre-images were then
restored and the original served checksums confirmed.

## Acceptance criteria

- [x] The SMB mount to the NAS Web share is confirmed absent before, during and after the run; the
      evidence is recorded.
- [x] The change is made only in the Git checkout — no file is edited on the NAS by hand.
- [x] `makecatalogs` runs against the checkout and produces the catalogs without error.
- [x] Publishing transfers metadata and catalogs over the NAS SSH path, writes to temporary names,
      verifies checksums, then renames into place — no partial file is ever visible to a client.
- [x] The changed attribute is verifiably served: the served artifact's checksum matches the
      checkout's.
- [x] A pilot machine run in check-only mode reports the item, with the resolved manifest name and
      clean result recorded against the machine's name.
- [x] Reverting the change restores the original served checksum, recorded as a second run.

## What was built

Two modules and a CLI, with the publish invariants held by tests rather than by care:

- **`munki_fleet/targets.py`** — the seam that makes the path testable: `LocalDirTarget` (tests,
  dry runs) and `SshTarget` (the NAS, over the `t6-nas` alias). `write_atomic` uploads to a
  temporary name, reads the checksum back, and only then renames; on any mismatch it removes the
  temporary file and leaves the destination untouched. SSH connections are multiplexed
  (`ControlMaster`/`ControlPersist`), because a publish stats ~200 paths.
- **`munki_fleet/catalogs.py`** — `build_catalogs` runs `makecatalogs --skip-pkg-check` against the
  checkout (payload existence is the integrity check's job against the published tree, ticket 03),
  and `compare_catalogs` diffs two catalogs item by item.
- **`munki_fleet/publish.py`** — `publish` (temp name → verify → rename, optional pre-image
  capture) and `verify_served`.
- **`munki_fleet/gate.py`** + `munki_fleet/cli.py` — the pre-publish gate (see below).

`catalogs/` is a build output and is gitignored: the metadata tree stays `pkgsinfo/`, `manifests/`,
`icons/`.

## The gate exists because of what happened in this ticket

The first publish carried an **unintended** second change (details under Findings). It got through
because the tool then offered `--allow-changes`, a bare bypass, and I passed it without reading the
diff first. That flag is gone. It is replaced by a declaration:

- `--expect-change <Item>:<key>` (repeatable) states what the publish intends to change; the gate
  refuses any undeclared change **and** refuses a declared change that did not happen.
- `--expect-new-catalog <name>` is required for a catalog that does not exist on the target.
- A **duplicate-name entry reordering** blocks by default and needs
  `--allow-duplicate-order-change`, because Munki takes the first entry matching a name — so an
  order swap changes which installer a client receives while looking like a no-op.

Refusal is exercised in the live run (exit 3, reason naming the item and the remedy), not only in
tests.

## Evidence (2026-09-13)

**Criterion 1 — mount absent throughout:** `mount | grep -ci smb` → 0 and
`ls -A /Users/t6/Mnt/Web` → 0 entries, checked before the run and again after the restore. The
`/etc/fstab` entry still carries no credentials, which is why it cannot mount headless.

**Criteria 2–5 — the publish, with the mount absent:**

| Step | Result |
|---|---|
| Intended change | `display_name` added to the `iTerm2` pkginfo — 2 added lines, `plutil -lint` OK |
| Build | `makecatalogs 7.3.0.5808 --skip-pkg-check .` → `catalogs/all` and `catalogs/testing`, 60,149 bytes each |
| Gate (declared change only) | **REFUSED**, exit 3: undeclared duplicate-name order change for Firefox |
| Gate (declared change + accepted risk) | allowed, risk printed as taken |
| Publish | written 3, unchanged 102, skipped 0, pre-images kept for all 3 |
| Filesystem verify | matching 105, mismatching 0, missing 0 |
| Served vs checkout (HTTP) | `catalogs/all` `d023c41256120047`, `catalogs/testing` `d023c41256120047`, `pkgsinfo/iTerm2-3.7.1.pkginfo` `e7f6aff874c7ab29` — all equal to the checkout |
| Temp files after | `find … -name '*.tmp'` → 0 |

**Criterion 6 — pilot check-only:** machine `202-TOC-M4-Max` (192.168.88.182), Munki 7.3.0.5808,
`sudo /usr/local/munki/managedsoftwareupdate --checkonly -vv`, exit 0.

- Resolved manifest: **`202-TOC-M4-Max`**, chain `toc → all → site_default` (report `ManifestName`
  agrees), `RunType` custom.
- **The changed item was consumed from the catalog:** line 215 processes `iTerm2 for install`,
  line 217 `Considering 1 items with name iTerm2 from catalog testing`, line 218
  `Considering item iTerm2, version 3.7.1`.
- Nothing installed: the run lists `+ GoogleChrome-153.0.8010.37` as the only pending item and
  says to run `--installonly`; it ends `Done.`
- Key lines committed at `docs/evidence/02-pilot-checkonly-excerpt.log`; the full 605-line log is
  605 lines with sha256 `0b5bdf43a0dd6538…` and is held in the gitignored evidence store.
- Warnings were limited to the pre-existing `IBMAsperaConnect` x86_64 rejection plus Munki's
  misleading "No pkginfo found" follow-up — an existing defect, not a result of this change.

**Criterion 7 — revert restored the original bytes:** the checkout was restored to `HEAD`
(the intended-change patch is kept at `…/evidence/02/intended-change.patch`), the pre-images were
re-published, and both the filesystem and HTTP serve the original
`catalogs/all` `catalogs/testing` `fabda778b3f6bd42` and `pkgsinfo/iTerm2-3.7.1.pkginfo`
`23c70bf5d89dd6ad`. The checkout now equals what the fleet is served.

## Findings (escalated, not fixed here)

1. **The repository's duplicate entries make a catalog rebuild change client behaviour.** The
   live repository carries two complete pkginfos for Firefox 155.0.1 (`.dmg`, `copy_from_dmg`) and
   two for GoogleChrome 153.0.8010.37. Building with **6.6.0** (what the NAS catalog was made
   with) writes the Firefox pair as `[.pkg, .dmg]`; building with **7.3.0** writes `[.dmg, .pkg]`.
   Munki takes the first entry matching a name, so the fleet's Firefox installer would flip from
   the `.pkg` to the `.dmg` on the first publish from the newer toolchain. GoogleChrome's order is
   the same under both versions.
2. **The 7.3.0 build is otherwise reproducible:** two independent builds in separate copies of the
   metadata tree produced byte-identical catalogs (`d023c412…`), so this is a tool-version
   difference, not build-to-build randomness.
3. **Consequence — routine publishing is blocked until the duplicate is resolved.** Because the
   fleet has been restored to the 6.6.0-built catalogs, every future publish from the local 7.3.0
   toolchain trips the gate's duplicate-order check. The gate is right to block: the change it is
   blocking is real. Resolving it is ticket 09 (which of the two Firefox pkginfos survives is
   Cyril's decision, and it is a deletion), or ticket 10 if the toolchain is aligned instead.
4. **`makecatalogs` rewrites the tracked `icons/_icon_hashes.plist`.** After a 7.3.0 rebuild it is
   byte-identical to the copy imported under ticket 01, so the file is stable across both tool
   versions and safe to keep tracked — but a future tool version could change it silently.
5. **The publish tool has no `--dry-run`-visible plan for the whole tree yet:** it reports
   catalogs, and reports written/unchanged/skipped, but does not yet print which non-catalog files
   would change. Ticket 03's drift check is where the full picture belongs.

## What this ticket does not do

No promotion, no manifest or policy change, and no client install ran. The fleet is served exactly
the bytes it was served before the ticket started. Ticket 03 (drift and integrity) and the
duplicate resolution still stand between this tracer bullet and routine publishing.
