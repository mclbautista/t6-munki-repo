# 16: Roll out to the first wave beyond the pilot ring

**What to build:** The policy and manifests proven on the pilot machines applied to a first wave of production Macs, with observed evidence that each one resolves its own manifest and receives what policy says it should.

**Blocked by:** 08, 10, 11

**Approval gate:** Applying policy to production Macs changes what they receive and requires Cyril's confirmation of the wave before execution.

**Status:** ready-for-agent

## Acceptance criteria

- [ ] The wave is named explicitly (proposed: the `toc` and `warroom` machines — 202 Mac Pro, 202 TOC M4 Max, 202A Mac Mini M4, 202B Mac Studio) and Cyril confirms it before it runs.
- [ ] For each machine: the resolved manifest is its own machine manifest, the forced core is present, role extras match the role, and nothing is pending that policy does not intend.
- [ ] No architecture rejection appears in any machine's report; a rejection is treated as a defect of this ticket, not of the machine.
- [ ] Each machine's before and after state are recorded from the observation store, by machine name, with observation timestamps.
- [ ] Any machine that could not be observed during the wave is reported as unobserved with the reason and is not counted as complete.
- [ ] The wave's outcome is summarised with what changed per machine and what remains outstanding.
