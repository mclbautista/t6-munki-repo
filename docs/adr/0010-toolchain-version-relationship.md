# 0010: The catalog builder must match the clients' major version

- **Status:** Proposed — needs Cyril's acceptance, because the install it authorises is a system
  change on a facility Mac (ADR 0008).

## Context

Read from each machine's own tools on 2026-09-13:

- The machine that **builds catalogs** (whichever runs the publish path — today Cyril's Mac mini)
  runs Munki **7.3.0.5808** for `makecatalogs`, `managedsoftwareupdate` and `munkiimport`.
- The **admin workstation** (`Sixto-5`, macOS 15.7.1, Intel) runs **6.6.0.4686**
  (`com.googlecode.munki.admin` and `core` 6.6.0.4686, installed 2024-08-31), and its `munkiimport`
  writes pkginfos into the mount of the served share.
- The one client observed so far (`Cyrils-Mac-mini`, serial `RWJ57V9PW4`) runs **7.3.0.5808**; the
  pilot `202-TOC-M4-Max` was enrolled at 7.3.0.

So pkginfos are imported by a tool two major versions older than the tool that builds the catalogs
they end up in, and older than the tool every client reads them with.

**The gap is already observable in output, not theoretical.** The same metadata built by 6.6.0 and by
7.3.0 produces byte-different catalogs: the Firefox same-name pair was written `[.pkg, .dmg]` by
6.6.0 and `[.dmg, .pkg]` by 7.3.0, and a client takes the first entry matching a name (ticket 09's
evidence). That duplicate is resolved, but the mechanism is the point: **a rebuild is not guaranteed
to be a no-op**, which is precisely what a catalog rebuild has to be for the pre-publish gate's "no
item-level changes" to mean anything.

**The host question, defined here because the ticket's reference does not resolve.** Ticket 10 says
"see the open host question in the spec"; the specification contains no such question. The question
that actually exists is *which machine runs `makecatalogs`*, and today the answer is implicit —
whichever machine runs the CLI. That is an accident of tooling rather than a decision, and a catalog
built anywhere must be the catalog the clients receive.

## Decision

1. **The catalog build host is the machine that runs the publish path, and it must run the same major
   Munki version as the fleet's clients.** Verified now, not asserted: the live catalogs are
   **byte-reproducible** from that machine — a fresh build of the checkout equals what the NAS serves,
   both catalogs, `2/2 identical`, exit 0.
2. **The admin workstation is brought onto the same 7.3.x line before it is used for imports again.**
   Its `munkiimport` currently writes pkginfos into a tree whose catalogs are built by a different
   major version: an untested pairing, and one that can only be checked by trying it.
3. **Supported relationship: builder and clients share a major version.** Not a floor and ceiling
   across a gap — align. A client newer in major than the builder is the defect above; a builder newer
   than every client means the format has not been exercised on a client at all. `toolchain` fails
   while either is true.
4. **Any change to the admin tool version requires a before/after catalog byte-compare with the
   difference explained item by item**, captured *before* the change, and run against a **copy** of
   the metadata tree — never against the served share, which is a publish target.
5. **The relationship is recorded from observed versions, per machine**, by
   `munki_fleet.cli toolchain` (`docs/evidence/10-toolchain-versions.json`). It is a check that stays
   true, not a statement about one afternoon.

## Consequences

- The version relationship stops being folklore: one command exits non-zero while it is violated, and
  names both sides of the gap.
- **Importing is blocked on an upgrade** of the admin workstation, which is a system change on a
  facility Mac and therefore needs Cyril's approval before execution (ADR 0008).
- A rebuild becomes a no-op again, which is what makes the publish gate's item-level comparison a
  meaningful statement rather than a hopeful one.
- To be revisited when Munki 8 is released: a major-version change for the whole fleet at once,
  clients included, which this decision's rule would then require of all of them.

## Rollback

Re-install the previous Munki tools on the admin workstation. The component versions are recorded —
`munki.admin`/`core` 6.6.0.4686, `app` 6.6.0.4690, `launchd` 6.6.0.4656, `python` 3.12.2.4689 — so
the previous state is reproducible rather than remembered. Upgrading the tools rewrites no pkginfo
and no manifest (the tools do not own the metadata), so rollback is a re-install, not a restore; and
because the catalogs are byte-compared before and after, a change in catalog output would be visible
rather than silent.
