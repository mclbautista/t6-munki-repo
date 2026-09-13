# 10: Align the admin toolchain with the client fleet

**What to build:** Admin tooling and clients on a supportable version relationship, so the catalogs and pkginfos built by the admin workstation are the ones the clients actually understand.

**Blocked by:** 02

**Approval gate:** Installing or upgrading tooling on the Mac Mini is a system change on a facility machine and requires Cyril's approval before execution.

**Status:** ready-for-agent

**Notes:** Verified 2026-09-13: admin tools 6.6.0.4686 against enrolled clients at 7.3.0.5808 — two major versions apart.

**Evidence added by ticket 02 (2026-09-13): the version gap already changes catalog output.** The
live catalog was built by 6.6.0; rebuilding the same metadata with 7.3.0 produces a byte-different
catalog whose Firefox duplicate pair is ordered the other way round, which changes which installer
a client receives (details in ticket 09). Both builds are individually reproducible, so this is a
tool-version difference. Aligning the toolchain is therefore not bookkeeping: it determines whether
a catalog rebuild is a no-op or a behaviour change. The `SshTarget` publish path already runs
against the checkout on the machine that holds it, so the decision includes *where* the build runs
(see the open host question in the spec).

## Acceptance criteria

- [ ] The admin workstation's Munki tool version and the version running on each client are recorded per machine from observed data.
- [ ] A decision is recorded on the supported version relationship — either the admin tools are brought up to the client major version, or an explicit floor and ceiling are declared with the reason.
- [ ] After any change to the admin tool version, `makecatalogs` is re-run and the resulting catalogs are byte-compared against the pre-change build, with any difference explained item by item.
- [ ] A pilot machine's check-only run after the change is clean, with the resolved manifest and client version recorded.
- [ ] The version relationship decision is written into the specification or an ADR, not left in the ticket.
