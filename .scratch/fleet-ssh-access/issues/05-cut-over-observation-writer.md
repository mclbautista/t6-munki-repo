# 05: Cut the authoritative observation writer over to the admin workstation

**What to build:** `Sixto-5` becomes the single authoritative writer of the fleet observation store, outside the Munki metadata repository. A full run executed there proves that the admin workstation can resolve the approved access records, observe the fleet, append the run atomically, and serve the resulting baseline to the existing read-only consumers.

**Blocked by:** 04: Establish SSH access for the remaining fleet

**Status:** ready-for-human

**Approval gate:** Deploying collector runtime state and authentication-dependent configuration to the facility admin workstation is a system-level change and requires Cyril's confirmation before execution.

**Boundary:** This ticket does not schedule the collector, send alerts, modify Munki policy, install software on clients, or add another observation writer.

- [ ] The current writer locations and observation stores are inventoried before cutover so no concurrent or forgotten writer remains active.
- [ ] The proposed admin-workstation paths, owner, permissions, access-map mechanism, invocation, dependencies, rollback, and recovery procedure are presented and approved before deployment.
- [ ] The authoritative observation store is outside the Git checkout, contains no credentials, is writable only by its declared writer, and preserves the append-only/idempotent guarantees already tested by the repository.
- [ ] The deployed collector revision is identified and matches a committed repository revision; runtime configuration identifies machines without embedding passwords or private-key material.
- [ ] A full run is executed on `Sixto-5`, read back from the exact deployed store, and reconciled programmatically against all 17 expected targets.
- [ ] The read-back distinguishes observed, partial, and unobserved machines, reports staleness, and preserves each transport reason; no unreachable machine appears compliant.
- [ ] Existing read-only observation, toolchain, manifest-resolution, and alert-condition consumers can read the deployed store without gaining write access to it.
- [ ] Any former writer is disabled only after the new run and read-back succeed; rollback restores the previous declared writer and store without deleting either store.
- [ ] The ticket records what was deployed, the committed revision, the live command and host, run totals, exact store location, verification results, and every remaining exception.
