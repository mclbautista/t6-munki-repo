# 0012: Write selected fleet facts to matched Bays records

- **Status:** Accepted as the scope of issue #6; live writes remain subject to the project's approval boundaries.

## Context

The identity check compares the authoritative identity inventory and manifests against the Bays
projection. Those systems can drift, while operators use Bays to find fleet facts. ADR 0004 keeps
Bays as a projection rather than a source of machine identity.

## Decision

Munki tooling may use `t6.notion` to write three known facts to an existing matching Bays row:
`Serial Number` from the identity inventory, `Munki Manifest` from the machine manifest, and `Ring`
from the declared pilot ring (ADR 0003). It must use the identity check's matching rules, skip
unmatched or ambiguous machines instead of creating rows, and leave unknown fields untouched.

A dry run is the default and reports the match and old and new values. An explicit `--apply` is
required to write; unchanged fields must not be written. The identity check continues to read the
Bays projection, and the observation store remains the authoritative record of observations. This
amends ADR 0004 only to allow the specified Bays projection writes, not to make Bays an identity
source or relax its other boundaries.

## Consequences

Bays can reflect selected facts without changing fleet clients or Munki metadata. A write is an
external change: review the dry run and obtain any required operational approval before applying it.
No guarantee is made that unobserved facts are current or that external changes are atomic.

## Rollback

Disable write-back and restore affected Bays values from the recorded prior values after review.
Do not blank fields merely because the inventory lacks a value.
