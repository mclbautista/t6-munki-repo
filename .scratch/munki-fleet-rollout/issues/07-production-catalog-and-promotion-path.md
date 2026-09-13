# 07: A production catalog and a real promotion path

**What to build:** Two catalogs with an enforced ring: an item is imported into `testing`, verified on the pilot machines, and only then promoted to `production`, which is what the rest of the fleet reads.

**Blocked by:** 02

**Approval gate:** Cyril approves the initial promotion into `production`, since that is the event which makes items fleet-wide.

**Status:** ready-for-human — implemented (mechanism, tests, evidence); the initial promotion it
describes awaits Cyril's approval.

*(was `ready-for-agent`: stale. The body has described the implementation since the ticket was
worked; the status was never moved.)*

**Notes:** This is the ticket that turns "everything is production by accident" into "everything is production by decision".

**Status:** ready-for-human

**Notes:** This is the ticket that turns "everything is production by accident" into "everything is production by decision".

## Acceptance criteria

- [~] The repository carries both `testing` and `production` catalogs, and a catalog build produces
      both.
      - **The build half is verified:** a test runs the real `makecatalogs` against a controlled tree
        whose items declare `testing`, `production`, and both, and asserts the build emits `all`,
        `testing` and `production`. It skips loudly if the tool is absent rather than passing empty.
      - **The repository half waits on the approval below** — the live repository gains a
        `production` catalog when the initial promotion is published, and not before.
- [ ] Pilot machine manifests declare `[testing, production]`; every other machine manifest declares
      `[production]`.
      Implemented as the plan's computed change, not yet applied, because applying it moves every
      machine's catalog search order at once. The plan computes exactly 28 manifest changes:
      `202-TOC-M4-Max -> ['testing', 'production']` and 27 others `-> ['production']`. Read-only
      output: `docs/evidence/07-initial-promotion-plan.txt`.
- [x] An item's catalog membership is what its pkginfo declares, and a test asserts that built catalog
      membership matches declared membership after every build.
      Per-catalog set equality between what `makecatalogs` wrote and what the pkginfos declare,
      against the real tool. This is the check whose absence let a wrong catalog silently change who
      can receive an item.
- [x] Promotion is an explicit, recorded action that states: the item, the version, the promotion
      date, the pilot verification evidence, and who approved it.
      `munki_fleet.cli promote` appends to `data/promotions.jsonl`, one JSON object per event, and the
      test asserts every one of those fields is present — plus the pkginfo's path and sha256, so the
      record names the exact bytes it moved. No promotion is on record yet: none has happened.
- [x] Promotion is refused when the item has no recorded pilot verification evidence.
      Refused before any write, naming what is missing. Covered by test, and demonstrated live on a
      throwaway copy: `--evidence` absent is a CLI-level refusal, and an unknown version reports what
      versions exist instead of guessing.
- [ ] The initial promotion of the currently-required items into `production` is performed as one
      recorded, approved event, so no machine loses software it already has.
      Planned, not performed. **Awaiting Cyril's approval** (the gate in this ticket's header).
- [ ] A non-pilot machine resolves a promoted item and does not resolve a testing-only item; both
      verified from observed client data, with machine names recorded.
      Needs the event first, then an observation run (ticket 05).

## The plan, and what it turns up

**Current plan (after ticket 09's cleanup, 2026-09-13): 26 items to promote, 2 deliberately left in
testing, 27 manifests to repoint, 1 blocker.** Read-only output:
`docs/evidence/07-initial-promotion-plan-after-cleanup.txt`. The two parked items are the deferred
Resolve pair, declared in `data/rings.json` so they cannot be promoted by forgetting a flag.

_What follows was the plan before the cleanup, kept because it is what the decisions were made
against._

36 items sat in the testing ring, and all 36 were referenced by some manifest — so "who belongs in
production" could not be derived from the repository. It was a policy decision, and it was the
approval ask. Beyond the documented 26-item baseline sat ten items:

| item | recommendation |
|---|---|
| `t6-munki-test` | exclude — a test artifact, and its manifest `t6-test-client` should be deleted, not repointed |
| `davinci-resolve-studio`, `davinci-resolve-project-server` | exclude — on the documented deferred list |
| `Cyberduck`, `Dropbox`, `Firefox`, `MSAutoUpdate`, `MSEdge`, `MSTeams`, `Spotify` | promote or withdraw? not in the documented baseline, all referenced by manifests, no recorded decision |

With the three clear exclusions applied that plan was 33 items and 28 manifests, captured in
`docs/evidence/07-initial-promotion-plan.txt` alongside the unfiltered run. **Cyril decided
2026-09-13: withdraw the seven beyond-baseline items, exclude the test artifact and the two
Resolve items from promotion.** Ticket 09 applied it: 36 → 28 pkginfos, so the promotion list is
now 26 items.

## Blockers that must be cleared before the event

1. **`Cyrils-Mac-mini` has no manifest of its own**, so it cannot read `testing` — it would resolve
   to `site_default` and the pilot ring would have one member, not two. It also carries
   `ClientIdentifier = t6-test-client` (read on the machine 2026-09-13), which overrides its
   identity entirely.
2. ~~The plan repoints `t6-test-client`~~ — **resolved by ticket 09**: the manifest and its test
   pkginfo are deleted, so there is nothing to repoint.

Ticket 09 is a **dependency of 07's initial event**, not a follow-up — recorded here because the
ticket header lists only 02. Ticket 09 is now implemented: the withdrawn items are gone, the
deferred pair is parked by declaration, and the manifest count is 27.

**Blocker 1 is still open and is now the only thing standing between the plan and the event.** It is
the `ClientIdentifier` line in ticket 09's "loose end" section — one command on Cyril's Mac mini,
and then the machine reports its own hostname manifest.

## Risks

- The event moves every machine's catalog search order in a single publish. That is the point — a
  machine that reads `production` must still find everything `testing` was serving — but it is also
  the largest single change in this project, and the pre-publish gate treats each manifest file as a
  declared file change, so it will refuse an undeclared run.
- Demotion is the rollback and is implemented and tested, but it only helps for an item that was
  promoted as an individual act. The initial event moves 33 items at once; rolling *it* back means
  restoring 36 pkginfos and 28 manifests, which is a pre-image restore, not a demotion.
