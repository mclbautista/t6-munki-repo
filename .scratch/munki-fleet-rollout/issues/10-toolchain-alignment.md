# 10: Align the admin toolchain with the client fleet

**What to build:** Admin tooling and clients on a supportable version relationship, so the catalogs and pkginfos built by the admin workstation are the ones the clients actually understand.

**Blocked by:** 02

**Approval gate:** Installing or upgrading tooling on the Mac Mini is a system change on a facility machine and requires Cyril's approval before execution.

**Status:** ready-for-human — implemented, and the install it authorises awaits Cyril

## What was built and verified

**`munki_fleet.cli toolchain`** — records the version relationship from observed data: the versions
are read by *running* each tool on the machine that holds it, and client versions come from the
observation store (ticket 05). Exit code is non-zero while the relationship is violated.

```
build hosts:
  local            makecatalogs             7.3.0.5808     <- builds the catalogs
  local            munkiimport              7.3.0.5808
  t6-mac-mini      makecatalogs             6.6.0.4686     <- admin workstation
  t6-mac-mini      munkiimport              6.6.0.4686
clients observed: 1
  RWJ57V9PW4    Cyrils-Mac-mini   7.3.0.5808
  FINDING: t6-mac-mini builds with Munki 6.6.0.4686 while RWJ57V9PW4 runs 7.3.0.5808: the
  builder is a major version behind a client, so a rebuild can reorder entries the client is
  already being served
```

Recorded to `docs/evidence/10-toolchain-versions.json`.

**`munki_fleet.cli catalog-compare`** — the before/after harness criterion 3 asks for: byte-compare a
fresh build against a pre-image (a local directory or a served target), and explain every difference
item by item. Demonstrated against a real pair — the catalog as served before ticket 09's cleanup —
where it reports the bytes differ and names exactly the eight withdrawn items ("every difference is
explained by the item-level diff"). It also distinguishes the case that has no item-level difference
at all: **the same entries serialised or ordered differently, which is what a different tool version
produces** — the 6.6-vs-7.3 behaviour this ticket exists because of.

**The current alignment is verified, not assumed:** a fresh build of the checkout equals what the NAS
is serving — **2/2 catalogs identical, exit 0** (`docs/evidence/10-toolchain-and-compare.txt`).

## A broken cross-reference, corrected

This ticket said "see the open host question in the spec". **The spec contains no such question** —
the reference does not resolve. The question that actually exists is *which machine runs
`makecatalogs`*, and it is now defined and answered in ADR 0010 rather than left as a dangling
pointer.

## The decision, and what it authorises

ADR 0010 (Proposed) decides: the **build host must share the clients' major version** (true today and
verified byte-for-byte), the **admin workstation is brought onto the same 7.3.x line** before its
next import, any tool change requires a **before/after byte-compare**, and the relationship is checked
by `toolchain` rather than remembered.

**What needs Cyril's approval** — an install on a facility Mac (ADR 0008):

1. On the admin workstation, build a catalog from a **copy** of the metadata tree with the current
   6.6.0 tools and keep the result (the "before").
2. Install the Munki 7.3.x release package there (the component receipts currently installed are
   recorded for rollback: `admin`/`core` 6.6.0.4686, `app` 6.6.0.4690, `launchd` 6.6.0.4656,
   `python` 3.12.2.4689). No installer is cached on either Mac, so this is a download from the Munki
   release page.
3. Rebuild from the same copy with 7.3.x and `catalog-compare` the two — every difference explained
   item by item.
4. Record the relationship again with `toolchain` (it must exit 0), and confirm a pilot's resolved
   manifest and client version from observed data.

Nothing in step 1 or 3 touches the served share: the build runs against a copy, because the mount is
a publish target.

## Acceptance criteria (revised against what can be observed today)

- [x] The admin workstation's tool version and the clients' versions are **recorded from observed
      data**: read by running each tool where it lives, clients from the ticket-05 store. One caveat
      recorded rather than hidden: only reachable machines can be observed, so this is one client and
      the admin workstation until the fleet has a transport (tickets 05/11).
- [x] A decision is recorded on the supported version relationship — **ADR 0010**, aligning the
      builder to the clients' major version rather than declaring a floor and ceiling across the gap.
      It is `Proposed` because accepting it authorises the install.
- [~] After any change to the admin tool version, `makecatalogs` is re-run and the catalogs
      byte-compared against the pre-change build with differences explained item by item.
      **The harness is built and demonstrated on a real pair**; the pre/post pair for the tool change
      itself cannot exist until the upgrade is approved and performed.
- [ ] A pilot machine's check-only run after the change is clean, with the resolved manifest and
      client version recorded. Waits on the install; note the change is to *admin* tools, so the
      catalogs are the client-visible artifact — which is why the byte-compare is the real check.
- [x] The decision is written into an ADR rather than left in the ticket: **ADR 0010**.

**Notes:** Verified 2026-09-13: admin tools 6.6.0.4686 against enrolled clients at 7.3.0.5808 — two major versions apart.

**Evidence added by ticket 02 (2026-09-13): the version gap already changes catalog output.** The
live catalog was built by 6.6.0; rebuilding the same metadata with 7.3.0 produces a byte-different
catalog whose Firefox duplicate pair is ordered the other way round, which changes which installer
a client receives (details in ticket 09). Both builds are individually reproducible, so this is a
tool-version difference. Aligning the toolchain is therefore not bookkeeping: it determines whether
a catalog rebuild is a no-op or a behaviour change. The `SshTarget` publish path already runs
against the checkout on the machine that holds it, so the decision includes *where* the build runs
(see the open host question in the spec).

## Acceptance criteria

- [ ] The admin workstation's Munki tool version and the version running on each client are recorded per machine from observed data.
- [ ] A decision is recorded on the supported version relationship — either the admin tools are brought up to the client major version, or an explicit floor and ceiling are declared with the reason.
- [ ] After any change to the admin tool version, `makecatalogs` is re-run and the resulting catalogs are byte-compared against the pre-change build, with any difference explained item by item.
- [ ] A pilot machine's check-only run after the change is clean, with the resolved manifest and client version recorded.
- [ ] The version relationship decision is written into the specification or an ADR, not left in the ticket.
