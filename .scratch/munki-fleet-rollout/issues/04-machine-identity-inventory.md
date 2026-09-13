# 04: One authoritative inventory of which Mac is which

**What to build:** A reconciled inventory of the fleet: every Mac's name, Munki short hostname, serial number, hardware UUID, architecture, and assigned role — cross-checked against the role matrix and the set of machine manifests, with every mismatch reported.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

**Notes:** The live repository's manifest set is evidence of intent, not evidence of reality: a manifest existing for a hostname does not prove a machine with that hostname exists. Both directions must be checked.

## Acceptance criteria

- [ ] Identity is sourced from the Apple Remote Desktop machine export (name, serial, UUID, MAC, OS version, known addresses); the source file used and its export date are recorded.
- [ ] The 16 role-matrix machines are present with their expected Munki short hostname and assigned role; the Mac Mini admin workstation and Cyril's Mac mini are present as fleet members in their own right.
- [ ] Every manifest filename in the repository is matched to an inventoried machine, and every inventoried machine to a manifest — both directions reported.
- [ ] Mismatches are listed as findings with a proposed correction: hostname differences (including names containing spaces), machines with a manifest but no inventory record, inventory records with no manifest, and role-matrix machines that are unassigned.
- [ ] Machines known to exist but absent from the engineering export are reported as needing a record, never guessed.
- [ ] The inventory is stored in a form the observer (ticket 05) reads as its identity input, and the T6 operational Bays records are reconciled against it as a projection whose differences are reported, not silently applied.
