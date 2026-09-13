# 03: Detect drift and integrity gaps instead of discovering them

**What to build:** A check that answers "is the NAS serving exactly what Git says it should, and can
every item in every manifest actually be installed?" — reporting differences and missing payloads as
classified findings rather than as a silent state.

**Blocked by:** 02

**Status:** done (2026-09-13)

**Notes:** Detection and reporting only. This ticket does not repair drift — repairing from Git is
the documented direction (ADR 0001) and is performed deliberately. Alert delivery is ticket 15.

**Verification:** `python3 -m pytest` → **67 passed**. Live read-only run against the real
repository: exit 1 with exactly two findings, in 5.7 seconds.

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

- **No payload is missing.** Every item any machine manifest offers resolves to a pkginfo and a
  payload that exists on the NAS. This had never been checkable before.
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
