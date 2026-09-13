# 0001: Git-owned repository metadata, published over SSH

- **Status:** Accepted (2026-09-13)
- **Supersedes:** the assumption that the NAS repository is the editable source, reached over an
  SMB mount from the admin workstation.

## Context

The live repository is `/share/ZFS23_DATA/Web/MunkiRepo` on the NAS, served over HTTP by the QTS
Web Server. Until now it has been edited only by mounting the NAS `Web` share on the Mac Mini and
running `munkiimport` / `makecatalogs` against the mount.

Verified 2026-09-13: that mount was **not present** (`/Users/t6/Mnt/Web` empty), and `/etc/fstab`
holds the share entry without credentials, so it cannot mount headless. The working credential
pattern requires a percent-encoded SMB password inline in an interactive command. Every import or
manifest change therefore starts with a human handing over a credential, which caps what any
agent can do autonomously and makes the repository's history unreviewable.

Also verified: `makecatalogs` reads only `pkgsinfo/`, `manifests/` and `icons/` — it does not
require the package payloads or the live mount.

## Decision

The **metadata tree** — `pkgsinfo/`, `manifests/`, `icons/` — is owned by this Git repository.
The NAS copy is a **publish target**:

1. Edit metadata in the Git checkout.
2. Build catalogs locally with `makecatalogs` against that checkout.
3. Publish the changed metadata and regenerated catalogs to the NAS over the existing SSH alias
   for the NAS (`t6-nas`, port 2222), with a checksum-verified transfer.
4. Verify the result over HTTP against the client endpoint, and compare the published tree
   against the checkout.

Package payloads stay on the NAS under the Web share. Acquisition stages a payload on the admin
workstation for hashing and pkginfo generation, then transfers it to the NAS by the same SSH
path. Large payloads are re-fetchable vendor artifacts; they are not version-controlled.

The SMB mount remains available as a documented manual fallback for GUI tooling. It is no longer
on any automated path.

## Consequences

- Repository changes become reviewable Git commits with authorship and rationale.
- No credential hand-off on routine repository work; agents can run the full build-and-publish
  path.
- Drift becomes meaningful and detectable: a hand-edit on the NAS is a defect, not a workflow.
- Two-step publish introduces one new invariant — checkout and published tree must match after
  every publish. Drift detection enforces it.
- `makecatalogs` results depend on the checkout being complete; a partial checkout could publish
  a catalog missing items. The publish step must therefore compare the full metadata tree, not
  only changed files.

## Rollback

Revert to the SMB-mount workflow by re-enabling the mount and editing the NAS tree directly. The
Git tree remains valid as a mirror. Rollback is discouraged because it re-introduces the
credential hand-off and unreviewable history.
