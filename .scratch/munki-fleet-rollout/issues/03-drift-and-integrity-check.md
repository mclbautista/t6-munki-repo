# 03: Detect drift and integrity gaps instead of discovering them

**What to build:** A check that answers "is the NAS serving exactly what Git says it should, and can every item in every manifest actually be installed?" — reporting differences and missing payloads as classified findings rather than as a silent state.

**Blocked by:** 02

**Status:** ready-for-agent

**Notes:** Detection and reporting only. This ticket does not repair drift — repairing from Git is the documented direction (ADR 0001) and is performed deliberately. Alert delivery is ticket 15.

## Acceptance criteria

- [ ] A drift report classifies, separately: files present in the checkout but missing on the NAS, files present on the NAS but not in the checkout, and files present in both with differing checksums.
- [ ] An in-sync repository reports clean, and the clean case is asserted by a test, not by inspection.
- [ ] Every item reachable in any machine manifest's catalog chain is checked for an existing payload and an existing pkginfo; missing ones are listed with the manifest that references them.
- [ ] Catalog membership is checked against each pkginfo's declared catalog, so an item declaring `testing` while a production-only manifest references it is reported.
- [ ] The check exits non-zero on any finding and requires no credentials to run.
- [ ] All of the above are exercised against fixtures by tests that never touch the live NAS.
