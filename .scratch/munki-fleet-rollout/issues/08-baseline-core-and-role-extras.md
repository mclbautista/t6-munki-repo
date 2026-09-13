# 08: A short forced baseline and role groups that mean something

**What to build:** Fleet software policy as three tiers — a small forced core on every Mac, everything else approved offered as optional and kept patched, and role-specific tools offered only to the roles that use them.

**Blocked by:** 07

**Approval gate:** Cyril confirms or amends the forced core list before it takes effect. Initial proposal: TeamViewer, AnyDesk, RemotePC, Remote Desktop, Google Chrome, Telegram, Notion.

**Status:** ready-for-agent

**Notes:** Role extras are proposed per group in this ticket and confirmed before publishing.

## Acceptance criteria

- [ ] The forced core is listed explicitly in the specification and matches what is in the manifests; nothing else is force-installed.
- [ ] Every approved non-core item appears as optional, and approved optional items are also listed for managed updates so already-installed copies stay patched.
- [ ] Each of the 9 role groups expresses that role's tool set and adds nothing to the forced core; a test asserts no role group declares a forced install.
- [ ] No deferred vendor suite appears in any manifest section, asserted by a test that searches every manifest section for them.
- [ ] No item is listed in two conflicting sections of one effective manifest, asserted per machine from the resolved chain.
- [ ] On the pilot machines the change is verified end to end: the core is present, an optional item appears as available rather than installed, and a role extra does not appear for a machine outside that role.
- [ ] The before/after of what each pilot machine would install is recorded as evidence.
