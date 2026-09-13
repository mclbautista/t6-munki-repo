# 06: Close the manifest resolution gaps the inventory exposes

**What to build:** Every inventoried Mac resolving the manifest it is supposed to resolve — including the admin workstation that currently falls back to `site_default`, the orphaned group manifests nobody inherits, and the production machine enrolled under a test identifier.

**Blocked by:** 05

**Approval gate:** Cyril approves the manifest assignment for the admin workstation and Cyril's Mac mini, because both changes alter what those machines receive.

**Status:** ready-for-human

## Acceptance criteria

- [ ] The Mac Mini admin workstation no longer falls back to `site_default`: it has a machine manifest, and the change to what it receives is approved before it is applied.
- [ ] Cyril's Mac mini is no longer identified by a test ClientIdentifier; it resolves its own machine manifest.
- [ ] The orphaned group manifests (the `production` group and the test-client group) are either placed in service with a documented purpose or retired — with the decision recorded.
- [ ] Resolution is verified per machine from observed data: every inventoried Mac reports a resolved manifest name that is its own machine manifest, not `site_default` and not a group.
- [ ] Any machine whose hostname does not match its manifest filename is corrected or the manifest renamed, whichever the inventory evidence supports, and the correction is recorded.
- [ ] Before/after evidence is recorded per machine affected.
