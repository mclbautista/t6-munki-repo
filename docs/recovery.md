# Recovery: what to do when something in the repository is lost

Written to be followed under pressure. Commands marked **(exercised)** were run in the drill
recorded in `docs/evidence/12-drill-2026-09-13.txt`; the rest are the documented procedure and have
not been run yet. The snapshot path is marked unavailable, because no snapshot schedule exists on
the NAS — by decision (Cyril, 2026-09-13), not by omission.

## What exists where

| what | where | protected by |
|---|---|---|
| Metadata (manifests, pkginfos, scripts, icons) | the checkout on the admin workstation, and the private GitHub remote `mclbautista/t6-munki-repo` | Git history, and a copy on a second device |
| The **served** copy clients read | `/share/ZFS23_DATA/Web/MunkiRepo/` on the NAS (`192.168.88.188`), over the `t6-nas` SSH alias | nothing yet — no snapshots |
| Catalogs (`all`, `testing`) | generated, not in Git: in the checkout and on the NAS | regenerable from the metadata **where the payloads are visible** |
| Payloads (10.76 GB) | the served tree on the NAS, **plus** a copy of the 9 that cannot be re-acquired in `~/munki-offnas-copy/` on the admin workstation (8.4 GB, sha256-verified) | for those 9, the copy is the second device; the other 20 are re-fetchable by decision |

Two facts that decide how you restore:

1. **Payloads are not in Git**, and the catalog build must not be run bare: `makecatalogs`
   **skips every item whose `installer_item_location` is absent**, one warning per item, and exits
   0 with an empty catalog. Always pass `--skip-pkg-check` (which is what
   `munki_fleet.catalogs.build_catalogs` does). Get this wrong during a restore and you publish an
   empty catalog: every client then sees no items at all.
2. **The served tree is what matters to clients.** Restoring a file into the checkout changes
   nothing until it is published to the NAS path above.

## One file was deleted or corrupted (the common case)

Metadata file, in the checkout:

```bash
cd <checkout>
git log --oneline -- <path>            # find the last commit where it was right
git checkout <good-commit> -- <path>   # (exercised) restore just that file
plutil -lint <path>                    # (exercised) a plist must parse before it is published

# publish it with the repository's publish path — SCP/SFTP is refused for the NAS SSH user, so
# `scp` cannot work here. Declare the change: the pre-publish gate refuses one it was not told
# about (ADR 0009).
python3 -m munki_fleet.cli publish --target t6-nas:/share/ZFS23_DATA/Web/MunkiRepo \
    --metadata-root . --backup-dir /tmp/pre-images <path>
```

Then rebuild and publish the catalogs, because a manifest or pkginfo change the catalog does not
reflect is invisible to clients:

```bash
python3 -m munki_fleet.cli build --metadata-root .        # makecatalogs --skip-pkg-check
```

A payload file, in the served tree:

- **Re-fetchable items** (20 of 28, 1.92 GB): download the same version from the vendor again and
  replace it. Check the new file's sha256 against the pkginfo's `installer_item_hash`; if it
  differs, re-import the item with `munkiimport` rather than hand-placing the file.
- **Account-gated items** (7, 8.74 GB — Resolve Studio and Project Server, Aspera, LucidLink,
  Soundly, Frame.io Drive, Apple Remote Desktop): re-downloading needs the vendor account still to be
  valid. A copy off the NAS exists at `~/munki-offnas-copy/` on the admin workstation, sha256-checked
  against each pkginfo, so a lapsed account no longer loses them.
- **Non-reproducible items** (1, 0.10 GB — `CineCred-0.0.pkg`, packaged in house): no upstream copy
  exists. A copy off the NAS exists at `~/munki-offnas-copy/` on the admin workstation; if both the
  NAS and that machine are gone, the item is gone.
- Per-item detail, with the reason for each: `docs/evidence/12-payload-classification-2026-09-13.tsv`.

## The whole metadata is gone

```bash
git clone https://github.com/mclbautista/t6-munki-repo.git /path/to/checkout   # (exercised)
cd /path/to/checkout && /usr/local/munki/makecatalogs --skip-pkg-check .       # (exercised)
```

Then publish the tree to the NAS path and verify (below). The drill shows this restores the
metadata exactly: same items, same payload hashes as the served catalog.

## The NAS served tree is lost or corrupted

1. **Snapshots first, once they exist** (Storage & Snapshots on the NAS): restore the share from the
   most recent snapshot. This is the *only* path that recovers payloads without the vendors.
2. If there is no snapshot: recreate the served tree from the checkout (metadata) and re-fetch
   payloads per the classification artifact. Expect to lose the non-reproducible item and any
   account-gated item whose account has lapsed.

## Verify after any restore

```bash
plutil -lint manifests/* pkgsinfo/*                          # everything parses
/usr/local/munki/makecatalogs --skip-pkg-check .             # NOT bare: see rule 1 above
python3 -c "import plistlib;print(len(plistlib.load(open('catalogs/all','rb'))))"   # not zero!
# compare the rebuilt catalog with the served one: same items, same installer_item_hash
ssh -n t6-nas 'cd /share/ZFS23_DATA/Web/MunkiRepo && find pkgs -type f -exec sha256sum {} \;'
```

The last command takes about 50 seconds and is how payload integrity is checked: every hash must
equal the `installer_item_hash` in its pkginfo. 28 of 28 did on 2026-09-13.

## What is not protected today

- **Payloads**: the 9 that cannot be re-acquired have a second copy on the admin workstation,
  which this ticket does not itself back up — a NAS failure is survivable, both failing is not. The
  other 20 rest on the vendors, by recorded decision. The classification artifact sizes both.
- **Snapshots**: none on the repository volume — **by decision, not by omission** (Cyril,
  2026-09-13: "I don't want to enable snapshotting on the NAS"). There is therefore no
  point-in-time recovery of the served tree: a bad import or a wrong delete is recovered from the
  Git history for the metadata, and from the off-NAS copy for the payloads listed above, and not
  otherwise. The revisit trigger is a second copy target existing, or a payload whose
  re-acquisition turns out to be impossible.
- ARD's machine-alias list and other live-machine state: not repository data, out of scope here.
