"""The pre-publish gate: what a publish is allowed to change.

Written after a real publish (2026-09-13) that carried an unintended change because the operator
passed the bypass flag without reading the diff first. The gate replaces the bypass with a
declaration: a publisher must state which items and keys it expects to change, and the tool
refuses anything else — including a duplicate-name entry reordering, which silently changes which
installer a client receives.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .catalogs import CatalogDiff, compare_catalogs

# An expectation is (item, key); key None means "any key of that item".
Expectation = Tuple[str, Optional[str]]


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
                  expect_changes: Set[Expectation], expect_new_catalogs: Set[str],
                  allow_duplicate_order_change: bool = False) -> GateDecision:
    """Decide whether a publish may proceed, and say why not when it may not."""
    decision = GateDecision()

    new_catalogs = sorted(name for name in built if name not in served)
    undeclared_new = [name for name in new_catalogs if name not in expect_new_catalogs]
    if undeclared_new:
        decision.reasons.append(
            f"new catalog(s) not declared: {', '.join(undeclared_new)} — "
            f"declare with --expect-new-catalog"
        )
    for name in new_catalogs:
        if name in expect_new_catalogs:
            decision.accepted_risks.append(f"catalogs/{name} does not exist on the target yet")

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
        matches = [c for c in observed if c[0] == item and (key is None or c[1] == key)]
        if not matches:
            decision.reasons.append(
                f"declared change {item}:{key if key else '*'} did not change in the built catalogs"
            )

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

    decision.allowed = not decision.reasons
    return decision
