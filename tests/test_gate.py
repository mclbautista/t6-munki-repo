"""Tests for the pre-publish gate: what a publish is allowed to change.

Written after a real publish on 2026-09-13 that carried an unintended Firefox entry reordering
because the operator bypassed an unread diff. The gate exists so that cannot happen again: a
publish must state what it expects to change, and the tool refuses anything else.
"""
import plistlib

from munki_fleet.gate import evaluate_gate


def make_catalog(items):
    return plistlib.dumps({"items": items})


def as_array(items):
    return plistlib.dumps(items)


def item(name, version="1.0", **extra):
    d = {"name": name, "version": version, "catalogs": ["testing"],
         "installer_item_location": f"{name}.dmg"}
    d.update(extra)
    return d


def test_a_declared_change_is_allowed():
    served = {"all": as_array([item("A", display_name="A")]),
              "testing": as_array([item("A", display_name="A")])}
    built = {"all": as_array([item("A", display_name="A (T6)")]),
             "testing": as_array([item("A", display_name="A (T6)")])}
    decision = evaluate_gate(served, built, expect_changes={("A", "display_name")},
                             expect_new_catalogs=set(), allow_duplicate_order_change=False)
    assert decision.allowed is True, decision.reasons


def test_an_undeclared_change_is_refused():
    served = {"all": as_array([item("A", display_name="A"), item("B", display_name="B")])}
    built = {"all": as_array([item("A", display_name="A (T6)"),
                              item("B", display_name="B (T6)")])}
    decision = evaluate_gate(served, built, expect_changes={("A", "display_name")},
                             expect_new_catalogs=set(), allow_duplicate_order_change=False)
    assert decision.allowed is False
    assert any("B" in r and "display_name" in r for r in decision.reasons)


def test_a_declared_change_that_did_not_happen_is_refused():
    served = {"all": as_array([item("A")])}
    built = {"all": as_array([item("A")])}
    decision = evaluate_gate(served, built, expect_changes={("A", "display_name")},
                             expect_new_catalogs=set(), allow_duplicate_order_change=False)
    assert decision.allowed is False
    assert any("did not change" in r for r in decision.reasons)


def test_an_empty_expectation_with_no_changes_is_allowed():
    served = {"all": as_array([item("A")])}
    built = {"all": as_array([item("A")])}
    decision = evaluate_gate(served, built, expect_changes=set(),
                             expect_new_catalogs=set(), allow_duplicate_order_change=False)
    assert decision.allowed is True, decision.reasons


def test_a_new_catalog_must_be_declared():
    built = {"all": as_array([item("A")])}
    decision = evaluate_gate({}, built, expect_changes=set(),
                             expect_new_catalogs=set(), allow_duplicate_order_change=False)
    assert decision.allowed is False
    assert any("new" in r for r in decision.reasons)
    allowed = evaluate_gate({}, built, expect_changes=set(),
                            expect_new_catalogs={"all"}, allow_duplicate_order_change=False)
    assert allowed.allowed is True, allowed.reasons


def test_duplicate_entry_reordering_blocks_by_default():
    dmg = item("Firefox", installer_item_location="Firefox.dmg")
    pkg = item("Firefox", installer_item_location="Firefox.pkg")
    decision = evaluate_gate({"all": as_array([pkg, dmg])}, {"all": as_array([dmg, pkg])},
                             expect_changes=set(), expect_new_catalogs=set(),
                             allow_duplicate_order_change=False)
    assert decision.allowed is False
    assert any("order" in r for r in decision.reasons)


def test_duplicate_entry_reordering_is_allowed_when_explicitly_accepted():
    dmg = item("Firefox", installer_item_location="Firefox.dmg")
    pkg = item("Firefox", installer_item_location="Firefox.pkg")
    decision = evaluate_gate({"all": as_array([pkg, dmg])}, {"all": as_array([dmg, pkg])},
                             expect_changes=set(), expect_new_catalogs=set(),
                             allow_duplicate_order_change=True)
    assert decision.allowed is True, decision.reasons
    assert any("order" in r for r in decision.accepted_risks)
