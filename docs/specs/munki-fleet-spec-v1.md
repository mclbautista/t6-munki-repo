# T6 Munki Fleet — Specification v1

Status: implementation authority for the scope below. Supersedes the recorded plan
summarised in the `projects.db` entry `munki-repo-macmini`.
Decision record: ADRs 0001–0008. Vocabulary: `CONTEXT.md`.

## Problem Statement

T6's macOS fleet gets its software from a Munki repository on the NAS, and today only the
repository's plumbing is finished. Everything around it is missing:

- Any package imported is immediately available to every Mac, because every manifest reads the
  `testing` catalog and there is no production catalog at all. There is no way to prove a package
  before the fleet receives it.
- The one catalog state that exists is unreviewable. It is edited by mounting the NAS share from
  the Mac Mini, and that mount is not present and cannot mount without credentials handed over
  interactively. Nobody can tell from Git what changed, when, or why.
- 26 items are force-installed on every Mac without anyone having approved that list per machine
  or per role, while the nine role groups carry no role-specific content whatsoever.
- One of those 26 items can never install on any Apple Silicon Mac, and it fails silently with a
  message that suggests something else is wrong.
- Test artifacts and explicitly deferred vendor suites are offered to every client in Managed
  Software Center.
- There is no record of what state any Mac is in. Three machines have ever been touched; the
  other 13 cannot be reported on without SSH-ing into each one. The admin workstation itself is
  an unmanaged client quietly resolving the fallback manifest.
- The repository's 13 GB of payloads have no snapshot and no backup job on the NAS.

Individually these are chores. Together they mean Cyril cannot answer two questions that
determine whether the fleet is under control: *"what is about to change on 18 Macs, and who
approved it?"* and *"what is each Mac actually running right now?"*

## Solution

Make the repository's metadata a reviewable Git history that an agent can build and publish
without a credential hand-off, and make fleet state a durable record instead of a live sweep.

For Cyril, the finished state behaves like this:

- He asks what a Mac is running and gets an answer from a record, with the time it was observed
  and whether that observation actually reached the machine.
- A new package proves itself on two pilot machines before the fleet can see it, and the moment
  it becomes fleet-wide is a recorded, approved promotion.
- The set of software forced onto every Mac is short, deliberate, and written down; craft software
  is offered per role and installed on request.
- Repository changes are ordinary reviewable commits; a hand-edit on the NAS is a defect the
  tooling reports rather than a workflow.
- An agent can do the whole import → build → publish → verify loop on its own, and cannot promote,
  delete, or reconfigure the fleet without him.
- A bad import or a wrong delete is recoverable from a snapshot, and a restore has been proven at
  least once.

## User Stories

1. As Cyril, I want every repository change to be a Git commit, so that I can see what changed,
   who changed it, and why.
2. As Cyril, I want the repository buildable without an interactive credential hand-off, so that
   an agent can complete maintenance without me.
3. As Cyril, I want one command that tells me whether the NAS is serving exactly what the
   repository says it should, so that drift is a report rather than a discovery.
4. As Cyril, I want a package to be provably tested on the pilot machines before the fleet sees
   it, so that a bad installer cannot reach 18 Macs at once.
5. As Cyril, I want promotion to production to be an explicit, recorded act, so that "who let this
   onto the fleet" always has an answer.
6. As Cyril, I want the forced baseline to be a short, deliberate list, so that no Mac receives
   craft software nobody chose for it.
7. As Cyril, I want role groups to actually differentiate roles, so that the tooling matches how
   the facility uses those Macs.
8. As Cyril, I want approved software to stay patched on Macs where it is already installed, even
   when it is optional, so that optional stops meaning unmanaged.
9. As Cyril, I want no deferred vendor suite offered through Munki, so that the recorded decision
   is the state of the fleet.
10. As Cyril, I want no test artifact visible in a client's software catalog, so that the fleet
    never sees the workshop.
11. As Cyril, I want every item that only supports one CPU architecture to say so, so that
    wrong-architecture installs are filtered instead of attempted.
12. As Cyril, I want no baseline item that a material share of the fleet can never install, so
    that the baseline means what it says.
13. As Cyril, I want a single authoritative answer to "which Mac is which", reconciled against
    machine serials and names, so that a manifest is never written for a hostname that does not
    exist.
14. As Cyril, I want to know which Macs have resolved which manifest, so that a machine silently
    falling back to `site_default` is visible instead of invisible.
15. As Cyril, I want the Mac Mini admin workstation treated as a fleet member, so that the machine
    that administers the fleet is not itself unmanaged.
16. As Cyril, I want to know what each Mac has pending, so that a stalled install is noticed
    before a deadline rather than during one.
17. As Cyril, I want architecture rejections and client warnings surfaced per machine, so that a
    package that cannot install is a reported fact.
18. As Cyril, I want an unreachable Mac recorded as unobserved, so that an offline laptop never
    reads as compliant.
19. As Cyril, I want every fleet statement to carry the time it was observed and its staleness, so
    that I never act on a stale reading as if it were current.
20. As Cyril, I want a new Mac onboarded by one documented procedure, so that onboarding does not
    depend on who is doing it.
21. As Cyril, I want onboarding to end with recorded evidence of manifest resolution, so that
    "enrolled" means verified rather than intended.
22. As an agent, I want to run the import → build → publish → verify loop without interrupting
    Cyril, so that routine maintenance is actually routine.
23. As an agent, I want a written list of what I may not do without approval, so that I never have
    to guess at blast radius.
24. As an agent, I want deterministic fixtures for the repository build and drift check, so that I
    can test without touching the live NAS.
25. As Cyril, I want repository health alerts only when something is actionable, so that alerts
    keep their meaning.
26. As Cyril, I want each alert to name its source and link to it, so that I can verify the claim
    myself.
27. As Cyril, I want the repository recoverable from a snapshot after a bad import or delete, so
    that a mistake is an inconvenience.
28. As Cyril, I want a restore actually performed and verified once, so that recovery is proven
    rather than assumed.
29. As Cyril, I want the repository unreachable from outside the LAN, so that fleet software
    distribution is not an internet-facing service.
30. As Cyril, I want the residual risk of unauthenticated metadata written down, so that the
    accepted risk is a decision on record.
31. As Cyril, I want the stale empty share that shadows the repository's name removed, so that
    nobody edits the wrong place.
32. As Cyril, I want the admin tooling and the clients on a supportable version relationship, so
    that the catalogs I generate are the catalogs my clients understand.
33. As a future maintainer, I want a specification, ADRs, and a ticket plan in one checkout, so
    that context does not live in a chat log.
34. As a future maintainer, I want the repository's current live state recorded as it actually is,
    so that the next person can tell what was built from what was assumed.
35. As Cyril, I want the fleet viewable without SSH-ing into each Mac, so that a status question
    is answered in seconds.
36. As Cyril, I want the fleet view to be a read-only projection, so that no reporting tool can
    change what the fleet runs.
37. As Cyril, I want an LLM to summarise fleet state but never change it, so that judgement is
    advisory and the deterministic path is authoritative.

## Implementation Decisions

### Modules and boundaries

**1. Metadata mirror.** *Responsibility:* own the editable `pkgsinfo/`, `manifests/` and `icons/`
trees in Git and publish them to the NAS host. *Non-responsibility:* deciding what the metadata
should contain; owning payloads. *Smallest interface:* `publish(paths, verify=True)` and
`compare() -> DriftReport`. *State owned:* the Git working tree and the publish manifest of
checksums. *Invariants:* after a successful publish the served tree matches the checkout
byte-for-byte for files under the metadata tree; a partial checkout is never publishable.
*Failure:* abort without partial publish; report which files diverged. *Dependencies:* the NAS
SSH path, ADR 0001.

**2. Package import.** *Responsibility:* acquire a vendor payload, generate its pkginfo, assign it
to the `testing` catalog, and record its source and architecture. *Non-responsibility:* promoting,
or editing fleet policy. *Smallest interface:* `import_item(payload) -> Pkginfo` and
`validate(pkginfo) -> list[Defect]`. *State owned:* staged payloads on the admin workstation.
*Invariants:* every pkginfo states a real payload hash and a real architecture guard when the
payload is single-architecture; the recorded source is one that can be re-fetched or the item is
flagged as non-reproducible (ADR 0006). *Failure:* a failed import leaves no pkginfo and no
catalog entry.

**3. Catalog builder.** *Responsibility:* build `testing` and `production` from the metadata tree
and publish the result. *Non-responsibility:* deciding membership — a pkginfo declares its own
catalog. *Smallest interface:* `build() -> CatalogSet` and `verify_served(names) -> list[Gap]`.
*Invariants:* every item in a machine manifest's catalog chain exists in the catalog and has a
reachable payload; catalog membership matches declared membership. *Failure:* a build that changes
membership unexpectedly is reported before publish.

**4. Manifest builder.** *Responsibility:* express fleet policy (baseline core, fleet optional,
role extras, machine→role assignment) as manifest files. *Non-responsibility:* resolving items,
building catalogs. *Smallest interface:* `render(policy) -> ManifestSet` and
`resolution_chain(hostname) -> list[str]`. *Invariants:* a machine manifest is named exactly the
machine's Munki short hostname and declares its own `catalogs` array; the chain
`site_default → all → role group → machine` resolves for every inventoried machine; no item appears
in two conflicting sections of one effective manifest. *Failure:* a manifest that cannot resolve is
a build failure, not a warning.

**5. Fleet observer.** *Responsibility:* the single deterministic writer of machine state. Reads
machine identity from the engineering inventory source and machine state from each Mac.
*Non-responsibility:* acting on what it observes. *Smallest interface:* `observe(targets) ->
ObservationRun` and `latest(hostname) -> Observation | None`. *Invariants:* append-only; every
observation carries source timestamp, observation timestamp, observer identity and probe outcome;
a failed probe writes an unreached observation, never a compliant one; a run records its own
completeness. *Failure:* a run that cannot complete writes what it observed and marks itself
incomplete.

**6. Fleet view.** *Responsibility:* a read-only projection of the observation store for humans and
for summaries. *Non-responsibility:* owning state. *Smallest interface:* `snapshot(scope) ->
FleetSnapshot` (a bounded, versioned read model). *Invariants:* never writes to the store, the
repository, the NAS, or a client; qualifies every statement with observation age; distinguishes
unobserved from compliant. *Failure:* renders what it has and says what is stale. This module's
user-facing shape is specified separately (see ticket 14); this specification fixes only its
read-only contract.

**7. Governance.** *Responsibility:* express and enforce the approval boundaries of ADR 0008 —
promotion, policy change, deletion, NAS system changes. *Non-responsibility:* doing the technical
work those approvals gate. *Smallest interface:* the approval-gated actions enumerated in ADR 0008
and the recorded approval attached to each. *Invariants:* no approval-gated action executes without
a recorded approval; illegal states (an item in `production` with no promotion record) are detected
and reported.

### Where the LLM boundary sits

Deterministic: identity, repository build and publish, catalog membership, manifest policy,
observation writes, drift detection, promotion records, alert triggering. An LLM may reason over a
bounded `FleetSnapshot` and render prose. It may not be on any path that writes to the metadata
tree, the observation store, the NAS, or a client (ADR 0004).

### Policy content settled here

- Baseline core (initial, subject to Cyril's confirmation in ticket 08): TeamViewer, AnyDesk,
  RemotePC, Remote Desktop, Google Chrome, Telegram, Notion.
- Everything else approved for the fleet is optional; approved optional items are also listed for
  managed updates.
- Role groups may only add optional items.
- Deferred vendor suites appear in no manifest section.
- Pilot machines: `202-TOC-M4-Max` and Cyril's Mac mini. Pilot manifests read
  `[testing, production]`; all other machine manifests read `[production]`.
- The Mac Mini admin workstation is a fleet member and requires a machine manifest.

### Recorded live state (baseline for this work)

Verified 2026-09-13; metadata imported into this repository under ticket 01 and checksum-verified
call-by-call against the NAS (103 files, zero differences): repository live at the NAS Web share and served over HTTP (`catalogs/all`,
`catalogs/testing`, `manifests/site_default` all return 200); 38 catalog entries over 36 unique
names, all declaring `catalogs: [testing]`; `catalogs/all` and `catalogs/testing` byte-identical;
28 manifest files including 16 machine manifests matching the role matrix; 27 top-level `.pkginfo` files plus 11 imported under a nested `apps` area (and four subdirectories of it) using a `.plist` extension; 13 GB of payloads; 36 icons;
duplicate name+version entries for two browsers; admin tools at Munki 6.6.0.4686 against clients
at 7.3.0.5808; NAS backup jobs zero; snapshots none; admin mount absent.

## Testing Decisions

- **Test external behaviour at module seams, never implementation detail.** A good test asserts a
  repository's *published and served* behaviour, not how a file was written.
- **Nothing in the test suite touches the live NAS or a live Mac.** Fixtures are a fake metadata
  tree and a fake served tree; the metadata mirror and catalog builder are exercised against a
  local static file server and a local temporary directory.
- **Drift detection is tested by mutation:** a mutated, missing and extra file must each be
  reported with the right classification, and an in-sync tree must report clean.
- **Manifest resolution is tested as a resolution problem:** for each inventoried machine, the
  chain must resolve, and a machine whose name is absent from the manifest set must be reported as
  falling back rather than silently accepted.
- **The observer is tested against recorded fixture report payloads**, including an unreachable
  machine, an architecture rejection, and a stale observation; the store's append-only and
  single-writer invariants are asserted directly.
- **Archive/restore is a test, not a hope:** the restore drill asserts payload checksums and that a
  catalog rebuild from restored metadata reproduces the live catalogs.
- **Live verification is acceptance evidence, not a unit test.** Each ticket records the machine,
  the command, and what it returned.

## Out of Scope

- Adopting an MDM, or any configuration-profile delivery channel (ADR 0005).
- TLS for the client endpoint (ADR 0007 defers it with an explicit revisit trigger).
- Distributing the deferred vendor suites (DaVinci Resolve, Adobe Creative Cloud, Avid Media
  Composer, Avid Pro Tools, NTFS for Mac).
- Automatic remediation of client machines: no agent-initiated installs, ever.
- AutoPkg-driven automatic package updates. Package acquisition is deliberate for now; this may
  become its own effort once the promotion path is proven.
- MunkiReport or Sal as a fleet telemetry product; the observation layer is bespoke and
  deterministic (ADR 0004).
- The T6 operations control plane's Notion/Telegram feed: unrelated ownership, though Kulit is the
  alert transport this project uses.
- Any change to the operational mirror database `projects-mgmt.db`. The tracker entry this project
  updates is the software-project tracker, `projects.db`.

## Further Notes

- The previously recorded plan for this project (tracker entry `munki-repo-macmini`) is superseded
  where it disagrees with this specification; its stale path references describe the earlier NAS
  share layout and are not the live repository.
- The repository's existing duplicate catalog entries and mixed pkginfo extensions pre-date this
  project and are cleaned as hygiene, not as a redesign.
- Ticket 14 asks for a separate specification of the fleet view's user-facing shape, produced by
  the same grilling method used to produce this specification. The read-only contract here stands
  regardless of what that specification decides.
- Work proceeds ticket by ticket on the declared frontier; each ticket's blockers must be complete
  before it starts.
