"""Tests for the publish path: temp name, checksum verification, atomic rename, backup."""
import hashlib
import os

import pytest

from munki_fleet.publish import PublishError, publish, verify_served
from munki_fleet.targets import LocalDirTarget


def sha(b):
    return hashlib.sha256(b).hexdigest()


def write(root, relpath, content):
    full = os.path.join(root, relpath)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "wb") as fh:
        fh.write(content)
    return full


def test_publish_writes_files_and_verifies_them(tmp_path):
    source = tmp_path / "src"
    target_dir = tmp_path / "tgt"
    source.mkdir()
    target_dir.mkdir()
    write(str(source), "manifests/site_default", b"manifest")
    write(str(source), "catalogs/all", b"catalog")

    report = publish(str(source), LocalDirTarget(str(target_dir)),
                     ["manifests/site_default", "catalogs/all"])

    assert (target_dir / "manifests" / "site_default").read_bytes() == b"manifest"
    assert (target_dir / "catalogs" / "all").read_bytes() == b"catalog"
    assert report.written == ["catalogs/all", "manifests/site_default"]
    assert report.unchanged == []
    assert report.skipped == []


def test_publish_skips_files_already_identical(tmp_path):
    source = tmp_path / "src"
    target_dir = tmp_path / "tgt"
    source.mkdir()
    target_dir.mkdir()
    write(str(source), "catalogs/all", b"same")
    write(str(target_dir), "catalogs/all", b"same")
    report = publish(str(source), LocalDirTarget(str(target_dir)), ["catalogs/all"])
    assert report.unchanged == ["catalogs/all"]
    assert report.written == []


def test_publish_does_not_touch_the_target_when_verification_fails(tmp_path):
    source = tmp_path / "src"
    target_dir = tmp_path / "tgt"
    source.mkdir()
    target_dir.mkdir()
    write(str(source), "catalogs/all", b"new bytes")
    write(str(target_dir), "catalogs/all", b"old bytes")

    with pytest.raises(PublishError):
        publish(str(source), LocalDirTarget(str(target_dir), corrupt_on_write=True), ["catalogs/all"])

    assert (target_dir / "catalogs" / "all").read_bytes() == b"old bytes"


def test_publish_records_the_pre_image_when_asked(tmp_path):
    source = tmp_path / "src"
    target_dir = tmp_path / "tgt"
    backup = tmp_path / "backup"
    source.mkdir()
    target_dir.mkdir()
    write(str(source), "catalogs/all", b"new")
    write(str(target_dir), "catalogs/all", b"old")

    report = publish(str(source), LocalDirTarget(str(target_dir)), ["catalogs/all"],
                     backup_dir=str(backup))

    assert (backup / "catalogs" / "all").read_bytes() == b"old"
    assert report.backed_up == ["catalogs/all"]


def test_publish_reports_files_missing_from_the_source(tmp_path):
    source = tmp_path / "src"
    target_dir = tmp_path / "tgt"
    source.mkdir()
    target_dir.mkdir()
    report = publish(str(source), LocalDirTarget(str(target_dir)), ["manifests/gone"])
    assert report.skipped == ["manifests/gone"]


def test_publish_rejects_paths_that_escape_the_root(tmp_path):
    source = tmp_path / "src"
    target_dir = tmp_path / "tgt"
    source.mkdir()
    target_dir.mkdir()
    with pytest.raises(PublishError):
        publish(str(source), LocalDirTarget(str(target_dir)), ["../outside"])


def test_verify_served_reports_matching_and_mismatching_files(tmp_path):
    source = tmp_path / "src"
    served_dir = tmp_path / "served"
    source.mkdir()
    served_dir.mkdir()
    write(str(source), "catalogs/all", b"same")
    write(str(served_dir), "catalogs/all", b"same")
    write(str(source), "catalogs/testing", b"expected")
    write(str(served_dir), "catalogs/testing", b"different")

    result = verify_served(str(source), LocalDirTarget(str(served_dir)),
                           ["catalogs/all", "catalogs/testing", "catalogs/missing"])

    assert result.matching == ["catalogs/all"]
    assert result.mismatching == ["catalogs/testing"]
    assert result.missing == ["catalogs/missing"]
    assert result.ok is False
