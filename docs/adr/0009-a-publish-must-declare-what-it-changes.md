# 0009: A publish must declare what it changes

- **Status:** Accepted (2026-09-13), decided during ticket 02 after a live incident.

## Context

On 2026-09-13 the first live use of the publish path carried an **unintended change to the fleet**.

The intent was a display-only edit to one pkginfo. What also went live was a reordering of the two
same-name `Firefox 155.0.1` entries in the catalog — because the repository carries two complete
pkginfos for that name and version, one pointing at a `.dmg` (`copy_from_dmg`) and one at a `.pkg`,
and `makecatalogs` 7.3.0 orders them the other way round from the 6.6.0 build the fleet was served.
Munki takes the first entry matching a name, so the fleet's Firefox installer would have changed
from the `.pkg` to the `.dmg`. Both builds are individually reproducible; the difference is the
tool version.

The change reached the repository because the tool offered `--allow-changes`, a bare bypass that
suppresses the diff check, and the operator passed it without reading the diff. The mechanism that
was supposed to inform the decision — printing the diff — was defeatable by a flag whose name
described the outcome rather than the intent.

The fleet was restored from pre-images within the same session and no client had fetched the
changed catalog, so the net effect on the fleet was zero. The lesson is not about that one flag.

## Decision

**A publish must declare what it expects to change, and the tool refuses everything else.** There is
no bypass flag. The four classes of change are each gated, because a key-by-key diff does not
describe all of them:

1. **Changed keys** on an existing item — `--expect-change ITEM:KEY` (or `ITEM:*`).
2. **Membership** — an item added to or removed from a catalog — `--expect-add`, `--expect-remove`.
   A diff that reads only changed keys lets these through silently.
3. **Duplicate-name entry reordering** — blocks by default, because it changes which installer a
   client receives while looking like a no-op. `--allow-duplicate-order-change` accepts it
   explicitly and prints the acceptance as a taken risk.
4. **Any non-catalog file that differs** — `--expect-file PATH`. A manifest edit produces no
   catalog diff at all and would otherwise publish undeclared.

A declaration that does not come true is also refused: declaring a change that did not happen is a
sign the operator's model of the repository is wrong, and publishing on a wrong model is how the
incident happened.

**The gate fails closed.** A target file that cannot be read is reported as unreadable, never as
absent, so a transient failure cannot turn into a silently accepted publish.

**A failed publish is not a partial publish.** The plan is validated before anything is written
(an incomplete checkout aborts with the target untouched), and a failure part-way through rolls
back every file this publish already wrote — restoring pre-images for files that existed and
removing files it created. The rollback outcome is part of the error, so a failure is never
reported with the target in an unknown state.

**Publishing is autonomous when the gate passes** (ADR 0008). The declaration is the record of what
was authorised, so it is written down rather than assumed.

## Consequences

- Routine publishing is **blocked** while the duplicate Firefox and GoogleChrome entries exist in
  the repository: every rebuild from the current toolchain reorders the Firefox pair, and the gate
  refuses it. That is the gate working, not failing. Resolving the duplicates is ticket 09, and
  aligning the toolchain is ticket 10 — either clears it.
- An operator (or agent) must state intent before a change can reach the fleet, and the statement
  is in the command that did it.
- A publish that partially applied is recoverable in the same operation, which matters because the
  repository has no snapshot until ticket 12 lands.
- The gate adds a step to every publish. The incident it prevents took minutes to detect and could
  have reached 18 Macs; the step is the cheaper side of that trade.
- The gate governs what this tool publishes. It cannot govern a hand edit on the NAS — that is
  drift, and drift detection (ticket 03) is what surfaces it.

## Rollback

Superseding this ADR requires a new one stating why an undeclared publish is safe. Removing the
gate without that would re-introduce the defect it was written for, so any proposal to weaken it
must name what replaces the declaration as the authorisation record.
