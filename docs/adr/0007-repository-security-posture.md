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

## Amendment, 2026-09-14: the mechanism this decision names is not the mechanism in force

The decision above is unchanged. What follows corrects this document's *description of its own
mechanism*, records what has and has not been read, and adds a revisit case — because a reader who takes
the quoted sentence at face value would go looking for a firewall rule on the NAS that does not exist.

> **Superseded wording, quoted from the Decision section above:** "Access is restricted at the NAS
> firewall to the fleet's own subnet addresses. The restriction is verified by a refused connection
> from an address outside the allowlist, not by the configuration screen alone."

Ticket 13's decision 13A (2026-09-13) replaced that mechanism: **no firewall app is installed on the
NAS** (App Center holds 19 apps and none is QuFirewall or an equivalent — re-read on 2026-09-14, in
`docs/evidence/13-network-path-verification-2026-09-14.txt`), so there is no rule set on the NAS to point
at. What is observed to restrict the repository is the **network path**, from one host with three
interfaces:

| path, from one host | result |
|---|---|
| fleet LAN, wired `192.168.88.202` | HTTP 200, 41,135 bytes, 0.002 s |
| the same host's Wi-Fi network (`192.168.0.107`, gateway `192.168.0.1`) | **no reply** — timeout after 8.0 s |
| the same host's Tailscale interface | **no reply**, and no tailnet node advertises a route into `192.168.88.0/24` |

Two consequences this decision's original text does not imply, and that a reader needs:

1. **No configured restriction was found — and the appliance that could carry one has not been read.**
   Nothing on the NAS creates a path (no relay, no DDNS, no UPnP; no VPN or overlay app at all), and no
   device on the paths this host can observe was found enforcing one. But the fleet LAN's gateway is a
   **pfSense firewall** (`192.168.88.201`: port 80 redirects to its management UI at
   `https://192.168.88.201:88/`, title `pfSense - Login`; Protectli hardware by its ARP MAC), and its
   NAT / port-forward table and LAN rules are unread because they need credentials — the UI answers, its
   contents do not. So the restriction should be treated as **observed, not documented**: under the
   topological account (two networks with no route between them) nothing reports it ending, while under
   the configured account there is a rule to read, record and rely on. Ticket 13's option A settles
   which.
2. **One path remains unverified, on that device.** Whether a hand-made port-forward to the NAS exists on
   the pfSense box, and whether the ISP address is public or carrier-shared, are both unread — 13D
   recorded both and neither is closed. (`27.49.72.161` is this host's *egress* address over the fleet
   path, not a reading of the firewall's own WAN configuration.) Three off-network probes attempted on
   2026-09-14 were inconclusive and are recorded as such, so until that UI is read, "never
   internet-reachable" rests on the NAS-side evidence alone.

The revisit trigger this decision states ("a profile delivery channel (or an MDM) ever exists, or if the
repository would become reachable beyond the LAN") therefore gains a third, named case: **any change to
the separation between the fleet LAN and another network, or any addition of the NAS to an overlay.**

## Second amendment, 2026-09-14: the unread configuration is accepted, not pending

Cyril's decision on ticket 13's option A: **stop trying to read the pfSense firewall. Accept the topology
as the restriction.** Recorded here so this document does not go on implying that a reading is coming.

- **The mechanism is the network path, and that is now the accepted answer — not the interim one.** Two
  networks with no route between them (fleet `192.168.88.0/24`; Wi-Fi `192.168.0.0/24`, gateway `.1`; the
  tailnet advertises no route in either direction), plus a NAS that establishes no path of its own
  (`myQNAPcloud` enabled but unlinked and unpublished, Auto Router Configuration force-disabled, no VPN or
  overlay app among its 19 App Center apps).
- **`192.168.88.201` (pfSense, Protectli) remains unread and is now an accepted unknown**, not an open
  item. It answers on TCP 53 and 80 and serves its management UI at `https://192.168.88.201:88/`; its NAT
  / port-forward table and LAN rules were never read, because reading them needs credentials that were not
  supplied and are no longer being asked for. Consequence, stated plainly: **there may be a configured rule
  on that appliance that this decision does not know about** — if one exists it only makes the restriction
  stronger, and it is not what the fleet relies on.
- **What "must never be reachable from outside the LAN" rests on, after this amendment:** the NAS-side
  evidence (no path created on the NAS) plus the observed absence of a route from any other network this
  host can see, with the residual risk below accepted rather than eliminated.
- **The cost that is now accepted deliberately:** nothing in the topology reports the restriction ending.
  There is no rule to review, no deny-log to watch, and no invariant checked by any automation today — the
  tripwires are named in ticket 13 and are **manual**. Any future monitoring of them is new work, not part
  of this decision.
- **The first amendment's finding is unchanged and still true**: no configured restriction was found on the
  paths observable, and the appliance that could carry one has not been read. What changes is the
  disposition — that gap is now accepted and documented instead of blocking a ticket.
