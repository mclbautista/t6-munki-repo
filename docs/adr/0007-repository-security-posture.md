# 0007: Plain HTTP on the LAN with a network allowlist; TLS deferred

- **Status:** Accepted (2026-09-13)

## Context

Verified 2026-09-13: the client endpoint is plain HTTP on port 80 on the NAS, unauthenticated,
with no directory listing. Package integrity is protected — `installer_item_hash` on every
pkginfo, `PackageVerificationMode = hash` on clients. The catalog, manifest and pkginfo path is
**not** authenticated: anything that can answer on that LAN path could serve a forged pkginfo
whose stated hash matches a substituted payload, and clients would trust it.

The NAS answers HTTPS on 443, but it does not expose the repository there. Munki cannot pin a
self-signed certificate, and there is no MDM or profile channel to deliver a trust anchor
(ADR 0005), so TLS would mean an unverifiable certificate trust decision at every client.

## Decision

- The repository **stays on plain HTTP and must never be reachable from outside the LAN.**
- Access is restricted at the NAS firewall to the fleet's own subnet addresses. The restriction
  is verified by a refused connection from an address outside the allowlist, not by the
  configuration screen alone.
- **The residual risk is recorded and accepted:** a LAN-level attacker positioned between a Mac
  and the NAS could substitute metadata. Package hashes protect payload integrity but not the
  metadata that states them.
- TLS is **deferred**, with an explicit revisit trigger: it is re-decided if a profile delivery
  channel (or an MDM) ever exists, or if the repository would become reachable beyond the LAN —
  in which case it must first be taken off the LAN entirely.
- The stale, empty NAS share that shadows the live repository's name is removed separately so it
  cannot be mistaken for the repository.

## Consequences

- No new trust infrastructure is required to keep the fleet working today.
- The accepted risk is documented where an auditor would look for it, rather than being implicit.
- Repository changes are visible to anything on the LAN; the repository holds no client data and
  no credentials, so the exposure is limited to software metadata and vendor installers.
- Any future BYOD or guest network sharing the subnet weakens the allowlist assumption and must
  trigger the revisit.

## Rollback

TLS can be introduced later behind a trust anchor delivered by a profile channel. Until such a
channel exists, there is no rollback path that does not break clients.

## Amendment, 2026-09-14: the mechanism this decision names is not the mechanism that is in force

The decision above is unchanged. What follows corrects this document's *description of its own
mechanism*, because a reader who takes the quoted sentence at face value would go looking for a
firewall that does not exist and a rule nobody ever wrote.

> **Superseded wording, quoted from the Decision section above:** "Access is restricted at the NAS
> firewall to the fleet's own subnet addresses. The restriction is verified by a refused connection
> from an address outside the allowlist, not by the configuration screen alone."

Ticket 13's decision 13A (2026-09-13) replaced that mechanism: **no firewall app is installed on the
NAS** (App Center holds 19 apps and none is QuFirewall or an equivalent), so there is no rule set to
point at and no default-deny posture to preserve. What restricts the repository is the **network path**,
verified read-only on 2026-09-14 and recorded in
`docs/evidence/13-network-path-verification-2026-09-14.txt`:

| path, from one host | result |
|---|---|
| fleet LAN, wired `192.168.88.202` | HTTP 200, 41,135 bytes, 0.002 s |
| the same host's Wi-Fi network (`192.168.0.107`, gateway `192.168.0.1`) | refused — timeout after 8.0 s |
| the same host's Tailscale interface | refused — timeout after 8.0 s |

Two consequences this decision's original text does not imply, and that a reader needs:

1. **The restriction is topological, not configured.** Nothing was set up to create it: it is the
   separation of two networks with no route between them, plus a NAS that establishes no path of its own
   (no relay, no DDNS, no UPnP; no VPN or overlay app at all; the connection log's recent window names
   only fleet-subnet sources). If those networks were bridged, or the NAS joined an overlay, the
   restriction would end **silently** — nothing observes reachability from a non-fleet path, so nothing
   would report it.
2. **One path remains unverified, on one device.** Whether a hand-made port-forward to the NAS exists on
   the device providing the fleet LAN's uplink (`192.168.88.201`, whose WAN NAT address is
   `27.49.72.161`) is a UI fact on a device that answers on TCP 53 only — none of the ten management
   ports probed — and whose MAC block carries no vendor name in the registry. Until that table is read,
   "never internet-reachable" rests on the NAS-side evidence alone; three off-network probes attempted on
   2026-09-14 were inconclusive and are recorded as such.

The revisit trigger this decision states ("a profile delivery channel (or an MDM) ever exists, or if the
repository would become reachable beyond the LAN") therefore gains a third, named case: **any change to
the separation between the fleet LAN and another network, or any addition of the NAS to an overlay.**
