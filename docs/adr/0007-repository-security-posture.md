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
