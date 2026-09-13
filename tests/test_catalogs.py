"""Catalog building and the item-level diff."""
import pytest

from conftest import catalog_array, catalog_dict, catalog_runner, item
from munki_fleet.catalogs import CatalogError, build_catalogs, compare_catalogs


class FailingRunner:
    def __call__(self, metadata_root):
        return 1


def test_build_catalogs_invokes_the_runner_with_the_metadata_root(tmp_path):
    runner = catalog_runner({"all": [item("A")], "testing": [item("A")]})
    result = build_catalogs(str(tmp_path), runner=runner)
    assert sorted(result.catalogs) == ["all", "testing"]


def test_build_catalogs_surfaces_a_failing_runner(tmp_path):
    with pytest.raises(CatalogError):
        build_catalogs(str(tmp_path), runner=FailingRunner())


def test_build_catalogs_rejects_a_build_that_produced_nothing(tmp_path):
    with pytest.raises(CatalogError):
        build_catalogs(str(tmp_path), runner=lambda root: 0)


def test_compare_catalogs_is_empty_for_identical_input():
    same = catalog_dict([item("A"), item("B")])
    assert compare_catalogs(same, same).is_empty()


def test_compare_catalogs_names_the_item_and_the_changed_key():
    old = catalog_dict([item("A", display_name="A"), item("B")])
    new = catalog_dict([item("A", display_name="A (T6)"), item("B")])
    diff = compare_catalogs(old, new)
    assert diff.changed == {"A": ["display_name"]}
    assert diff.added == [] and diff.removed == []


def test_compare_catalogs_reports_membership_changes():
    diff = compare_catalogs(catalog_dict([item("A")]), catalog_dict([item("B")]))
    assert diff.added == ["B"] and diff.removed == ["A"]
    assert diff.has_item_changes() is True


def test_compare_catalogs_accepts_the_top_level_array_shape():
    """makecatalogs writes items as a top-level array; the dict shape also occurs in the wild."""
    old = catalog_array([item("A"), item("B", display_name="B")])
    new = catalog_array([item("A"), item("B", display_name="B (T6)")])
    assert compare_catalogs(old, new).changed == {"B": ["display_name"]}


def test_compare_catalogs_rejects_an_unreadable_catalog():
    with pytest.raises(CatalogError):
        compare_catalogs(b"not a plist", catalog_dict([item("A")]))


def test_compare_catalogs_separates_reordering_from_real_change():
    """Two pkginfos share the Firefox name in the live repository; a rebuild can swap their order.

    Munki takes the first entry matching a name, so an order swap changes which installer a client
    receives. It must be reported as an order change, not as a dozen changed keys.
    """
    dmg = item("Firefox", installer_item_location="Firefox.dmg", installer_type="copy_from_dmg")
    pkg = item("Firefox", installer_item_location="Firefox.pkg")
    diff = compare_catalogs(catalog_array([pkg, dmg]), catalog_array([dmg, pkg]))
    assert diff.duplicate_order_changed == ["Firefox"]
    assert diff.changed == {}, f"reordering is not a key change: {diff.changed}"
    assert diff.duplicate_names == ["Firefox"]


def test_compare_catalogs_still_reports_a_changed_duplicate_entry():
    dmg = item("Firefox", installer_item_location="Firefox.dmg")
    other = item("Firefox", installer_item_location="Firefox.pkg")
    changed = item("Firefox", installer_item_location="Firefox.pkg", installer_item_hash="deadbeef")
    diff = compare_catalogs(catalog_array([dmg, other]), catalog_array([dmg, changed]))
    assert diff.duplicate_order_changed == []
    assert diff.changed == {"Firefox": ["installer_item_hash"]}
