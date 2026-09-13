# 01: Import the live repository metadata into Git

**What to build:** The repository's editable metadata — pkginfos (including the nested `apps`
area and its `.plist` extension), manifests, and icons — captured verbatim from the live NAS
repository into this Git repository, with a recorded checksum for every file, so that the checkout
is provably byte-identical to what the NAS serves today.

**Blocked by:** None (can start immediately)

**Status:** done (2026-09-13)

**Notes:** Import only. Do not rename extensions, do not dedupe, do not normalise the tree.
**One declared exception, added after review:** file *modes* were normalised from the NAS's mixed
`0770`/`0644` to directories `0755` / files `0644`, because Git records the executable bit and
`0770` would have marked every NAS-written pkginfo and icon executable in the repository. Content
bytes were not touched — the checksum comparison below proves that independently of this note.

**Verification:** NAS-side listing and checkout listing both 103 files; diff of the two on
`sha256<TAB>path` → empty. Recomputed independently after review (recomputing the checkout hashes
from the working tree and re-running the NAS command). Commands and results under Evidence.

## Acceptance criteria

- [x] The live repository's pkginfos, manifests and icons are all present in the checkout — count
      and per-file checksums recorded in the ticket.
- [x] The 9 nested `apps`-area pkginfos and the 4 deeper nested directories are captured, with
      their `.plist` extensions preserved as found. → the criterion's numbers are wrong; every
      nested pkginfo *was* captured, but the real shape is **11 nested pkginfos across 5
      directories**. See Corrections §1; the criterion is left verbatim rather than rewritten.
- [x] A checksum comparison of the checkout against the NAS reports zero differences for every
      metadata file.
- [x] A file-count reconciliation is recorded for each directory: pkginfos, manifests, icons —
      expected vs captured.
- [x] No payload, credential, or file above 1 MB is committed.
- [x] The live-state summary in the specification is confirmed or corrected against what was
      captured, and any correction is written back to the specification.

## Evidence (2026-09-13)

**Systems involved:** the T6 NAS (`t6-nas` SSH alias, port 2222) as the source, read-only; the
admin workstation's local git checkout as the destination. No client machine and no payload was
touched.

**Transfer — command run:**

```bash
for d in pkgsinfo manifests icons; do
  rsync -rltz --no-perms --no-owner --no-group -e "ssh -o BatchMode=yes" \
    "t6-nas:/share/ZFS23_DATA/Web/MunkiRepo/$d/" "./$d/"
done
```

Returned 38 / 28 / 37 files for the three directories, no errors. `--no-perms --no-owner
--no-group` kept the NAS's mixed ownership and modes out of the local tree.

**Mode normalisation — commands run (the declared exception above):**

```bash
find ./pkgsinfo ./manifests ./icons -type d -exec chmod 755 {} +
find ./pkgsinfo ./manifests ./icons -type f -exec chmod 644 {} +
```

**NAS-side checksum listing — command run:**

```bash
ssh -o BatchMode=yes t6-nas "cd /share/ZFS23_DATA/Web/MunkiRepo && \
  find pkgsinfo manifests icons -type f -print0 | xargs -0 sha256sum"
```

Returned 103 lines. Output committed verbatim as
`docs/evidence/01-nas-metadata-tree-checksums.tsv`. `-print0`/`xargs -0` is required, not
cosmetic: `manifests/303B iMac` contains a space and a plain `xargs` invocation failed on it
(`sha256sum: 303B: No such file or directory`) — an early sign of the naming problem ticket 04 and
06 exist to resolve.

**Checkout-side checksum listing and comparison:** every file under `pkgsinfo/`, `manifests/` and
`icons/` hashed from the working tree (SHA-256 over file contents), giving 103 entries; the two
listings compared on `sha256<TAB>path` after sorting.

- Files hashed: NAS 103, checkout 103
- Missing from checkout: none · Extra in checkout: none · Hash mismatches: none
- **Result: zero differences.** The checkout is byte-identical to the live NAS metadata tree.
- Metadata tree hash (SHA-256 over the sorted `path<TAB>content-hash` lines):
  `f69da4994a2492eda4682c2b03a85da69e18650707c9b4c76b5d513aea8d6c59`
- Checkout listing with sizes: `docs/evidence/01-metadata-tree-checksums.tsv` (103 rows:
  `sha256<TAB>size_bytes<TAB>path`).

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

**Extension census as captured (recomputed after review; sums to 103):** 27 `.pkginfo` +
12 `.plist` (11 in `pkgsinfo`, 1 = `icons/_icon_hashes.plist`) + 36 `.png` + 28 manifest files with
no extension = 103. A first draft of this census mis-stated the `.plist` split and summed to 102;
the corrected figures are above, and the review finding that caught it is why this line is
recomputed rather than asserted.

**Size check — command:** every file under the three directories stat'd for size. No file exceeds
1 MB; total 3,829,269 bytes; largest `icons/FrameioDrive.png` at 273,144 bytes; smallest
`manifests/202-Mac-Pro-3` at 358 bytes. No `pkgs/` payloads are committed — they stay on the NAS
per ADR 0001.

**Secret scan — command:** a `git grep` pass over the committed tree for `t6t6t6t6t`, `password=`,
`passwd`, private-key headers, `gho_`/`ghp_`, `sk-`, `api_key`, `bot_token` and `secret=`
strategies, plus a scan for any tracked file over 1 MB. Both returned no matches before the first
push.

**Criterion 6.** The specification's recorded live state was re-checked against what was captured;
one number was wrong and is corrected in `docs/specs/munki-fleet-spec-v1.md` (nested pkginfo count,
and the `icons/` count now names `_icon_hashes.plist` explicitly). The rest — repository path, 38
catalog entries over 36 unique names, 28 manifest files, 16 machine manifests matching the role
matrix, duplicate name+version entries for two browsers, 13 GB of payloads, tooling versions —
matched. The specification remains the authority for those numbers; this ticket cites it rather
than restating it where they overlap.

## Corrections recorded during the import

1. **Nested pkginfo count: 11, not 9.** Six `.plist` pkginfos sit at `pkgsinfo/apps/` top level and
   five more in the four subdirectories (`firefox/` 2, `Google/` 1, `VLC/` 1, `Dropbox/` 1).
2. **The duplicate Firefox catalog entry is not a stray file.**
   `apps/firefox/Firefox-155.0.1.plist` and `apps/firefox/Firefox-155.0.1__1.plist` are two
   complete pkginfos for the same name and version pointing at different installer items — a `.dmg`
   (hash `ab75b7c9…`) and a `.pkg` (hash `d2379ea8…`). GoogleChrome's duplicate is the same pattern
   across directories: `apps/GoogleChrome-153.0.8010.37.plist` (`.dmg`) and
   `apps/Google/GoogleChrome-153.0.8010.37.plist` (`.pkg`). Both duplicates are therefore
   *deliberate-looking* staged alternatives with no recorded decision between them — a ticket 09
   decision, not a delete.
3. **`makecatalogs` publishes all of them.** These nested `.plist` files are why the catalog holds
   entries whose pkginfos are invisible to anyone reading only the top level of `pkgsinfo/`.

## What remains for this ticket's successors

Nothing in this ticket touched the NAS, a client machine, or any payload. This tree is a copy, not
a publish target (ticket 02); drift detection between this checkout and the NAS does not exist yet
(ticket 03); the inherited defects above are preserved, not fixed (ticket 09).
