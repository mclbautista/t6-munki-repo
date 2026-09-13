"""The pre-publish gate: what a publish is allowed to change.

The gate exists because a real publish on 2026-09-13 carried an unintended change: the operator
passed the old bypass flag (`--allow-changes`) without reading the diff, and a duplicate-name entry
reordering went live. A publish must now declare what it expects, and everything else is refused.
"""
from conftest import catalog_array, item
from munki_fleet.gate import evaluate_gate


def gate(served_items, built_items, **kwargs):
    kwargs.setdefault("expect_changes", set())
    kwargs.setdefault("expect_new_catalogs", set())
    return evaluate_gate({"all": catalog_array(served_items)}, {"all": catalog_array(built_items)},
                         **kwargs)


def test_a_declared_change_is_allowed():
    decision = gate([item("A", display_name="A")], [item("A", display_name="A (T6)")],
                    expect_changes={("A", "display_name")})
    assert decision.allowed is True, decision.reasons


def test_a_wildcard_declaration_covers_any_key_of_that_item():
    decision = gate([item("A", display_name="A")], [item("A", display_name="A (T6)")],
                    expect_changes={("A", None)})
    assert decision.allowed is True, decision.reasons


def test_an_undeclared_change_is_refused():
    decision = gate([item("A", display_name="A"), item("B", display_name="B")],
                    [item("A", display_name="A (T6)"), item("B", display_name="B (T6)")],
                    expect_changes={("A", "display_name")})
    assert decision.allowed is False
    assert any("B" in r and "display_name" in r for r in decision.reasons)


def test_a_declared_change_that_did_not_happen_is_refused():
    decision = gate([item("A")], [item("A")], expect_changes={("A", "display_name")})
    assert decision.allowed is False
    assert any("did not change" in r for r in decision.reasons)


def test_an_empty_expectation_with_no_changes_is_allowed():
    assert gate([item("A")], [item("A")]).allowed is True


def test_an_undeclared_addition_is_refused():
    decision = gate([item("A")], [item("A"), item("NEW")])
    assert decision.allowed is False
    assert any("added" in r and "NEW" in r for r in decision.reasons)


def test_a_declared_addition_is_allowed():
    decision = gate([item("A")], [item("A"), item("NEW")], expect_additions={"NEW"})
    assert decision.allowed is True, decision.reasons


def test_a_declared_addition_that_did_not_happen_is_refused():
    decision = gate([item("A")], [item("A")], expect_additions={"NEW"})
    assert decision.allowed is False
    assert any("did not appear" in r for r in decision.reasons)


def test_an_undeclared_removal_is_refused():
    decision = gate([item("A"), item("GONE")], [item("A")])
    assert decision.allowed is False
    assert any("removed" in r and "GONE" in r for r in decision.reasons)


def test_a_declared_removal_is_allowed():
    decision = gate([item("A"), item("GONE")], [item("A")], expect_removals={"GONE"})
    assert decision.allowed is True, decision.reasons


def test_a_new_catalog_must_be_declared():
    built_only = evaluate_gate({}, {"all": catalog_array([item("A")])},
                               expect_changes=set(), expect_new_catalogs=set())
    assert built_only.allowed is False
    assert any("new catalog" in r for r in built_only.reasons)
    declared = evaluate_gate({}, {"all": catalog_array([item("A")])},
                             expect_changes=set(), expect_new_catalogs={"all"})
    assert declared.allowed is True, declared.reasons


def test_duplicate_entry_reordering_blocks_by_default():
    dmg = item("Firefox", installer_item_location="Firefox.dmg")
    pkg = item("Firefox", installer_item_location="Firefox.pkg")
    decision = gate([pkg, dmg], [dmg, pkg])
    assert decision.allowed is False
    assert any("order" in r for r in decision.reasons)


def test_duplicate_entry_reordering_is_allowed_when_explicitly_accepted():
    dmg = item("Firefox", installer_item_location="Firefox.dmg")
    pkg = item("Firefox", installer_item_location="Firefox.pkg")
    decision = gate([pkg, dmg], [dmg, pkg], allow_duplicate_order_change=True)
    assert decision.allowed is True, decision.reasons
    assert any("order" in r for r in decision.accepted_risks)


def test_a_resolved_duplicate_must_be_declared():
    """Retiring one of two same-name pkginfos changes the catalog's duplicate set.

    Name-level membership does not change, so a diff that only reports added/removed names would
    let this through — yet it is exactly the change that resolves the Firefox ordering hazard.
    """
    dmg = item("Firefox", installer_item_location="Firefox.dmg")
    pkg = item("Firefox", installer_item_location="Firefox.pkg")
    decision = gate([pkg, dmg], [pkg])
    assert decision.allowed is False
    assert any("duplicate" in r and "Firefox" in r for r in decision.reasons)


def test_a_declared_duplicate_resolution_is_allowed_and_recorded():
    dmg = item("Firefox", installer_item_location="Firefox.dmg")
    pkg = item("Firefox", installer_item_location="Firefox.pkg")
    decision = gate([pkg, dmg], [pkg], expect_duplicates_resolved={"Firefox"})
    assert decision.allowed is True, decision.reasons
    assert any("Firefox" in r for r in decision.accepted_risks)


def test_a_newly_appearing_duplicate_is_refused_even_when_declared():
    """One entry per name and version is the rule; a second one appearing is a defect, not a change."""
    dmg = item("Firefox", installer_item_location="Firefox.dmg")
    pkg = item("Firefox", installer_item_location="Firefox.pkg")
    decision = gate([dmg], [dmg, pkg], expect_duplicates_resolved=set())
    assert decision.allowed is False
    assert any("duplicate" in r.lower() for r in decision.reasons)


def test_an_undeclared_file_change_is_refused():
    """A manifest edit produces no catalog diff at all, so it must be declared as a file."""
    decision = gate([item("A")], [item("A")],
                    file_changes={"manifests/all": "changed"})
    assert decision.allowed is False
    assert any("manifests/all" in r for r in decision.reasons)


def test_a_declared_file_change_is_allowed_and_recorded():
    decision = gate([item("A")], [item("A")], file_changes={"manifests/all": "changed"},
                    expect_files={"manifests/all"})
    assert decision.allowed is True, decision.reasons
    assert any("manifests/all" in r for r in decision.accepted_risks)


def test_an_unreadable_file_is_refused_even_when_declared():
    """A target that cannot be read is not an empty target."""
    decision = gate([item("A")], [item("A")], file_changes={"manifests/all": "unreadable"},
                    expect_files={"manifests/all"})
    assert decision.allowed is False
    assert any("could not read" in r for r in decision.reasons)
