# 01: Import the live repository metadata into Git

**What to build:** The repository's editable metadata — pkginfos (including the nested `apps` area and its `.plist` extension), manifests, and icons — captured verbatim from the live NAS repository into this Git repository, with a recorded checksum for every file, so that the checkout is provably byte-identical to what the NAS serves today.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

**Notes:** Import only. Do not rename extensions, do not dedupe, do not normalise. Whatever is wrong in the live tree is preserved here so later tickets can prove they fixed it; ticket 09 owns the cleanup.

## Acceptance criteria

- [ ] The live repository's pkginfos, manifests and icons are all present in the checkout — count and per-file checksums recorded in the ticket.
- [ ] The 9 nested `apps`-area pkginfos and the 4 deeper nested directories are captured, with their `.plist` extensions preserved as found.
- [ ] A checksum comparison of the checkout against the NAS reports zero differences for every metadata file.
- [ ] A file-count reconciliation is recorded for each directory: pkginfos, manifests, icons — expected vs captured.
- [ ] No payload, credential, or file above 1 MB is committed.
- [ ] The live-state summary in the specification is confirmed or corrected against what was captured, and any correction is written back to the specification.
