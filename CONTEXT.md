# T6 Munki Fleet — Context

## Purpose

This repository is the **git-owned source of truth for the Munki repository metadata** that
drives software delivery to T6's macOS fleet, plus the deterministic tooling that reports
what state each Mac is actually in.

The fleet is 16 production Macs (edit bays, war room, TOC, online, DIT laptops,
coordination, interns) plus the Mac Mini admin workstation and Cyril's Mac mini.

Two failures this project exists to prevent, in order:

1. **A change reaching the fleet un-reviewed.** Every item, catalog and manifest edit is a
   reviewable Git change with a recorded promotion decision.
2. **Cyril being unable to answer "what is each Mac running, and is it what we intended?"**
   Fleet state is observed deterministically and stored with provenance, so the answer comes
   from a record rather than from memory.

## Domain glossary

- **Repo (Munki repository):** the directory tree a Munki client reads over HTTP. Contains
  `catalogs/`, `manifests/`, `pkgs/`, `pkgsinfo/`, `icons/`.
- **Client endpoint:** `http://192.168.88.188/MunkiRepo` — plain HTTP on the T6 NAS, served by
  the QTS Web Server. Never internet-reachable.
- **Repository host:** the T6 NAS (`192.168.88.188`); live repo directory on volume `zfs23`.
- **Admin workstation:** the T6 Mac Mini (`192.168.88.151`). Runs `munkiimport`, `makecatalogs`
  and `manifestutil`; does not serve HTTP.
- **Metadata tree:** this repository's copy of `pkgsinfo/`, `manifests/` and `icons/` — the
  authoritative editable source. The NAS copy is a publish target, not an editable source.
- **Package payload (`pkgs/`):** installer items (`.dmg`, `.pkg`). Large, mostly re-downloadable
  vendor artifacts; kept on the NAS only, never in Git.
- **pkginfo:** a plist describing one installable item (name, version, installs, receipts,
  installer item, catalogs, architecture guard).
- **Catalog:** a generated index of pkginfos, produced by `makecatalogs` from the metadata tree.
  Two catalogs exist: `testing` and `production`.
- **Manifest chain:** `site_default` → `all` (fleet baseline policy) → role group → machine
  manifest. A machine manifest is named exactly the Mac's Munki short hostname.
- **Role group:** a manifest per fleet role (`toc`, `online`, `warroom`, `client-facing`,
  `dit`, `sound`, `interns-temporary`, `coordination-admin`). Carries role extras only.
- **Role matrix:** the assignment of each Mac to one role group, recorded in the specification.
- **Ring:** a stage an item passes through before fleet-wide availability. `testing` → **pilot**
  (`202-TOC-M4-Max`, Cyril's Mac mini) → `production`.
- **Promotion:** the recorded act of moving an item from `testing` to `production`.
- **Baseline core:** the small set of items force-installed on every Mac (remote support and
  shared essentials). Everything else approved for the fleet is optional.
- **Optional install:** an item a user may install from Managed Software Center. Approved items
  are also listed for managed updates so already-installed copies stay patched.
- **Deferred software:** vendor suites explicitly not distributed by Munki (DaVinci Resolve,
  Adobe Creative Cloud, Avid Media Composer, Avid Pro Tools, NTFS for Mac).
- **Observation:** one deterministic read of one Mac's Munki state, carrying both the source's
  own timestamps and the observation timestamp.
- **Observation store:** the append-only record of observations on the Mac Mini. Single writer.
- **Fleet view:** a derived, read-only projection of the observation store. Never authoritative.
- **Staleness:** the age of an observation. Stale observations are always qualified as stale,
  never presented as current state.
- **Drift:** any difference between the metadata tree and what the NAS is actually serving.
- **Kulit:** the T6 Telegram bot that owns alert delivery. Munki monitoring routes through it.

## Boundaries

- This repository never writes to a Mac. Clients initiate their own checks and installs.
- The NAS copy of the repository is a publish target. Hand-editing it is drift, and drift is a
  detected defect, not a workflow.
- No package payloads, credentials, or keys in Git.
- No LLM writes to the metadata tree, the observation store, the NAS, or a client machine. An
  LLM may render a bounded, read-only summary from the fleet view and nothing else.
- Munki never distributes the deferred vendor suites, and never without a recorded promotion.
- The Mac Mini admin workstation is a fleet member in its own right and is inventoried like any
  other Mac.
- Adopting an MDM is explicitly out of scope; onboarding stays scripted and documented.

## Engineering workflow

- Tickets: `.scratch/<feature>/issues/`, numbered in dependency order, one file per ticket,
  each declaring `Blocked by` edges and `Status`.
- Read `CONTEXT.md`, the relevant ADR, and the applicable specification before implementing.
- Durable decisions go in `docs/adr/`. Specifications go in `docs/specs/`.
- Prefer tests at module public seams with deterministic fixtures; never unit-test against the
  live NAS or a live Mac.
- Live verification evidence belongs in the ticket that claims the result; artifacts that are data
  rather than prose (checksum listings, captured output) live under `docs/evidence/` and are cited
  by the ticket.
- Secrets stay out of Git; operational credentials come from the approved credential mechanism
  at execution time.
