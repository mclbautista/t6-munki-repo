"""The pre-publish gate: what a publish is allowed to change.

Written after a real publish (2026-09-13) that carried an unintended change because the operator
passed the old bypass flag without reading the diff first. The gate replaces the bypass with a
declaration: a publisher must state what it expects to change, and anything else is refused.

It covers four kinds of change, because a catalog can change in ways that a key-by-key diff alone
does not describe:

- **changed keys** on an existing item (`--expect-change Item:key`);
- **added or removed items** — membership changes, which a diff that only reads changed keys would
  otherwise let through silently;
- **reordering of same-name duplicate entries**, which changes which installer a client receives
  while looking like a no-op;
- **any non-catalog file that differs** (`--expect-file path`) — a manifest edit produces no
  catalog diff at all, so it would otherwise publish undeclared.

A target that cannot be read is never treated as an empty target: an unreadable file is refused,
so a transient failure cannot turn into a silently-accepted publish.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .catalogs import CatalogDiff, compare_catalogs

# An expectation is (item, key); key None means "any key of that item".
Expectation = Tuple[str, Optional[str]]
# A file-level change is described by path and kind: changed, added, removed, or unreadable.
FileChange = Tuple[str, str]


@dataclass
class GateDecision:
    allowed: bool = True
    reasons: List[str] = field(default_factory=list)
    accepted_risks: List[str] = field(default_factory=list)
    diffs: Dict[str, CatalogDiff] = field(default_factory=dict)

    def describe(self) -> str:
        lines = []
        for name, diff in sorted(self.diffs.items()):
            lines.append(f"catalogs/{name}: {diff.describe()}")
        lines += [f"REFUSED: {r}" for r in self.reasons]
        lines += [f"ACCEPTED RISK: {r}" for r in self.accepted_risks]
        return "\n".join(lines)


def _observed_changes(diffs: Dict[str, CatalogDiff]) -> Set[Expectation]:
    observed: Set[Expectation] = set()
    for diff in diffs.values():
        for item, keys in diff.changed.items():
            for key in keys:
                observed.add((item, key))
    return observed


def _satisfied_by(observed: Expectation, declared: Set[Expectation]) -> bool:
    item, key = observed
    return (item, key) in declared or (item, None) in declared


def evaluate_gate(served: Dict[str, bytes], built: Dict[str, bytes],
                  expect_changes: Set[Expectation] = frozenset(),
                  expect_new_catalogs: Set[str] = frozenset(),
                  expect_additions: Set[str] = frozenset(),
                  expect_removals: Set[str] = frozenset(),
                  file_changes: Optional[Dict[str, str]] = None,
                  expect_files: Set[str] = frozenset(),
                  allow_duplicate_order_change: bool = False) -> GateDecision:
    """Decide whether a publish may proceed, and say why not when it may not."""
    decision = GateDecision()
    file_changes = file_changes or {}

    new_catalogs = sorted(name for name in built if name not in served)
    for name in new_catalogs:
        if name in expect_new_catalogs:
            decision.accepted_risks.append(f"catalogs/{name} does not exist on the target yet")
        else:
            decision.reasons.append(
                f"new catalog not declared: catalogs/{name} — declare with --expect-new-catalog"
            )

    for name in sorted(set(built) & set(served)):
        decision.diffs[name] = compare_catalogs(served[name], built[name])

    observed = _observed_changes(decision.diffs)
    for change in sorted(observed):
        if not _satisfied_by(change, expect_changes):
            item, key = change
            decision.reasons.append(
                f"undeclared change to {item}: {key} — declare it with --expect-change {item}:{key}"
            )
    for declared in sorted(expect_changes):
        item, key = declared
        if not [c for c in observed if c[0] == item and (key is None or c[1] == key)]:
            decision.reasons.append(
                f"declared change {item}:{key if key else '*'} did not change in the built catalogs"
            )

    added = sorted({name for diff in decision.diffs.values() for name in diff.added})
    removed = sorted({name for diff in decision.diffs.values() for name in diff.removed})
    for name in added:
        if name not in expect_additions:
            decision.reasons.append(
                f"undeclared item added to the catalog: {name} — declare it with --expect-add {name}"
            )
    for name in removed:
        if name not in expect_removals:
            decision.reasons.append(
                f"undeclared item removed from the catalog: {name} — declare it with "
                f"--expect-remove {name}"
            )
    for declared in sorted(expect_additions):
        if declared not in added:
            decision.reasons.append(f"declared addition {declared} did not appear in the catalogs")
    for declared in sorted(expect_removals):
        if declared not in removed:
            decision.reasons.append(f"declared removal {declared} did not happen")

    order_changed = sorted({name for diff in decision.diffs.values()
                            for name in diff.duplicate_order_changed})
    if order_changed and not allow_duplicate_order_change:
        decision.reasons.append(
            "duplicate-name entry order changed for " + ", ".join(order_changed)
            + " — Munki takes the first match, so this changes which installer a client receives; "
              "resolve the duplicate instead, or accept it explicitly with "
              "--allow-duplicate-order-change"
        )
    elif order_changed:
        decision.accepted_risks.append(
            "duplicate-name entry order changed for " + ", ".join(order_changed)
            + " — accepted explicitly by the operator"
        )

    for path, kind in sorted(file_changes.items()):
        if kind == "unreadable":
            decision.reasons.append(
                f"could not read {path} from the target — refusing to publish while the target's "
                f"state is unknown"
            )
        elif path not in expect_files:
            decision.reasons.append(
                f"undeclared {kind} file: {path} — declare it with --expect-file {path}"
            )
        else:
            decision.accepted_risks.append(f"declared {kind} file: {path}")

    decision.allowed = not decision.reasons
    return decision
