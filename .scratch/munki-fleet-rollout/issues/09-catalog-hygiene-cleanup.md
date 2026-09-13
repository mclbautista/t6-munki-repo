# 09: Clean the repository's inherited mess

**What to build:** The repository's pre-existing defects removed at the source, so what is served matches what is intended: duplicate catalog entries, mixed pkginfo conventions, a test artifact in a client-facing manifest, deferred software offered to every client, and the stale share that shadows the repository's name.

**Blocked by:** 07

**Approval gate:** Every deletion in this ticket requires Cyril's approval before execution (ADR 0008), and the share removal is a NAS configuration change.

**Status:** ready-for-human

**Notes:** Cleanup runs after the promotion path exists so nothing reaches the fleet mid-cleanup.

## Acceptance criteria

- [ ] Duplicate name+version catalog entries are eliminated, with the surviving entry's payload and hash the one that is actually installed.
- [ ] The test artifact item is removed from every manifest section, and its pkginfo is retired from the repository.
- [ ] Deferred vendor suites are removed from `site_default`'s optional list and appear in no manifest section.
- [ ] The staged-but-unmanaged nested `apps` area is resolved: each item is either fully imported into the standard layout or withdrawn, and the decision for each is recorded.
- [ ] All pkginfos follow one declared extension convention, and the nested directories no longer split the repository's layout.
- [ ] The stale, empty NAS share that shadows the repository's name is removed so it cannot be mistaken for the repository.
- [ ] After cleanup the drift check reports clean, both catalogs build, and every manifest's items resolve with an existing payload.
