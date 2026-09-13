# 01: Import the live repository metadata into Git

**What to build:** The repository's editable metadata — pkginfos (including the nested `apps`
area and its `.plist` extension), manifests, and icons — captured verbatim from the live NAS
repository into this Git repository, with a recorded checksum for every file, so that the checkout
is provably byte-identical to what the NAS serves today.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

**Notes:** Import only. Do not rename extensions, do not dedupe, do not normalise. Whatever is
wrong in the live tree is preserved here so later tickets can prove they fixed it; ticket 09 owns
the cleanup.

## Acceptance criteria

- [x] The live repository's pkginfos, manifests and icons are all present in the checkout — count
      and per-file checksums recorded in the ticket.
- [x] The nested `apps`-area pkginfos and the deeper nested directories are captured, with their
      `.plist` extensions preserved as found. *(Criterion as written said "9 nested pkginfos and 4
      deeper directories"; the captured reality is **11** nested `.plist` pkginfos across **5**
      directories — `apps/` plus 4 subdirectories. See Corrections.)*
- [x] A checksum comparison of the checkout against the NAS reports zero differences for every
      metadata file.
- [x] A file-count reconciliation is recorded for each directory: pkginfos, manifests, icons —
      expected vs captured.
- [x] No payload, credential, or file above 1 MB is committed.
- [x] The live-state summary in the specification is confirmed or corrected against what was
      captured, and any correction is written back to the specification.

## Evidence (2026-09-13)

**Transfer.** `rsync -rltz --no-perms --no-owner --no-group -e "ssh -o BatchMode=yes"` from the
`t6-nas` SSH alias (port 2222), one call per directory, source
`/share/ZFS23_DATA/Web/MunkiRepo/{pkgsinfo,manifests,icons}/`. File modes were then normalised to
directories `0755` / files `0644`: the NAS carries mixed modes (`0770`, `0644`) and Git records the
executable bit, which would have marked every NAS-written icon and pkginfo executable. This is a
permission-bit change only — every file's **content bytes are unchanged**, which the checksum
comparison below proves independently.

**Reconciliation — expected (NAS, counted recursively) vs captured (checkout):**

| Directory | NAS | Checkout | Match |
|---|---|---|---|
| `pkgsinfo/` (recursive) | 38 | 38 | ✅ |
| — `pkgsinfo/` top level (`.pkginfo`) | 27 | 27 | ✅ |
| — `pkgsinfo/apps/` (`.plist`) | 6 | 6 | ✅ |
| — `pkgsinfo/apps/firefox/` | 2 | 2 | ✅ |
| — `pkgsinfo/apps/Google/` | 1 | 1 | ✅ |
| — `pkgsinfo/apps/VLC/` | 1 | 1 | ✅ |
| — `pkgsinfo/apps/Dropbox/` | 1 | 1 | ✅ |
| `manifests/` | 28 | 28 | ✅ |
| `icons/` | 37 | 37 | ✅ |
| **Total** | **103** | **103** | ✅ |

Extension census as captured: 27 `.pkginfo`, 11 `.plist` (10 in `pkgsinfo`, plus
`icons/_icon_hashes.plist`), 36 `.png`, 28 manifest files with no extension.

**Checksum verification.** Every file was hashed on both sides — `sha256sum` on the NAS,
SHA-256 of file contents in the checkout — with null-delimited path handling because one manifest
filename contains a space (`manifests/303B iMac`).

- Files hashed: NAS 103, checkout 103
- Missing from checkout: none
- Extra in checkout: none
- Hash mismatches: none
- **Result: zero differences.** The checkout is byte-identical to the live NAS metadata tree.
- Metadata tree hash (SHA-256 over the sorted `path<TAB>content-hash` lines):
  `f69da4994a2492eda4682c2b03a85da69e18650707c9b4c76b5d513aea8d6c59`

**Per-file checksums:** `docs/evidence/01-metadata-tree-checksums.tsv` (103 rows:
`sha256<TAB>size_bytes<TAB>path`), committed alongside this ticket.

**Size check.** No file exceeds 1 MB. Total metadata 3,829,269 bytes; largest file
`icons/FrameioDrive.png` at 273,144 bytes; smallest `manifests/202-Mac-Pro-3` at 358 bytes. No
payloads (`pkgs/`) committed — those stay on the NAS per ADR 0001. No credentials: the tree was
scanned for token/password/key patterns before pushing, with no matches.

**Criterion 6.** The specification's recorded live state was re-checked against what was captured.
One number was wrong and is corrected in `docs/specs/munki-fleet-spec-v1.md` (nested pkginfo
count); the rest — repository path, 38 catalog entries over 36 unique names, 28 manifest files, 16
machine manifests matching the role matrix, 36 icons plus `_icon_hashes.plist`, duplicate
name+version entries for two browsers, 13 GB of payloads, tooling versions — matched.

## Corrections recorded during the import

1. **Nested pkginfo count:** 11, not 9. Six `.plist` pkginfos sit at `pkgsinfo/apps/` top level and
   five more in the four subdirectories (`firefox/` 2, `Google/` 1, `VLC/` 1, `Dropbox/` 1).
2. **The duplicate Firefox catalog entry is not a stray file.** `apps/firefox/Firefox-155.0.1.plist`
   and `apps/firefox/Firefox-155.0.1__1.plist` are two complete pkginfos for the same name and
   version, pointing at different installer items — a `.dmg` (hash `ab75b7c9…`) and a `.pkg`
   (hash `d2379ea8…`). GoogleChrome's duplicate is the same pattern across directories:
   `apps/GoogleChrome-153.0.8010.37.plist` (`.dmg`) and
   `apps/Google/GoogleChrome-153.0.8010.37.plist` (`.pkg`). Both duplicates are therefore
   *deliberate-looking* staged alternatives with no recorded decision between them — ticket 09's
   problem, and it needs a decision rather than a delete.
3. **`makecatalogs` publishes all of them.** These nested `.plist` files are why the catalog holds
   entries whose pkginfos are invisible to anyone reading only the top level of `pkgsinfo/`.

## What remains for this ticket's successors

Nothing in this ticket touched the NAS, a client machine, or any payload. The mounted tree is a
copy, not a publish target (ticket 02); drift detection between this checkout and the NAS does not
exist yet (ticket 03); the inherited defects above are preserved, not fixed (ticket 09).
