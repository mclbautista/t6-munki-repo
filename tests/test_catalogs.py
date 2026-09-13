"""Tests for catalog building and the pre-publish catalog diff guard."""
import plistlib

import pytest

from munki_fleet.catalogs import CatalogError, build_catalogs, compare_catalogs


class FakeRunner:
    def __init__(self, catalog_names=("all", "testing"), returns=0):
        self.calls = []
        self.catalog_names = catalog_names
        self.returns = returns

    def __call__(self, metadata_root, skip_pkg_check=True):
        self.calls.append({"metadata_root": metadata_root, "skip_pkg_check": skip_pkg_check})
        return self.returns


def make_catalog(items):
    return plistlib.dumps({"items": items})


def item(name, version="1.0", **extra):
    d = {"name": name, "version": version, "catalogs": ["testing"], "installer_item_location": f"{name}.dmg"}
    d.update(extra)
    return d


def test_build_catalogs_invokes_the_runner_with_the_metadata_root(tmp_path):
    (tmp_path / "catalogs").mkdir()
    (tmp_path / "catalogs" / "all").write_bytes(make_catalog([item("A")]))
    runner = FakeRunner()
    result = build_catalogs(str(tmp_path), runner=runner)
    assert runner.calls == [{"metadata_root": str(tmp_path), "skip_pkg_check": True}]
    assert "all" in result.catalogs


def test_build_catalogs_surfaces_a_failing_runner(tmp_path):
    runner = FakeRunner(returns=1)
    with pytest.raises(CatalogError):
        build_catalogs(str(tmp_path), runner=runner)


def test_compare_catalogs_reports_no_changes_for_identical_input():
    same = make_catalog([item("A"), item("B")])
    assert compare_catalogs(same, same).is_empty()


def test_compare_catalogs_names_the_item_and_the_changed_key():
    old = make_catalog([item("A", display_name="A"), item("B")])
    new = make_catalog([item("A", display_name="A (T6)"), item("B")])
    diff = compare_catalogs(old, new)
    assert diff.is_empty() is False
    assert diff.changed == {"A": ["display_name"]}
    assert diff.added == [] and diff.removed == []


def test_compare_catalogs_reports_added_and_removed_items():
    diff = compare_catalogs(make_catalog([item("A")]), make_catalog([item("B")]))
    assert diff.added == ["B"] and diff.removed == ["A"]


def test_compare_catalogs_accepts_a_top_level_array_catalog():
    """makecatalogs writes the items as a top-level array, not under an `items` key.

    Verified against the live repository on 2026-09-13: catalogs/all parses as a list of item
    dicts. The dict-with-`items` shape is also accepted because both appear in the wild.
    """
    old = plistlib.dumps([item("A"), item("B", display_name="B")])
    new = plistlib.dumps([item("A"), item("B", display_name="B (T6)")])
    diff = compare_catalogs(old, new)
    assert diff.changed == {"B": ["display_name"]}
    assert diff.added == [] and diff.removed == []


def test_compare_catalogs_rejects_an_unreadable_catalog():
    with pytest.raises(CatalogError):
        compare_catalogs(b"not a plist", make_catalog([item("A")]))


def test_compare_catalogs_separates_reordering_from_real_change():
    """The live repository has two Firefox pkginfos; a rebuild can swap their catalog order.

    Munki takes the first match for a name, so an order swap changes which installer a client
    receives. It must be reported as an order change — not as a dozen changed keys, and not as
    nothing at all.
    """
    dmg = item("Firefox", installer_item_location="Firefox.dmg", installer_type="copy_from_dmg")
    pkg = item("Firefox", installer_item_location="Firefox.pkg")
    before = plistlib.dumps([pkg, dmg])
    after = plistlib.dumps([dmg, pkg])
    diff = compare_catalogs(before, after)
    assert diff.duplicate_order_changed == ["Firefox"]
    assert diff.changed == {}, f"reordering is not a key change: {diff.changed}"


def test_compare_catalogs_still_reports_a_changed_duplicate_entry():
    dmg = item("Firefox", installer_item_location="Firefox.dmg")
    other = item("Firefox", installer_item_location="Firefox.pkg")
    changed = item("Firefox", installer_item_location="Firefox.pkg", installer_item_hash="deadbeef")
    diff = compare_catalogs(plistlib.dumps([dmg, other]), plistlib.dumps([dmg, changed]))
    assert diff.duplicate_order_changed == []
    assert diff.changed == {"Firefox": ["installer_item_hash"]}


def test_compare_catalogs_flags_duplicate_names_as_a_defect():
    """The live repository has two pkginfos for the same name+version; a diff must not hide it."""
    diff = compare_catalogs(make_catalog([item("A"), item("A", installer_item_location="A.pkg")]),
                            make_catalog([item("A")]))
    assert diff.duplicate_names == ["A"]
