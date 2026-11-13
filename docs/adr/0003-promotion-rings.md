# 0003: Two catalogs, three rings, explicit promotions

- **Status:** Accepted (2026-09-13), amended 2026-11-13 (see below: every Mac reads `testing` for now)

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

## Where the ring is declared

The pilot ring is machine-readable in `data/rings.json`, which names the two machines and where each
name came from. It exists because the promotion path has to decide who tests first, and prose in an
ADR cannot be read by the plan. **If the file and this decision disagree, this ADR wins and the file
is the bug.**

## Amendment: every Mac reads `testing` until Cyril decides otherwise (2026-11-13)

**Superseded wording** (Decision, Rings and manifests): "The pilot machines are the only Macs that
read `testing`." and "Machine manifests for pilot machines declare `catalogs: [testing, production]`;
every other machine manifest declares `catalogs: [production]`."

Cyril, 2026-11-13, confirmed that every manifest being on `testing` is intentional for now. Until
Cyril decides to move the fleet to `production`, **every Mac reads `testing`**, and the state this
ADR's Context recorded (every manifest declares `catalogs: [testing]`) is the accepted state, not a
defect. The move to `production` is Cyril's decision and is not made by this amendment.

What still holds: the two catalogs, a pkginfo's own `catalogs` array as the record of membership,
the pilot machines as the place an item is verified first, and promotion and demotion as explicit
steps that need Cyril's approval (ADR 0008). What changes in practice: while every Mac reads
`testing`, an import reaches the whole fleet at its next check, so the "only two machines" limit in
Consequences does not apply until the fleet moves.

When Cyril decides to move the fleet, that decision restores the superseded wording (pilots on
`[testing, production]`, everyone else on `[production]`) or records a different split. The
`_why_it_matters` note in `data/rings.json` still describes the old rule; this amendment does not
touch code or data.
