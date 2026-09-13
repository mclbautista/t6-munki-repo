# 02: Publish path tracer bullet: Git edit to a client-visible change over HTTP, with no SMB mount

**What to build:** One narrow end-to-end proof of the new administration path: change one non-behavioural attribute of one existing pkginfo in the Git checkout, build catalogs locally, publish over the NAS SSH path, and confirm a pilot client's check-only run reflects the change — with the SMB mount demonstrably absent the whole time.

**Blocked by:** 01

**Status:** ready-for-agent

**Notes:** Choose a change with no install semantics (for example a display name or category) so the tracer bullet proves the path without altering what any Mac receives. Pilot machines: `202-TOC-M4-Max` and Cyril's Mac mini.

## Acceptance criteria

- [ ] The SMB mount to the NAS Web share is confirmed absent before, during and after the run; the evidence is recorded.
- [ ] The change is made only in the Git checkout — no file is edited on the NAS by hand.
- [ ] `makecatalogs` runs against the checkout and produces both catalogs without error.
- [ ] Publishing transfers metadata and catalogs over the NAS SSH path, writes to temporary names, verifies checksums, then renames into place — no partial file is ever visible to a client.
- [ ] The changed attribute is verifiably served: the served artifact's checksum matches the checkout's.
- [ ] A pilot machine run in check-only mode reports the item, with the resolved manifest name and clean result recorded against the machine's name.
- [ ] Reverting the change restores the original served checksum, recorded as a second run.
