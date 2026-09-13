# 0003: Two catalogs, three rings, explicit promotions

- **Status:** Accepted (2026-09-13)

## Context

Verified 2026-09-13: every pkginfo declares `catalogs: ["testing"]`, every manifest (machine
manifests included) declares `catalogs: [testing]`, and `catalogs/all` and `catalogs/testing` are
byte-identical (60,092 bytes). There is no production catalog in use and no client reads one, so
everything imported is immediately fleet-wide. The previously recorded plan to "import to testing
first, promote to production after verification" was never implemented.

## Decision

- The repository carries **two catalogs: `testing` and `production`**.
- **Rings:** an item is imported into `testing`, verified on the **pilot machines**
  (`202-TOC-M4-Max` and Cyril's Mac mini), then **promoted to `production`** for the rest of the
  fleet. The pilot machines are the only Macs that read `testing`.
- Machine manifests for pilot machines declare `catalogs: [testing, production]`; every other
  machine manifest declares `catalogs: [production]`.
- A pkginfo's own `catalogs` array states which catalog it belongs to; promotion is the recorded
  change of that array (plus any version supersession), never an implicit rename.
- Promotion and demotion are explicit steps with recorded evidence on the pilot machines. A
  promotion with no verification evidence on the pilot ring is incomplete.

## Consequences

- A bad package can only reach two machines before someone looks at it.
- Each import costs one deliberate promotion step. That cost is the control.
- The pilot ring must actually be exercised; a promotion that skips pilot verification defeats
  the ring and is a defect.
- `production` and `testing` membership must be checked after every catalog build, since a
  pkginfo declaring the wrong catalog silently changes who can receive it.

## Rollback

Demote the item by restoring its `testing` catalog membership in Git and republishing; clients
stop seeing it at their next check. No client state is destroyed by a demotion.
