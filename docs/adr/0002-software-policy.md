# 0002: Forced core, optional fleet software, role extras

- **Status:** Accepted (2026-09-13)

## Context

Verified 2026-09-13: the `all` manifest lists **26 items as `managed_installs`**, so every enrolled
Mac would receive all of them without consent — including Macs in client-facing viewing rooms and
edit bays. Cyril's Mac mini had **13 items pending install**; `managed_updates` was empty
everywhere. Ten of the 26 items come from the previously recorded baseline. The nine role groups
carry no distinguishing content at all: each inherits `all` and declares nothing else, so the
role hierarchy currently expresses no role policy.

## Decision

Three tiers, all recorded in the metadata tree:

1. **Baseline core — `managed_installs` in `all`.** A deliberately small set, limited to remote
   support and shared essentials, force-installed on every Mac. Initial core: TeamViewer,
   AnyDesk, RemotePC, Remote Desktop, Google Chrome, Telegram, Notion. This list is confirmed or
   amended by Cyril before it takes effect on the fleet.
2. **Fleet optional — `optional_installs` in `all`.** Everything else approved for the fleet.
   Approved items are also listed in `managed_updates` so copies already installed on a Mac are
   kept patched without forcing an install. This is what prevents silent drift on Macs where the
   tool was installed by hand.
3. **Role extras — `optional_installs` in the role group.** Craft-specific tools offered only to
   the roles that use them. Role groups may not add anything to `managed_installs`.

The **deferred vendor suites** (DaVinci Resolve, Adobe Creative Cloud, Avid Media Composer, Avid
Pro Tools, NTFS for Mac) are not present in any manifest section. Staged payloads for deferred
software may exist on the NAS, but no manifest may reference them.

Items that only support one CPU architecture must carry an explicit architecture guard, and an
item may not sit in a section where a material share of the fleet can never install it.

## Consequences

- Fleet Macs stop receiving craft software nobody asked for; the viewing rooms stay clean.
- Role groups finally mean something, and each role's extra set is reviewable in one place.
- Optional availability depends on a user action in Managed Software Center, offset by the
  managed-updates pairing for existing installs.
- Any change to the core list changes 18 machines and therefore requires Cyril's approval
  (ADR 0008).

## Rollback

Restore the prior `all` manifest from Git history and republish. Because the metadata tree is
versioned, the previous policy is recoverable as a single commit.
## Amendment: the baseline core is empty for now (2026-09-13)

**Superseded wording** (Decision, item 1): "A deliberately small set, limited to remote support and
shared essentials, force-installed on every Mac. Initial core: TeamViewer, AnyDesk, RemotePC,
Remote Desktop, Google Chrome, Telegram, Notion. This list is confirmed or amended by Cyril before
it takes effect on the fleet."

Cyril, 2026-09-13: *"i don't want anything to be force installed on this mac at this time. actually
turn off all the force installs for now."* That is the confirmation this ADR was waiting for, and
the confirmed core is **empty**. `all` declares `managed_installs` with no items, and the 26 items
that were force-installed are now in `optional_installs` in the same manifest, so they stay
installable by hand instead of vanishing.

The suspended list — AnyDesk, AppCleaner, CineCred, Stow, DiskCatalogMaker, FrameioDrive,
FrameioTransfer, FreeFileSync, GoogleChrome, HandBrake, IBMAsperaConnect, iTerm2, Keka, LucidLink,
MediaInfo, Notion, OnyX, QfinderPro, RemoteDesktop, RemotePC, ShutterEncoder, Soundly, TeamViewer,
Telegram, VLC, Zoom — is recorded machine-readably in `data/baseline-suspended.json` with the date,
approver, reason and the instruction for reversing it. Restoring the core is that list moved back to
`managed_installs` in `all` and republished; it changes what 18 machines receive and needs Cyril's
approval then as now (ADR 0008).

Verified after the change: no manifest anywhere declares `managed_installs`, `default_installs` or
`forced_installs`, and every machine manifest and role group resolves to **0 forced / 26 optional**.
Evidence: `docs/evidence/08-baseline-suspension.txt`. The tables above describe the tier model, which
is unchanged; only tier 1's membership is currently empty.

Nothing is uninstalled by this: an item that leaves `managed_installs` stops being installed and
updated automatically, it is not removed. Two consequences to know:

- **Self Service changes.** `managed_installs` items are hidden from Managed Software Center;
  `optional_installs` items are visible and user-installable. The 26 items become visible fleet-wide.
- **A machine missing them will not get them.** Machines without the remote-support tools stay
  without them until a user installs them from Self Service or the core is restored.


## Amendment: the deferred list is retired (2026-10-30)

**Superseded wording** (Decision, deferred paragraph): "The **deferred vendor suites** (DaVinci
Resolve, Adobe Creative Cloud, Avid Media Composer, Avid Pro Tools, NTFS for Mac) are not present in
any manifest section. Staged payloads for deferred software may exist on the NAS, but no manifest may
reference them."

Cyril, 2026-10-30, widened the project scope. **No suite is deferred any more**: Adobe Creative
Cloud, Avid Media Composer, Avid Pro Tools, DaVinci Resolve and NTFS for Mac are all in scope.

What replaces the rule for these titles: they may appear in a manifest only as **role extras
(`optional_installs`)**, and only after the package is validated in `testing` and Cyril approves the
promotion (ADR 0003, 0008). They never enter `managed_installs`; the baseline core stays empty and is
not re-enabled by this amendment. Eligible versions are set per OS and architecture, with no blanket
latest-version upgrades on editing machines. Adobe remains the entitlement authority (packages from
authorized Admin Console deployment packages); Avid titles come from official Avid sources. Vendor
sign-in may stay manual, and no credential, license key or activation detail enters Git.

Until the first validated package is promoted, no manifest references these titles, so nothing in the
served metadata changes by this amendment. `DEFERRED_SUITES` in `munki_fleet/drift.py`, the two
DaVinci `promotion_exclusions` in `data/rings.json`, and ticket 08's no-deferred-suite criterion still
encode the old rule and need a follow-up change; this amendment does not touch code or data.
