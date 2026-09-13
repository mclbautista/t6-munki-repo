# 0008: Agent autonomy and approval boundaries

- **Status:** Accepted (2026-09-13), approved by Cyril.

## Context

This repository's tooling is meant to run under agents. Fleet-affecting actions — what installs
on 18 machines, what leaves the repository, what changes on the NAS — must not be reachable by an
agent acting on a routine instruction. Without a written boundary, every agent invocation becomes
a judgement call about blast radius.

## Decision

**An agent may do autonomously (no approval):**

- Read any repository, NAS, or client state needed to understand the fleet.
- Edit the metadata tree in Git: pkginfos, manifests, role-group contents, icons.
- Run `makecatalogs` against the Git checkout.
- Publish lint-clean, checksum-verified metadata and catalogs to the NAS (ADR 0001), then verify
  the result over HTTP.
- Write observations to the observation store (ADR 0004).
- Run check-only Munki verification on a client machine (resolution and pending state, no
  installs).
- Open, update, and close tickets; record evidence; correct documentation.
- Import an item into `testing` and verify it **on the pilot machines**.

**Requires Cyril's explicit approval before execution:**

- Any change to the baseline core, or to a role group's membership (ADR 0002).
- Any promotion to `production`, or any demotion from it (ADR 0003).
- Any deletion in the repository: pkginfo, manifest, icon, catalog, or payload.
- Any change to a client's repository URL, or any client-side install run initiated by an agent.
- NAS system configuration: firewall, snapshots, backup jobs, shares.
- Munki tool versions on the admin workstation.
- Removing stale, empty, or superseded resources on the NAS.

**Never:**

- Make the client endpoint reachable from outside the LAN.
- Hand-edit the NAS tree when drift detection reports a difference; report the drift and repair it
  from Git.
- Put credentials, keys, or tokens in Git or in a ticket.
- Report a machine as compliant from an observation that did not reach it.
- Narrate a result as verified without reading the target back.

**Planned → attempted → completed → verified** are distinct states, and evidence must be attached
to the state being claimed. An unexplained system change carries no exemption because it looked
small.

## Consequences

- Routine repository work needs no human in the loop, which is the point of this project.
- Fleet-visible changes and anything destructive stay with Cyril, which keeps the blast radius of
  a mistaken agent small.
- Because promotions require approval, the pilot ring is where an agent can prove an item on its
  own; the approval step is the promotion itself, not the verification work.

## Rollback

Tighten or loosen the lists above through a new ADR. Do not treat this ADR as advisory: an agent
acting outside it is a defect to be reported, not a shortcut to be tolerated.
