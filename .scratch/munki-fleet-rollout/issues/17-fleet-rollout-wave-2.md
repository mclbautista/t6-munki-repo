# 17: Roll out to the remaining fleet, including the machines nobody remembers are on it

**What to build:** The rest of the fleet brought under the same policy and the same observation, including the admin workstation and any machine the inventory surfaced as unregistered — so that "the fleet" finally means every Mac T6 actually runs.

**Blocked by:** 16

**Approval gate:** Applying policy fleet-wide changes what every remaining Mac receives and requires Cyril's confirmation of the wave before execution.

**Status:** ready-for-agent

**Notes:** This ticket is the project's definition of done for rollout: after it, every Mac is accounted for and observed.

## Acceptance criteria

- [ ] The wave covers the machines not completed in wave 1 (proposed: online, client-facing, dit, sound, internships, coordination-admin, plus the admin workstation and Cyril's Mac mini) and Cyril confirms the wave before it runs.
- [ ] Machines the inventory found with no record, or with records that disagreed, are resolved in this ticket with the decision recorded per machine.
- [ ] Every machine in the fleet has exactly one machine manifest, exactly one inventory record, and at least one observation newer than the wave's start — or is listed as unobserved with a reason.
- [ ] No machine anywhere in the fleet resolves `site_default`, asserted from observed data rather than from configuration.
- [ ] The final counts reconcile: machines in the role matrix = machine manifests = inventory records = machines with a fresh observation, or the difference is explained per machine.
- [ ] The fleet's state at the end of the wave is recorded as the new baseline in the specification.
