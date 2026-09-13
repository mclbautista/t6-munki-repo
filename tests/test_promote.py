"""The promotion path: what may move from testing to production, and what must be recorded.

The ring only means something if promotion is (a) refused without evidence and (b) recorded with
enough detail to answer "who let this onto the fleet, on what proof, and when".
"""
import json
import os
import plistlib

import pytest

from conftest import catalog_array, item
from munki_fleet.drift import _iter_pkginfos
from munki_fleet.promote import (PROMOTIONS_PATH, PromotionError, declared_exclusions,
                                 delete_manifest, demote, find_pkginfo,
                                 initial_promotion_plan, load_history, promote,
                                 set_manifest_catalogs, withdraw, write_pkginfo_catalogs)


def metadata_tree(root, items=None, manifests=None, catalogs=("testing",)):
    root = str(root)
    items = items if items is not None else [item("A"), item("B")]
    for idx, entry in enumerate(items):
        pkginfo = dict(entry)
        pkginfo.setdefault("installer_item_location", f"payload-{idx}.dmg")
        write = os.path.join(root, "pkgsinfo", f"{entry['name']}-{idx}.pkginfo")
        os.makedirs(os.path.dirname(write), exist_ok=True)
        with open(write, "wb") as fh:
            plistlib.dump(pkginfo, fh, sort_keys=True)
    for name in catalogs:
        os.makedirs(os.path.join(root, "catalogs"), exist_ok=True)
        with open(os.path.join(root, "catalogs", name), "wb") as fh:
            fh.write(catalog_array(items))
    for name, body in (manifests or {
            "site_default": {"catalogs": ["testing"]},
            "all": {"catalogs": ["testing"], "included_manifests": ["site_default"],
                    "managed_installs": ["A"]},
            "202-TOC-M4-Max": {"catalogs": ["testing"], "included_manifests": ["all"]},
            "202-Mac-Pro-3": {"catalogs": ["testing"], "included_manifests": ["all"]},
    }).items():
        os.makedirs(os.path.join(root, "manifests"), exist_ok=True)
        with open(os.path.join(root, "manifests", name), "wb") as fh:
            plistlib.dump(body, fh, sort_keys=True)
    return root


def catalogs_of(root, name):
    for entry in os.listdir(os.path.join(root, "pkgsinfo")):
        if entry.startswith(name):
            with open(os.path.join(root, "pkgsinfo", entry), "rb") as fh:
                return plistlib.load(fh).get("catalogs")
    raise AssertionError(f"no pkginfo for {name}")


# --- what promotion refuses --------------------------------------------------------------------

def test_promotion_is_refused_without_evidence(tmp_path):
    root = metadata_tree(tmp_path / "src")
    with pytest.raises(PromotionError) as excinfo:
        promote(root, "A", "1.0", approved_by="Cyril", evidence=[])
    assert "evidence" in str(excinfo.value)
    assert catalogs_of(root, "A") == ["testing"], "a refused promotion must change nothing"


def test_promotion_is_refused_without_an_approver(tmp_path):
    root = metadata_tree(tmp_path / "src")
    with pytest.raises(PromotionError):
        promote(root, "A", "1.0", approved_by="", evidence=["pilot run 2026-09-13"])


def test_promotion_is_refused_for_an_unknown_item(tmp_path):
    root = metadata_tree(tmp_path / "src")
    with pytest.raises(PromotionError) as excinfo:
        promote(root, "NOPE", "1.0", approved_by="Cyril", evidence=["x"])
    assert "NOPE" in str(excinfo.value)


def test_promotion_is_refused_for_an_unknown_version(tmp_path):
    root = metadata_tree(tmp_path / "src")
    with pytest.raises(PromotionError):
        promote(root, "A", "9.9", approved_by="Cyril", evidence=["x"])


def test_promotion_is_refused_when_already_promoted(tmp_path):
    root = metadata_tree(tmp_path / "src")
    promote(root, "A", "1.0", approved_by="Cyril", evidence=["pilot run"])
    with pytest.raises(PromotionError) as excinfo:
        promote(root, "A", "1.0", approved_by="Cyril", evidence=["pilot run"])
    assert "already" in str(excinfo.value)


# --- what promotion does, and what it records ---------------------------------------------------

def test_promotion_moves_the_item_and_records_the_event(tmp_path):
    root = metadata_tree(tmp_path / "src")
    record = promote(root, "A", "1.0", approved_by="Cyril",
                     evidence=["202-TOC-M4-Max check-only run, clean, 2026-09-13"],
                     at="2026-09-13T19:00:00+08:00")

    assert catalogs_of(root, "A") == ["production"]
    assert record.item == "A" and record.version == "1.0"
    assert record.from_catalogs == ["testing"] and record.to_catalogs == ["production"]
    assert record.approved_by == "Cyril"
    assert record.evidence == ["202-TOC-M4-Max check-only run, clean, 2026-09-13"]
    assert record.at == "2026-09-13T19:00:00+08:00"

    lines = open(os.path.join(root, PROMOTIONS_PATH)).read().splitlines()
    assert len(lines) == 1
    stored = json.loads(lines[0])
    for field in ("item", "version", "at", "approved_by", "evidence", "from_catalogs",
                  "to_catalogs", "pkginfo_path", "pkginfo_sha256"):
        assert field in stored, f"the record must carry {field}"
    assert stored["pkginfo_sha256"] == record.pkginfo_sha256


def test_promotion_history_is_append_only(tmp_path):
    root = metadata_tree(tmp_path / "src")
    promote(root, "A", "1.0", approved_by="Cyril", evidence=["e1"], at="T1")
    promote(root, "B", "1.0", approved_by="Cyril", evidence=["e2"], at="T2")
    history = load_history(root)
    assert [r.item for r in history] == ["A", "B"]


def test_demotion_puts_the_item_back_and_records_a_reason(tmp_path):
    root = metadata_tree(tmp_path / "src")
    promote(root, "A", "1.0", approved_by="Cyril", evidence=["e"], at="T1")
    record = demote(root, "A", "1.0", approved_by="Cyril", reason="install failed on the pilot",
                    at="T2")
    assert catalogs_of(root, "A") == ["testing"]
    assert record.action == "demote" and "failed" in record.reason
    assert [r.action for r in load_history(root)] == ["promote", "demote"]


def test_find_pkginfo_reports_where_the_item_lives(tmp_path):
    root = metadata_tree(tmp_path / "src")
    path, pkginfo = find_pkginfo(root, "A", "1.0")
    assert path.endswith("A-0.pkginfo") and pkginfo["name"] == "A"


# --- withdrawal: the other ending an item can have ---------------------------------------------

def test_withdrawal_strips_the_item_from_every_manifest_section(tmp_path):
    root = metadata_tree(tmp_path / "src", items=[item("Keep"), item("Gone")], manifests={
        "site_default": {"catalogs": ["testing"],
                         "optional_installs": ["Keep", "Gone", "AlsoGone"]},
        "all": {"catalogs": ["testing"], "included_manifests": ["site_default"],
                "managed_installs": ["Keep", "Gone"]},
    })
    removed = withdraw(root, ["Gone"], approved_by="Cyril", reason="not deployed at T6")
    assert removed == ["Gone"]

    def body(name):
        with open(os.path.join(root, "manifests", name), "rb") as fh:
            return plistlib.load(fh)

    assert body("site_default")["optional_installs"] == ["Keep", "AlsoGone"], \
        "only the withdrawn item may leave, and an unrelated string must survive"
    assert body("all")["managed_installs"] == ["Keep"]
    assert [p["name"] for _, p in _iter_pkginfos(root)] == ["Keep"], \
        "the withdrawn pkginfo goes, the other stays"


def test_withdrawal_deletes_the_pkginfos_and_records_why(tmp_path):
    root = metadata_tree(tmp_path / "src")
    removed = withdraw(root, None, approved_by="Cyril", reason="withdrawing per 2026-09-13 decision")

    remaining = [os.path.basename(p) for p, _ in _iter_pkginfos(root)]
    assert remaining == [], f"expected an empty tree, found {remaining}"
    lines = open(os.path.join(root, "data", "withdrawals.jsonl")).read().splitlines()
    assert len(lines) == 2, "one record per removed pkginfo"
    stored = json.loads(lines[0])
    for field_ in ("item", "version", "kind", "at", "approved_by", "reason",
                   "source_path", "source_sha256"):
        assert field_ in stored, f"the record must carry {field_}"
    assert stored["kind"] == "pkginfo"
    assert stored["source_sha256"], "the record must name the bytes it removed"


def test_withdrawal_is_refused_without_a_reason(tmp_path):
    root = metadata_tree(tmp_path / "src")
    with pytest.raises(PromotionError) as excinfo:
        withdraw(root, None, approved_by="Cyril", reason="  ")
    assert "why" in str(excinfo.value)
    assert len(list(_iter_pkginfos(root))) == 2, "a refused withdrawal must change nothing"


def test_withdrawal_is_refused_without_an_approver(tmp_path):
    root = metadata_tree(tmp_path / "src")
    with pytest.raises(PromotionError):
        withdraw(root, None, approved_by="", reason="cleanup")


def test_withdrawal_of_a_named_item_leaves_the_others(tmp_path):
    root = metadata_tree(tmp_path / "src")
    withdraw(root, ["A"], approved_by="Cyril", reason="withdrawn")
    assert [p["name"] for _, p in _iter_pkginfos(root)] == ["B"]


def test_withdrawal_refuses_an_item_that_is_not_there(tmp_path):
    root = metadata_tree(tmp_path / "src")
    with pytest.raises(PromotionError) as excinfo:
        withdraw(root, ["Nonexistent"], approved_by="Cyril", reason="typo")
    assert "Nonexistent" in str(excinfo.value)


def test_deleting_a_manifest_is_recorded_as_its_own_kind(tmp_path):
    root = metadata_tree(tmp_path / "src")
    delete_manifest(root, "202-Mac-Pro-3")
    assert not os.path.exists(os.path.join(root, "manifests", "202-Mac-Pro-3"))
    stored = json.loads(open(os.path.join(root, "data", "withdrawals.jsonl")).read().splitlines()[0])
    assert stored["kind"] == "manifest" and stored["item"] == "202-Mac-Pro-3"
    assert stored["source_sha256"], "the record must name the bytes it removed"


# --- exclusions are declared, not remembered ----------------------------------------------------

def test_the_declared_exclusions_are_read_from_the_ring_file(tmp_path):
    root = metadata_tree(tmp_path / "src")
    os.makedirs(os.path.join(root, "data"), exist_ok=True)
    with open(os.path.join(root, "data", "rings.json"), "w") as fh:
        json.dump({"pilots": [{"name": "202-TOC-M4-Max"}],
                   "promotion_exclusions": [
                       {"item": "Parked", "why": "on the deferred list", "decided": "Cyril"}],
                   }, fh)
    assert declared_exclusions(root) == ["Parked"]
    plan = initial_promotion_plan(root, pilots=("202-TOC-M4-Max",),
                                 exclude=declared_exclusions(root))
    assert [i.name for i in plan.items] == ["A", "B"], "the declared exclusion must apply"


# --- the initial promotion: one event, nothing lost ---------------------------------------------

def test_the_initial_plan_promotes_everything_that_is_live_and_reassigns_the_manifests(tmp_path):
    root = metadata_tree(tmp_path / "src")
    plan = initial_promotion_plan(root, pilots=("202-TOC-M4-Max",))
    assert sorted((i.name, i.version) for i in plan.items) == [("A", "1.0"), ("B", "1.0")]
    assert plan.manifest_changes["202-TOC-M4-Max"] == (["testing"], ["testing", "production"])
    assert plan.manifest_changes["202-Mac-Pro-3"] == (["testing"], ["production"])
    assert plan.manifest_changes["all"] == (["testing"], ["production"])
    assert plan.manifest_changes["site_default"] == (["testing"], ["production"])


def test_the_initial_plan_is_empty_when_there_is_nothing_left_to_promote(tmp_path):
    root = metadata_tree(tmp_path / "src", items=[item("A", catalogs=["production"])])
    plan = initial_promotion_plan(root, pilots=("202-TOC-M4-Max",))
    assert plan.items == []


def test_setting_manifest_catalogs_edits_only_the_catalogs_array(tmp_path):
    root = metadata_tree(tmp_path / "src")
    path = os.path.join(root, "manifests", "202-TOC-M4-Max")
    before = open(path, "rb").read()
    set_manifest_catalogs(path, ["testing", "production"])
    after = open(path, "rb").read()
    with open(path, "rb") as fh:
        body = plistlib.load(fh)
    assert body["catalogs"] == ["testing", "production"]
    assert body["included_manifests"] == ["all"], "nothing else may change"
    assert b"included_manifests" in after and len(after) > len(before) - 40


def test_setting_manifest_catalogs_refuses_a_manifest_with_no_catalogs_key(tmp_path):
    root = metadata_tree(tmp_path / "src")
    path = os.path.join(root, "manifests", "no-catalogs")
    with open(path, "wb") as fh:
        plistlib.dump({"included_manifests": ["all"]}, fh)
    with pytest.raises(PromotionError):
        set_manifest_catalogs(path, ["production"])


def test_a_real_catalog_build_matches_declared_membership(tmp_path):
    """Criterion 3, against the real makecatalogs rather than a stand-in.

    A pkginfo declaring the wrong catalog silently changes who can receive an item, so the check is
    "what the build produced" == "what the pkginfos declare", per catalog, after every build.
    """
    import shutil

    from munki_fleet.catalogs import DEFAULT_MAKECATALOGS, build_catalogs
    from munki_fleet.catalogs import _load_items
    if not os.path.isfile(DEFAULT_MAKECATALOGS):
        pytest.skip("makecatalogs is not installed on this machine")

    root = metadata_tree(tmp_path / "src", items=[
        item("Promoted", catalogs=["production"]),
        item("Staged", catalogs=["testing"]),
        item("Both", catalogs=["testing", "production"]),
    ])
    for name, cats in (("Promoted", ["production"]), ("Staged", ["testing"]),
                       ("Both", ["testing", "production"])):
        for entry in os.listdir(os.path.join(root, "pkgsinfo")):
            if entry.startswith(name):
                write_pkginfo_catalogs(os.path.join(root, "pkgsinfo", entry), cats)
    shutil.rmtree(os.path.join(root, "catalogs"))       # the build is the only source

    result = build_catalogs(root)                        # the real makecatalogs
    built = {name: {e["name"] for e in _load_items(body)}
             for name, body in result.catalogs.items()}
    declared = {}
    for _, pkginfo in _iter_pkginfos(root):
        for cat in pkginfo.get("catalogs") or []:
            declared.setdefault(cat, set()).add(pkginfo["name"])

    assert set(built) >= {"all", "testing", "production"}, \
        f"both rings must build, got {sorted(built)}"
    for cat in ("testing", "production"):
        assert built[cat] == declared[cat], \
            f"{cat}: built {sorted(built[cat])} != declared {sorted(declared[cat])}"


def test_write_pkginfo_catalogs_preserves_the_rest_of_the_plist(tmp_path):
    root = metadata_tree(tmp_path / "src")
    path = os.path.join(root, "pkgsinfo", "A-0.pkginfo")
    before = plistlib.load(open(path, "rb"))
    write_pkginfo_catalogs(path, ["production"])
    after = plistlib.load(open(path, "rb"))
    assert after["catalogs"] == ["production"]
    before.pop("catalogs"), after.pop("catalogs")
    assert before == after, "only the catalogs array may change"
