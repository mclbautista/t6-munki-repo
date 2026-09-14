# 08: A short forced baseline and role groups that mean something

**What to build:** Fleet software policy as three tiers — a small forced core on every Mac, everything else approved offered as optional and kept patched, and role-specific tools offered only to the roles that use them.

**Blocked by:** 07

**Approval gate:** Cyril confirms or amends the forced core list before it takes effect. Initial proposal: TeamViewer, AnyDesk, RemotePC, Remote Desktop, Google Chrome, Telegram, Notion.

**Status:** ready-for-human (the forced core is suspended **and, as of 2026-09-14, published**; role extras
and the managed-updates pairing remain).

## The forced core is empty (Cyril, 2026-09-13)

Cyril: *"i don't want anything to be force installed on this mac at this time. actually turn off all
the force installs for now."* Applied and recorded:

- `manifests/all` declares `managed_installs` with no items; the 26 items moved to
  `optional_installs` in the same manifest, so they remain installable by hand.
- `data/baseline-suspended.json` carries the suspended list with the date, approver, reason and the
  reversal instruction. Mechanism: `munki_fleet.baseline.suspend_forced_installs`, tested; the check
  `forced_installs()` returns empty, verified across every machine manifest and role group
  (`docs/evidence/08-baseline-suspension.txt`).
- ADR 0002 carries an amendment quoting the superseded core list; `CONTEXT.md`'s glossary entry now
  says the core is empty by decision.
- **Nothing is uninstalled by this**, and the tier model in ADR 0002 is unchanged — only tier 1's
  membership is currently empty.

Two consequences that are now live decisions rather than footnotes: the 26 items are **visible in
Self Service** (they were hidden as managed installs), and a Mac missing them **will not receive
them** until a user installs one or the core is restored.

**This change is PUBLISHED** — 2026-09-14, in the one publish that carried it together with ticket 06's two machine manifests, exactly as the ordering note below required. Served `manifests/all` now reads **0 `managed_installs` / 26 `optional_installs`**, verified over HTTP, and the drift check reports 0 findings. Full capture: `docs/evidence/06-08-publish-2026-09-14.txt`.

## Ordering: this change and ticket 06's manifests are entangled

A publish is all-or-nothing: the pre-publish gate refuses any undeclared file difference between the
checkout and the target, so the two machine manifests ticket 06 committed for `303A-Mac-Mini-M4-Pro`
and `Sixto-5` (the admin workstation) cannot be left out of a publish that carries this change.

Ticket 06's own approval gate requires Cyril to approve *what the admin workstation receives* before
that manifest is applied, so the two should not be published by this ticket's urgency. The safe order
is **one publish carrying both**, because the suspension lands in the same change: those two machines
then resolve their own manifests and inherit 0 forced / 26 optional, where publishing them *before*
this change would have force-installed up to 26 items on both.

**Discharged 2026-09-14:** that is what the publish did — one run, declared up front with three
`--expect-file` entries, gate accepted, `written 3, unchanged 93, backed up 1`, HTTP verify `96/96 match`.
The two machines are served their own manifests and, through `all`, inherit 0 forced / 26 optional.
Capture: `docs/evidence/06-08-publish-2026-09-14.txt`. The pre-publish state of `manifests/all` is kept
at `~/.munki-fleet/pre-images-20260914T092916/manifests/all` (sha256 `88a3e05f…`) as the way back.

## Acceptance criteria (revised against the current decision)

- [x] The forced core is listed explicitly and matches what is in the manifests; nothing else is
      force-installed. **The core is empty**, so it trivially matches — and `forced_installs()`
      asserts it rather than asserting it by eye.
- [ ] Every approved non-core item appears as optional, and approved optional items are also listed
      for managed updates so already-installed copies stay patched. **Half done:** the 26 are
      optional; `managed_updates` is still empty everywhere, so nothing is kept patched yet. That
      pairing is a follow-on decision, not part of Cyril's instruction.

**Notes:** Role extras are proposed per group in this ticket and confirmed before publishing.

## Acceptance criteria

- [ ] The forced core is listed explicitly in the specification and matches what is in the manifests; nothing else is force-installed.
- [ ] Every approved non-core item appears as optional, and approved optional items are also listed for managed updates so already-installed copies stay patched.
- [ ] Each of the 9 role groups expresses that role's tool set and adds nothing to the forced core; a test asserts no role group declares a forced install.
- [ ] No deferred vendor suite appears in any manifest section, asserted by a test that searches every manifest section for them.
- [ ] No item is listed in two conflicting sections of one effective manifest, asserted per machine from the resolved chain.
- [ ] On the pilot machines the change is verified end to end: the core is present, an optional item appears as available rather than installed, and a role extra does not appear for a machine outside that role.
- [ ] The before/after of what each pilot machine would install is recorded as evidence.
