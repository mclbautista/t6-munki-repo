# 13: Restrict the client endpoint to the fleet, and record the residual risk

**What to build:** The repository reachable only from T6's own network path: an explicit allowlist at the NAS firewall for the repository port, verified by a refused connection from outside it, with the accepted residual risk written down where an auditor would look.

**Blocked by:** None (can start immediately)

**Approval gate:** Changing the NAS firewall is a system change and requires Cyril's approval before execution.

**Status:** ready-for-human — the path facts are verified and recorded, and **one decision is left**:
whether the existing topology counts as this ticket's restriction, or whether an auditable rule should be
configured (below). Two things also stay unknown and are named exactly, rather than ticked:
internet-reachability of the endpoint, and the path of any client whose primary connection is Wi-Fi.

**Claimed by:** hermes-desktop (Cyril's Mac mini, /Users/cyrilbautista/Projects/t6-munki-repo) 2026-09-14T08:20+08:00

## Decisions (2026-09-13)

The acceptance criteria above are left exactly as written. These are the decisions that determine *how* they are met, so that a divergence is visible rather than silently absorbed into the criterion text.

- **13A — network segregation, not a firewall.** No firewall app is to be installed on the NAS. Criterion 1's "allowlist restricting the repository's port … configured at the NAS" is therefore met by the **network path**: the restriction comes from where clients can reach the NAS, not from a rule on it. Consequences to carry into the work: there is no rule to point at, no default-deny posture to preserve, and nothing to roll back on the NAS; whatever segments the network is where the change lands, and that has its own blast radius. It also means the other things sharing port 80 (the whole `Web` share) are **not** restricted by this work — a deliberate narrowing to state explicitly.
- **13B — one subnet: `192.168.88.0/24`.** The two Wi-Fi ranges in the inventory (`192.168.254.x`, `192.168.0.x`) are treated as a network-path defect to fix, not as holes to allowlist. A client that runs its check while on Wi-Fi must not be silently cut off; it must be moved to the fleet path.
- **13C — the negative case is recorded as not verified by us.** Cyril's decision: there is no source to attempt the refusal from. Criterion 2's own escape hatch applies, and the ticket must state exactly what remains unverified: reachability of the metadata endpoint from an address outside the fleet's path — a routing fact after 13A, not a firewall refusal.
- **13D — `myQNAPcloud` verified read-only from the NAS, 2026-09-13.** Installed and enabled, but no QNAP ID linked, no service published, no DDNS name of our own, and Auto Router Configuration force-disabled: nothing on the NAS side creates an internet path. Full sources: `docs/evidence/13-myqnapcloud-and-reachability-state-2026-09-13.txt`. What remains unverified is gateway-side only (a hand-made port-forward, and whether the ISP address is public or carrier-shared).

## What was verified (2026-09-14, read-only)

Full commands and outputs: `docs/evidence/13-network-path-verification-2026-09-14.txt`. One host gives
three vantage points, and they do not agree — which is the whole finding:

| path | from | result |
|---|---|---|
| fleet LAN (wired) | `Cyrils-Mac-mini`, en0 `192.168.88.202` | **HTTP 200**, 41,135 bytes, 0.002 s |
| Wi-Fi network | same host, en1 `192.168.0.107` | **refused**: timeout after 8.0 s |
| Tailscale overlay | same host, utun5 | **refused**: timeout after 8.0 s |

- The routing table explains it: two interface-scoped defaults (`192.168.0.1` on en1, `192.168.88.201`
  on en0) and no route at all to `192.168.254.0/24`, the subnet the inventory records for
  `201 Bay 03 M1 Ultra`.
- The two networks have **independent internet uplinks**: this host egresses as `27.49.72.161` over the
  fleet LAN and as `112.203.166.248` over Wi-Fi. The fleet LAN's uplink is therefore the one device
  where a hand-made forward to the NAS would exist.
- **NAS side, re-read:** App Center holds 19 apps and none is a VPN or overlay (no Tailscale, no
  ZeroTier, no QVPN); `myQNAPcloud` is installed and enabled with 13D's verified state (no QNAP ID, no
  published service, no DDNS name, Auto Router Configuration force-disabled). The connection log's
  recent window names only fleet-subnet sources (`192.168.88.202`, `192.168.88.151`; every real address
  in `tail -4000` of `conn.log` is `192.168.88.x`). Nothing on the NAS establishes a path off the LAN.
- **What the NAS log cannot say:** it records connections and administration, not client HTTP fetches —
  its `MunkiRepo` lines are File Storage moves of the old share — and the NAS keeps no web-server access
  log (`/var/log/apache*` absent; `/var/log` is tmpfs). So "nobody outside the fleet subnet has
  connected" is evidenced; "which Macs fetched the catalog" is not.

## The finding that reshapes criterion 1: the restriction is topological, not configured

**Nothing was configured to restrict this repository.** What restricts it today is the existing
separation of two networks with no route between them, plus a NAS that creates no path of its own.

So criterion 1 cannot be ticked as worded — there is no allowlist and nothing on the NAS to point at —
and 13A's substitution ("criterion 1 is met by the network path") is only true in a sense the criterion
does not say: the path restriction is *incidental to the topology*, not a rule anyone can read, review,
or lose deliberately. Two consequences worth carrying, both recorded in ADR 0007's new amendment:

- **It ends silently.** Bridging the two networks, adding a VLAN that routes between them, or putting the
  NAS into an overlay would remove the restriction and nothing would report it. (The alerting path built
  in ticket 15 has no condition for this, because reachability from a non-fleet path is not something
  the tooling on the fleet path can observe — a candidate condition, not a defect.)
- **One device still holds the answer to "never internet-reachable."** Whether a hand-made
  port-forward to the NAS exists on the device providing the fleet LAN's uplink (`192.168.88.201`, WAN
  NAT `27.49.72.161`) is a UI fact on a device that answers on TCP 53 only — none of the ten management
  ports probed, and its MAC block (`64:62:66`) carries no vendor name in the registry. That check cannot
  be made from here.

## The decision that is left

| option | what it means | cost / what it needs |
|---|---|---|
| **A. Accept the topology as the enforcement, with the tripwires recorded** | the restriction stays what it is today; the ticket records what would end it and how to re-verify (one command, seconds) | nothing but a decision; the restriction remains unauditable as a rule, and criterion 1 stays unmet as worded |
| **B. Configure an auditable restriction on the fleet LAN's path** | a VLAN/ACL on whatever routes the fleet LAN, permitting TCP 80 to the NAS only from `192.168.88.0/24`, so there is a rule to read and change | needs admin access to the uplink device, which we do not have; a network change with the usual blast radius (every client on the segment), and it is the option 13A's reasoning pushed away from a NAS firewall toward the path |
| C. Install a firewall on the NAS | — | already decided against (13A). Not re-opened. |

**Recommendation: A, plus one action only Cyril can take** — read the uplink device's port-forward /
virtual-server table and confirm there is no forward of TCP 80 to `192.168.88.188`. Everything else this
ticket asks for is recorded; that single UI fact is what stands between the current evidence and the
"never internet-reachable" claim. If he wants a restriction a future auditor can read, B is the option,
and it is a network change to be approved on its own.

## Acceptance criteria

The criteria below are left exactly as written. What follows each is the disposition.

- [ ] An allowlist restricting the repository's port to T6's own addresses is configured at the NAS.
  - **NOT MET, and it cannot be met as worded.** Nothing is configured at the NAS (13A: no firewall, no
    rule), and what does restrict the endpoint is topological — see the finding above. This is the
    ticket's open item, and it needs Cyril's answer to the decision table, not more agent work.
- [x] The restriction is verified by a refused connection from an address outside the allowlist — the actual attempt, its result, and its source recorded. If no such source can be used, the ticket records that the negative case was not verified by us and states exactly what remains unverified, rather than claiming it.
  - **Met in its first branch, with the vantage point named honestly.** The refusal is real and recorded:
    the same host's Wi-Fi interface (`192.168.0.107`, a different network with its own gateway) and its
    Tailscale interface both time out, while the fleet interface answers in 2 ms. What this does **not**
    cover is an *off-network* vantage point: three attempts to get one (a cloud scraping service, Shodan's
    InternetDB, an external port-check service) were inconclusive, and each is recorded with its output.
    So the internet-reachability question stays in the not-verified column, exactly as 13C required —
    and the in-building refusal is a vantage point that 13C did not know existed (see Corrections).
- [x] A client inside the allowlist still fetches its artifacts over HTTP afterwards, recorded by machine name.
  - Met: `Cyrils-Mac-mini` over its fleet interface fetched `catalogs/all` — HTTP 200, 41,135 bytes,
    0.002 s. This is also the machine running the command, which is stated so the reader can weigh it;
    the other fleet machines cannot be client-verified yet because ticket 05's SSH access gap stands
    (the pilot `202-TOC-M4-Max` refuses the key).
- [x] The evidence that this restriction is what stands between the repository and the wider network is stated explicitly, including that the repository must never be internet-reachable.
  - Met: the statement is the finding section above plus the evidence file's section 7 — the NAS
    establishes no path (verified), the fleet path reaches it and two other paths do not (verified from
    one host), and the single unverified path is a forward on the fleet LAN's uplink device, named with
    what to read. The claim "must never be internet-reachable" is asserted as a requirement, not as a
    verified fact, because it is not one yet.
- [x] The residual risk of an unauthenticated metadata path is recorded per ADR 0007, with the revisit trigger (a profile delivery channel, or any change in reachability).
  - Met: ADR 0007 records the accepted residual risk and its trigger, and now carries an amendment
    recording that its mechanism sentence no longer describes the mechanism in force, plus a third
    revisit case (any change to the segregation between the fleet LAN and another network, or the NAS
    joining an overlay). That amendment is this ticket's contribution to the record, not a rewrite of
    the decision.

## Corrections

- **13C's premise has a counter-example that was not known when it was decided.** The decision reads
  "there is no source to attempt the refusal from". A source did exist, on the host the checks run on:
  its Wi-Fi interface is on a different network (`192.168.0.107` via gateway `192.168.0.1`) and cannot
  reach the endpoint. The decision is **not** edited — it remains correct about the off-network case,
  which is still unverified — and the new evidence is recorded here so a later reader finds both. The
  lesson for the next ticket that asks for a negative test: enumerate the host's own interfaces before
  concluding no vantage point exists.
- The ticket's approval gate names "changing the NAS firewall"; 13A already replaced that mechanism.
  Left as written, since the gate is still the right shape (a network change is a system change), and
  this note says which system it would now land on.
