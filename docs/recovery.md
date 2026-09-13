# Recovery: what to do when something in the repository is lost

Written to be followed under pressure. Every command here has been exercised in the drill recorded
in `docs/evidence/12-drill-2026-09-13.txt` — except the snapshot path, which is marked as not yet
available, because no snapshot schedule exists on the NAS yet (ticket 12, criterion 1).

## What exists where

| what | where | protected by |
|---|---|---|
| Metadata (manifests, pkginfos, scripts, icons) | the checkout on the admin workstation, and the private GitHub remote `mclbautista/t6-munki-repo` | Git history, and a copy on a second device |
| The **served** copy clients read | `/share/ZFS23_DATA/Web/MunkiRepo/` on the NAS (`192.168.88.188`), over the `t6-nas` SSH alias | nothing yet — no snapshots |
| Catalogs (`all`, `testing`) | generated, not in Git: in the checkout and on the NAS | regenerable from the metadata **where the payloads are visible** |
| Payloads (10.76 GB) | **only** `/share/ZFS23_DATA/Web/MunkiRepo/pkgs/` on the NAS | nothing yet; see the classification artifact |

Two facts that decide how you restore:

1. **Payloads are not in Git.** A metadata restore alone cannot rebuild catalogs: `makecatalogs`
   drops every item whose payload is missing (it warns per item). Rebuild where both are visible.
2. **The served tree is what matters to clients.** Restoring a file into the checkout changes
   nothing until it is published to the NAS path above.

## One file was deleted or corrupted (the common case)

Metadata file, in the checkout:

```bash
cd <checkout>
git log --oneline -- <path>            # find the last commit where it was right
git checkout <good-commit> -- <path>   # restore just that file
plutil -lint <path>                    # a plist must parse before it is published
scp <path> t6-nas:/share/ZFS23_DATA/Web/MunkiRepo/<path>   # publish just that file
```

Then rebuild and publish the catalogs **on a machine where the payloads are visible** (see below),
because a manifest or pkginfo change the catalog does not reflect is invisible to clients.

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
git clone https://github.com/mclbautista/t6-munki-repo.git /path/to/checkout   # private remote
cd /path/to/checkout && mkdir -p catalogs && /usr/local/munki/makecatalogs .   # where payloads are visible
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
plutil -lint manifests/* pkgsinfo/*                 # everything parses
/usr/local/munki/makecatalogs .                     # rebuild without warnings
# compare the rebuilt catalog with the served one: same items, same installer_item_hash
ssh t6-nas 'cd /share/ZFS23_DATA/Web/MunkiRepo && find pkgs -type f -exec sha256sum {} \;'
```

The last command takes about 50 seconds and is how payload integrity is checked: every hash must
equal the `installer_item_hash` in its pkginfo. 28 of 28 did on 2026-09-13.

## What is not protected today

- **Payloads**: one NAS volume, no off-NAS copy. The classification artifact sizes the problem.
- **Snapshots**: none on the repository volume (ticket 12, criterion 1 — settings proposed, needs
  the QTS UI).
- ARD's machine-alias list and other live-machine state: not repository data, out of scope here.
