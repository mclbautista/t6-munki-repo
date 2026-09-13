# 07: A production catalog and a real promotion path

**What to build:** Two catalogs with an enforced ring: an item is imported into `testing`, verified on the pilot machines, and only then promoted to `production`, which is what the rest of the fleet reads.

**Blocked by:** 02

**Approval gate:** Cyril approves the initial promotion into `production`, since that is the event which makes items fleet-wide.

**Status:** ready-for-agent

**Notes:** This is the ticket that turns "everything is production by accident" into "everything is production by decision".

## Acceptance criteria

- [ ] The repository carries both `testing` and `production` catalogs, and a catalog build produces both.
- [ ] Pilot machine manifests declare `[testing, production]`; every other machine manifest declares `[production]`.
- [ ] An item's catalog membership is what its pkginfo declares, and a test asserts that built catalog membership matches declared membership after every build.
- [ ] Promotion is an explicit, recorded action that states: the item, the version, the promotion date, the pilot verification evidence, and who approved it.
- [ ] Promotion is refused when the item has no recorded pilot verification evidence.
- [ ] The initial promotion of the currently-required items into `production` is performed as one recorded, approved event, so no machine loses software it already has.
- [ ] A non-pilot machine resolves a promoted item and does not resolve a testing-only item; both verified from observed client data, with machine names recorded.
