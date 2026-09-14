# 0011: Munki decides, Kulit delivers, and the outbox is the contract

- **Status:** Proposed — needs Cyril's acceptance, because wiring it changes a live service (the
  Kulit bot, which owns T6 alert delivery), picks the deployment paths, and adds one write class to
  ADR 0008's autonomy list (a message file and a state file on a machine's own filesystem). The
  decision-making half is implemented and verified; only delivery is gated.

## Context

Ticket 15 requires repository drift, integrity failures and fleet compliance regressions to reach
Cyril through Kulit, with a source he can check and with silence when nothing is actionable.

Three facts constrain how that can be done, all read from the systems on 2026-09-14:

- **The decision needs the checkout and the NAS; the bot does not have them.** Drift and integrity
  read the Git checkout *and* the served tree over the `t6-nas` SSH path (ADR 0001), and fleet state
  comes from the observation store (ADR 0004). The Kulit container mounts only `./data` and
  `./logs` of its own repository — no checkout, no SSH configuration, no observation store.
- **The delivery needs the bot, and the bot has one polling owner.** Kulit's existing precedent is
  in-process: `bot/ingest_monitor.py` polls the Ingest API's health URL and messages Cyril through
  the bot's own authenticated session, holding `failures` and `alert_sent` in memory. `CONTEXT.md`
  for Kulit says its token must have one polling owner and the dashboard is not a public API.
- **The two processes are on the same host.** Kulit runs in Docker on Cyril's Mac mini
  (`192.168.88.202`), which is also where the munki checkout lives. The container is the only thing
  that can send as Kulit; the host is the only thing that can compute the decision.

The naive alternatives are worse than they look: a script outside Kulit posting with Kulit's token
makes a second sender that reads the bot's credentials (and the ticket forbids a second identity); an
HTTP intake on Kulit's dashboard turns a local operational surface into an API (Kulit's `CONTEXT.md`
forbids it); running the check inside the container requires mounting the checkout, the observation
store and SSH keys into a service that has no business holding them.

## Decision

1. **The deterministic decision stays in this repository.** `munki_fleet.alerting` decides what is
   actionable and renders exactly one message; `munki_fleet.cli alert` runs one cycle. It holds no
   credential, sends nothing, and can be run and replayed by hand.
2. **Kulit is the only sender.** No second bot identity, no second reader of the token, and no
   Hermes transport in the alert path.
3. **The contract between them is a filesystem outbox with receipts**, because the container's
   `/data` mount is the one channel both sides already have:
   - the cycle writes at most one message per run: `<outbox>/alert-<stamp>-<digest>.json`;
   - the deliverer sends it to Cyril (`CYRIL_TELEGRAM_USER_ID`), appends
     `<outbox>/receipts.jsonl` — `{"message_id", "delivered", "at", "detail"}` — and removes the
     message file;
   - the next cycle consumes the receipt. Delivered means the condition counts as notified; failed
     means it is recorded undelivered, retried, and the run exits non-zero. A message nobody
     acknowledged within `--ack-ttl` is undelivered for the same reason, unless a later message
     delivered the same conditions — then it is *superseded*, which stops one lost message reporting
     failure for as long as the state file lives;
   - a receipt counts only what the message actually showed a reader. A digest truncated at
     `--max-conditions` leaves the elided conditions actionable, so a first sight of nineteen
     conditions arrives as two messages rather than one that silently drops the tail.
4. **Receipts are consumed idempotently, so the log is the deliverer's to rotate.** The cycle records
   a receipt against the message it names; a receipt for a message the state no longer holds changes
   nothing and is reported as stray. The deliverer may therefore truncate `receipts.jsonl` whenever
   it likes, and a replayed line is harmless.
5. **The deliverer is a second monitor in Kulit, mirroring `ingest_monitor.py`**: a loop that reads
   the outbox every 30 seconds, sends one message per file, writes the receipt, and fails closed
   (no receipt, message left in place, logged) when `CYRIL_TELEGRAM_USER_ID` is unset or the send
   fails. It never decides anything: severity, content and "is this worth sending" are already
   decided, which is what keeps the trigger deterministic.
6. **Deployment paths, proposed**: outbox and its receipts at
   `~/Projects/kulit_t6bot/data/munki-alerts/` (already inside the container's mounted `/data`);
   alert state at `~/.munki-fleet/alert-state.json` beside the observation store, on the host named
   below — not in the checkout; the cycle run by a launchd job every 15 minutes. Cost, measured on
   2026-09-14 rather than estimated: a cycle reads the checkout (94 metadata files) and the served
   tree over SSH — one `list_files` plus one `stat` per file — and took **4.1–4.3 s** wall clock
   across three runs (`docs/evidence/15-alert-cycle-live-2026-09-14.txt`, capture 1).
7. **The failure modes are the point**: Kulit down → the outbox grows, cycles exit non-zero, and no
   alert is reported as delivered. The host running the cycle down → nothing is delivered, and
   nothing about software delivery to the fleet changes, because the observer and the alerter are not
   in the delivery path.

### The host this runs on, named

`CONTEXT.md` defines the **admin workstation** as the T6 Mac Mini, `192.168.88.151` (ADR 0010 names
it `Sixto-5`). The machine that actually holds the checkout, the observation store and the Kulit
container is a different one: **Cyril's Mac mini, `192.168.88.202`**, verified 2026-09-14 —
`scutil --get LocalHostName` → `Cyrils-Mac-mini`, `ipconfig getifaddr en0` → `192.168.88.202`,
`~/.munki-fleet/observations.jsonl` present there, and the `kulit-bot` container running there with
`./data:/data` mounted. ADR 0004 carries the same looseness ("the observation store on the admin
workstation"), and this ADR's Context was written from its own facts, not from that term.

**The decision documents are not edited here**: what "the admin workstation" means is Cyril's call,
not an agent's. This note exists so the deployment above names a host that can run it — the cycle
must run where the checkout and the store are, and the outbox must be on the host running the
container, which today is one machine.

## Consequences

- Alert delivery is verifiable end to end: a condition, the message it produced, whether the
  transport acknowledged it, and the source for the claim — all on disk.
- Kulit remains the single owner of T6 alert delivery, and this project never holds a Telegram
  credential (ADR 0008's "never put credentials in Git" stays true by construction, not by care).
- The munki tooling writes into another service's deployment directory. That is deliberate: the
  alternative is a new inbound API on Kulit or a credential outside it, and this is the narrowest
  channel that already exists.
- **On acceptance, ADR 0008 should be amended in words** to name this write class. ADR 0008
  enumerates what an agent may do autonomously and says an agent acting outside it is a defect; its
  rollback sanctions loosening the list "through a new ADR", which this is. Leaving the extension
  implicit is how a boundary stops being checkable.
- Alerts are only as fresh as the observation store: a stale fleet reading alerts as *stale*, never
  as current, and the freshest state any alert can carry is the last probe.
- To be revisited if T6 ever standardises a service-health intake (then the outbox becomes one
  producer of it), or if Kulit stops being the alert transport.

## Rollback

Remove the launchd job and the Kulit monitor task; the cycle command is inert without a runner, and
nothing else changes. Delete the outbox directory and the alert state. No NAS, Mac or client is
touched by any part of this decision, so rollback has no fleet effect.
