# 0012: Write selected fleet facts to matched Bays records

- **Status:** Accepted as the scope of issue #6; live writes remain subject to the project's approval boundaries.

## Context

The identity check compares the authoritative identity inventory and manifests against the Bays
projection. Those systems can drift, while operators use Bays to find fleet facts. ADR 0004 keeps
Bays as a projection rather than a source of machine identity.

## Decision

Munki tooling may use `t6.notion` to write three known facts to an existing matching Bays row:
`Serial Number` from the identity inventory, `Munki Manifest` from the machine manifest, and `Ring`
from the declared pilot ring (ADR 0003). It uses the identity check's name normalization and candidate
names but, unlike that read-only check's first-match precedence, refuses any competing normalized
matches. It skips unmatched or ambiguous machines instead of creating rows, and leaves unknown fields
untouched.

A dry run is the default and reports the match and old and new values. An explicit `--apply` is
required to write; unchanged fields must not be written. The identity check continues to read the
Bays projection, and the observation store remains the authoritative record of observations. This
amends ADR 0004 only to allow the specified Bays projection writes, not to make Bays an identity
source or relax its other boundaries.

## Amendment 2026-11-14: through `t6.fleet`

Under the consumer contract (t6-core#115), this repo no longer calls `t6.notion` or names a Bays
property. `bays-writeback` builds the machine facts from the inventory and rings data and calls
`t6.fleet`, which owns the matching, the dry run, the write and the field mapping. The rules above
still hold. With `--store`, the command also writes `Munki Client Version`, `Last Check-in` (Munki's
own last run time, not the probe time) and `OS Version` from the newest observation per machine
(`probe.latest_per_machine`); an unreachable, missing or stale observation leaves the existing
values and the dry run says why.

## Consequences

Bays can reflect selected facts without changing fleet clients or Munki metadata. A write is an
external change: review the dry run and obtain any required operational approval before applying it.
No guarantee is made that unobserved facts are current or that external changes are atomic.

## Rollback

Disable write-back and restore affected Bays values from the recorded prior values after review.
Do not blank fields merely because the inventory lacks a value.
