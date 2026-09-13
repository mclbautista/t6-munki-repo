"""The publish path: pre-flight, write-verify-rename, pre-images, and rollback.

The invariants under test come from the specification: a partial publish never happens, and a
publish that fails leaves the target as it was.
"""
import pytest

from conftest import FailingTarget, StoringTarget, sha, write_file
from munki_fleet.publish import PublishAborted, PublishError, publish, verify_served
from munki_fleet.targets import LocalDirTarget


def test_publish_writes_and_verifies(tmp_path):
    source, target_dir = tmp_path / "src", tmp_path / "tgt"
    source.mkdir(), target_dir.mkdir()
    write_file(str(source), "manifests/site_default", b"manifest")
    write_file(str(source), "catalogs/all", b"catalog")

    report = publish(str(source), LocalDirTarget(str(target_dir)),
                     ["manifests/site_default", "catalogs/all"])

    assert (target_dir / "manifests" / "site_default").read_bytes() == b"manifest"
    assert report.written == ["catalogs/all", "manifests/site_default"]
    assert report.unchanged == []


def test_publish_skips_files_already_identical(tmp_path):
    source, target_dir = tmp_path / "src", tmp_path / "tgt"
    source.mkdir(), target_dir.mkdir()
    write_file(str(source), "catalogs/all", b"same")
    write_file(str(target_dir), "catalogs/all", b"same")
    report = publish(str(source), LocalDirTarget(str(target_dir)), ["catalogs/all"])
    assert report.unchanged == ["catalogs/all"] and report.written == []


def test_publish_leaves_the_target_alone_when_a_write_cannot_be_verified(tmp_path):
    source, target_dir = tmp_path / "src", tmp_path / "tgt"
    source.mkdir(), target_dir.mkdir()
    write_file(str(source), "catalogs/all", b"new bytes")
    write_file(str(target_dir), "catalogs/all", b"old bytes")

    with pytest.raises(PublishAborted):
        publish(str(source), StoringTarget(str(target_dir)), ["catalogs/all"])

    assert (target_dir / "catalogs" / "all").read_bytes() == b"old bytes"


def test_publish_records_the_pre_image_when_asked(tmp_path):
    source, target_dir, backup = tmp_path / "src", tmp_path / "tgt", tmp_path / "backup"
    source.mkdir(), target_dir.mkdir()
    write_file(str(source), "catalogs/all", b"new")
    write_file(str(target_dir), "catalogs/all", b"old")

    report = publish(str(source), LocalDirTarget(str(target_dir)), ["catalogs/all"],
                     backup_dir=str(backup))

    assert (backup / "catalogs" / "all").read_bytes() == b"old"
    assert report.backed_up == ["catalogs/all"]


def test_publish_refuses_an_incomplete_checkout_before_writing_anything(tmp_path):
    """The plan is validated first: a missing source file aborts with the target untouched."""
    source, target_dir = tmp_path / "src", tmp_path / "tgt"
    source.mkdir(), target_dir.mkdir()
    write_file(str(source), "catalogs/all", b"new")
    write_file(str(target_dir), "catalogs/all", b"old")

    with pytest.raises(PublishError) as excinfo:
        publish(str(source), LocalDirTarget(str(target_dir)), ["catalogs/all", "manifests/gone"])

    assert "missing" in str(excinfo.value)
    assert (target_dir / "catalogs" / "all").read_bytes() == b"old", "nothing may be written"


def test_a_failure_partway_rolls_back_what_was_already_written(tmp_path):
    source, target_dir = tmp_path / "src", tmp_path / "tgt"
    source.mkdir(), target_dir.mkdir()
    write_file(str(source), "catalogs/all", b"new catalog")
    write_file(str(source), "manifests/site_default", b"new manifest")
    write_file(str(target_dir), "catalogs/all", b"old catalog")

    target = FailingTarget(str(target_dir), fail_prefix="manifests/")
    with pytest.raises(PublishAborted) as excinfo:
        publish(str(source), target, ["catalogs/all", "manifests/site_default"])

    report = excinfo.value.report
    assert report.rolled_back == ["catalogs/all"], report.describe()
    assert report.rollback_errors == []
    assert (target_dir / "catalogs" / "all").read_bytes() == b"old catalog", "must be restored"
    assert not (target_dir / "manifests" / "site_default").exists()


def test_rollback_removes_a_file_the_publish_created(tmp_path):
    source, target_dir = tmp_path / "src", tmp_path / "tgt"
    source.mkdir(), target_dir.mkdir()
    write_file(str(source), "catalogs/all", b"new catalog")
    write_file(str(source), "catalogs/new", b"brand new")

    target = FailingTarget(str(target_dir), fail_prefix="catalogs/new")
    with pytest.raises(PublishAborted):
        publish(str(source), target, ["catalogs/all", "catalogs/new"])

    assert not (target_dir / "catalogs" / "all").exists(), "a file this publish created is removed"


def test_publish_rejects_paths_that_escape_the_root(tmp_path):
    source, target_dir = tmp_path / "src", tmp_path / "tgt"
    source.mkdir(), target_dir.mkdir()
    with pytest.raises(PublishError):
        publish(str(source), LocalDirTarget(str(target_dir)), ["../outside"])


def test_verify_served_reports_matching_mismatching_and_missing(tmp_path):
    source, served_dir = tmp_path / "src", tmp_path / "served"
    source.mkdir(), served_dir.mkdir()
    write_file(str(source), "catalogs/all", b"same")
    write_file(str(served_dir), "catalogs/all", b"same")
    write_file(str(source), "catalogs/testing", b"expected")
    write_file(str(served_dir), "catalogs/testing", b"different")

    result = verify_served(str(source), LocalDirTarget(str(served_dir)),
                           ["catalogs/all", "catalogs/testing", "catalogs/missing"])

    assert result.matching == ["catalogs/all"]
    assert result.mismatching == ["catalogs/testing"]
    assert result.missing == ["catalogs/missing"]
    assert result.ok is False
