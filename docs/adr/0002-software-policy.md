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
