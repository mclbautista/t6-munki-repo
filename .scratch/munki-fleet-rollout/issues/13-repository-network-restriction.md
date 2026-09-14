# 13: Restrict the client endpoint to the fleet, and record the residual risk

**What to build:** The repository reachable only from T6's own network path: an explicit allowlist at the NAS firewall for the repository port, verified by a refused connection from outside it, with the accepted residual risk written down where an auditor would look.

**Blocked by:** None (can start immediately)

**Approval gate:** Changing the NAS firewall is a system change and requires Cyril's approval before execution.

**Status:** ready-for-human — two criteria are **not met** (1 and 2), three are (3, 4 as a statement of
record, 5), and what is left needs Cyril: **one credential-dependent read** of the firewall that carries
the fleet LAN, and **one decision** about whether that firewall's configuration counts as this ticket's
restriction or whether a rule should be read and recorded deliberately.

**Claimed by:** hermes-desktop (Cyril's Mac mini, /Users/cyrilbautista/Projects/t6-munki-repo) 2026-09-14T08:20+08:00

## Decisions (2026-09-13)

The acceptance criteria above are left exactly as written. These are the decisions that determine *how* they are met, so that a divergence is visible rather than silently absorbed into the criterion text.

- **13A — network segregation, not a firewall.** No firewall app is to be installed on the NAS. Criterion 1's "allowlist restricting the repository's port … configured at the NAS" is therefore met by the **network path**: the restriction comes from where clients can reach the NAS, not from a rule on it. Consequences to carry into the work: there is no rule to point at, no default-deny posture to preserve, and nothing to roll back on the NAS; whatever segments the network is where the change lands, and that has its own blast radius. It also means the other things sharing port 80 (the whole `Web` share) are **not** restricted by this work — a deliberate narrowing to state explicitly.
- **13B — one subnet: `192.168.88.0/24`.** The two Wi-Fi ranges in the inventory (`192.168.254.x`, `192.168.0.x`) are treated as a network-path defect to fix, not as holes to allowlist. A client that runs its check while on Wi-Fi must not be silently cut off; it must be moved to the fleet path.
- **13C — the negative case is recorded as not verified by us.** Cyril's decision: there is no source to attempt the refusal from. Criterion 2's own escape hatch applies, and the ticket must state exactly what remains unverified: reachability of the metadata endpoint from an address outside the fleet's path — a routing fact after 13A, not a firewall refusal.
- **13D — `myQNAPcloud` verified read-only from the NAS, 2026-09-13.** Installed and enabled, but no QNAP ID linked, no service published, no DDNS name of our own, and Auto Router Configuration force-disabled: nothing on the NAS side creates an internet path. Full sources: `docs/evidence/13-myqnapcloud-and-reachability-state-2026-09-13.txt`. What remains unverified is gateway-side only (a hand-made port-forward, and whether the ISP address is public or carrier-shared).

## What was verified (2026-09-14, read-only)

Full commands and outputs: `docs/evidence/13-network-path-verification-2026-09-14.txt`, which is a
**second** capture: its first version was reviewed line by line against its own claims and three of its
captures were wrong or unable to support what they were cited for (a truncated routing table, a
prefix-biased log extraction, and a port probe whose own output contradicted the sentence written about
it). The corrections are in the file, section by section.

| path, from this one host | what happened |
|---|---|
| fleet LAN, wired `192.168.88.202` | **HTTP 200**, 41,135 bytes, 0.002 s |
| Wi-Fi network (`192.168.0.107`, gateway `192.168.0.1`) | **no reply** — `curl` exit 28, timeout after 8.0 s |
| Tailscale interface | **no reply** — and no tailnet node advertises a route into `192.168.88.0/24`, so this request had nowhere to go (section 8) |

- **A timeout is not a refusal.** `HTTP 000`/exit 28 means no response; a filtered, black-holed or
  unrouted connection looks identical. This is recorded as a timeout everywhere, and it is why criterion
  2 is not ticked.
- The routing table shows the fleet subnet as a route on en0 and **zero** routes to `192.168.254.0/24`
  — the subnet the inventory records for `201 Bay 03 M1 Ultra` — captured as a count rather than
  asserted (section 2).
- Two independent internet uplinks: this host egresses as `27.49.72.161` over the fleet LAN and as
  `112.203.166.248` over Wi-Fi. These are the host's egress addresses, not a reading of any router's WAN
  configuration, and they say nothing about whether the ISP address is public or carrier-shared (still
  unverified, per 13D).
- **The fleet LAN's gateway is a pfSense firewall** at `192.168.88.201` (port 80 → `301` →
  `https://192.168.88.201:88/`, whose page title is `pfSense - Login`; the ARP MAC `64:62:66:21:cb:8e`
  resolves to Protectli hardware). This is the correction that matters: the first capture recorded the
  port-80 probe as "open" and then described the device as answering on TCP 53 only. Its configuration —
  in particular its NAT / port-forward table — is the unread thing, and it is blocked by **credentials**,
  not by unreachability.
- **NAS side, re-read:** 19 App Center apps and none is a VPN or overlay (no Tailscale, no ZeroTier, no
  QVPN); `myQNAPcloud` installed and enabled with 13D's verified state; the connection log's most recent
  200 entries (2026-09-13 → 2026-09-14) name only `192.168.88.202` (191) and `192.168.88.151` (9). Its
  own addresses are `eth3 192.168.88.188/24`, `lo`, and three container bridges in `10.0.x`.
- **What the NAS log is not:** it records connections and administration, not client HTTP fetches, and
  the NAS keeps no web-server access log (`/var/log/apache*` absent; `/var/log` is tmpfs). So "nobody
  outside the fleet subnet has connected" is evidenced for the window read; "which Macs fetched the
  catalog" is not evidenced from the NAS side at all.

## The finding, scoped to what was actually observed

The first version of this section claimed the restriction is "topological, not configured". That was an
inference over the vantage points held, presented as a fact, and the device that decides the question had
not been read. The honest version:

**No configured restriction was found on the NAS or on any path this host can observe — and one firewall
appliance sits on the fleet LAN whose configuration has not been read.** So there are two accounts of the
observations, and they cannot be told apart without that read:

1. the restriction is incidental to the topology: two networks with no route between them, plus a NAS
   that creates no path of its own; or
2. the restriction *is* configured, on the pfSense firewall that carries the fleet LAN — which is exactly
   where a rule permitting TCP 80 to `192.168.88.188` only from `192.168.88.0/24` would live.

Both are consistent with everything measured. Which one holds changes what criterion 1 means: under (2)
there is a rule to read, record, and rely on; under (1) nothing was set up and nothing would report the
restriction ending. **The read is the deliverable, and it needs a login.**

## The decision that is left

| option | what it means | cost / what it needs |
|---|---|---|
| **A. Read the pfSense firewall's NAT and LAN rules, then record what they say** | establishes which account above is true; under (1) the ticket records the tripwires that would end the restriction, under (2) it records the rule as the enforcement | needs credentials for `https://192.168.88.201:88/` — Cyril can read the two pages himself, or save the login so the read can be done read-only |
| **B. Configure an auditable rule deliberately** (on the pfSense box, not the NAS) | a rule permitting TCP 80 to the NAS only from `192.168.88.0/24`, so the enforcement is a deliberate, reviewable object | a network change on the appliance carrying the whole fleet LAN: every client on the segment is in the blast radius, and a mistake locks out the fleet's software delivery. Needs approval on its own |
| C. Install a firewall on the NAS | — | already decided against (13A). Not re-opened. |

**Recommendation: A first** — it is a read, it settles the question, and it is the only way to know
whether B is even necessary. Then B only if the read shows nothing is enforcing the path today, or if
Cyril wants the enforcement to be a thing an auditor can read.

## Acceptance criteria

The criteria below are left exactly as written. What follows each is the disposition.

- [ ] An allowlist restricting the repository's port to T6's own addresses is configured at the NAS.
  - **NOT MET.** There is no allowlist at the NAS (13A: no firewall app, no rule), and no configured
    restriction has been found on any path this host can observe — but a pfSense firewall carries the
    fleet LAN and its configuration has not been read, so "not found" is not "not there". This is the
    ticket's open item; option A above is what closes it.
- [ ] The restriction is verified by a refused connection from an address outside the allowlist — the actual attempt, its result, and its source recorded. If no such source can be used, the ticket records that the negative case was not verified by us and states exactly what remains unverified, rather than claiming it.
  - **NOT MET.** What was observed is a **timeout**, not a refusal, and the two are not interchangeable:
    `curl` exit 28 (`HTTP 000`) means no reply at all, which is also what a filtered or unrouted
    connection produces. Recorded as observations, with their vantage points: this host's Wi-Fi interface
    (`192.168.0.107`, on a different network with its own gateway) got no reply; the Tailscale interface
    had no route to try (no tailnet node advertises `192.168.88.0/24`). Off-network, three attempts (a
    cloud scraping service, Shodan InternetDB, an external port-check service) produced no usable result
    and are recorded as inconclusive. The negative case therefore remains **not verified by us**, which
    13C's escape hatch covers and which is why this is left open rather than ticked on the weak evidence.
- [x] A client inside the allowlist still fetches its artifacts over HTTP afterwards, recorded by machine name.
  - Met: `Cyrils-Mac-mini` over its fleet interface fetched `catalogs/all` — HTTP 200, 41,135 bytes,
    0.002 s — and the machine's name is grounded in captured output (`scutil --get LocalHostName`,
    `hostname`) rather than asserted. "Afterwards" is vacuous here because nothing changed, and this is
    also the machine running the command, which is stated so a reader can weigh it. The other fleet
    machines cannot be client-verified yet: ticket 05's SSH access gap stands (the pilot
    `202-TOC-M4-Max` refuses the key).
- [x] The evidence that this restriction is what stands between the repository and the wider network is stated explicitly, including that the repository must never be internet-reachable.
  - **Met as a statement of record, not as a verified fact.** The statement is the finding section above
    and the evidence file's section 7: the NAS establishes no path (verified), the fleet path reaches the
    endpoint while two other interfaces get no reply (observed), and the two unread/unverified items are
    named — the pfSense firewall's NAT table, and whether the ISP address is public or carrier-shared.
    "Must never be internet-reachable" is asserted as the requirement it is; what stands behind it today
    is the NAS-side evidence plus a firewall whose configuration has not been read.
- [x] The residual risk of an unauthenticated metadata path is recorded per ADR 0007, with the revisit trigger (a profile delivery channel, or any change in reachability).
  - Met: ADR 0007 records the accepted residual risk and its trigger, and now carries an amendment
    recording that its mechanism sentence ("restricted at the NAS firewall") no longer describes the
    mechanism its own records point to — the decision itself is unchanged, and the trigger gains a third
    named case (any change to the segregation between the fleet LAN and another network, or the NAS
    joining an overlay). The amendment's own two errors (the uplink device's ports and its vendor) are
    corrected in the same pass as this ticket.

## Corrections

- **13C's premise, corrected rather than adopted.** The decision reads "there is no source to attempt the
  refusal from". A source did exist for an *attempt* — this host's own Wi-Fi interface, on a network
  outside the fleet path — and the attempt produced no reply. That is not the refusal criterion 2 asks
  for, so 13C's conclusion (the negative case is not verified by us) stands for the case it names, and
  the decision is not edited. The lesson is worth keeping: enumerate the host's own interfaces before
  concluding that no vantage point exists.
- **The first version of this ticket's own finding was overstated** and is rewritten above: "nothing was
  configured" became "nothing was found on the paths observable, and the firewall that carries the fleet
  LAN was not read". Same for the two sentences about the uplink device in this ticket and in ADR 0007,
  which described it as answering on TCP 53 only and as having no vendor on record — both false, both
  corrected against captured output (section 4 of the evidence file).
- **The ticket's approval gate** names "changing the NAS firewall"; 13A already replaced that mechanism,
  and the object any change would land on is the pfSense appliance carrying the fleet LAN. Left as
  written — the gate is the right shape, and this note says which system it now points at.
