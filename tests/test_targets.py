"""The write-verify-rename invariant, exercised on both transports.

Behaviour under test (not implementation): after a successful write the destination holds exactly
the bytes given; a target that does not store what it was given is refused, with the destination
untouched and no temporary file left behind.
"""
import os

import pytest

from conftest import FakeSsh, StoringTarget, sha
from munki_fleet.targets import LocalDirTarget, SshTarget, TargetError


def leftovers(root, keep):
    found = []
    for dirpath, _, files in os.walk(root):
        for f in files:
            rel = os.path.relpath(os.path.join(dirpath, f), root)
            if rel != keep:
                found.append(rel)
    return sorted(found)


def test_local_write_stores_the_bytes_and_leaves_nothing_behind(tmp_path):
    target = LocalDirTarget(str(tmp_path))
    target.write_atomic("x/y.plist", b"first")
    assert (tmp_path / "x" / "y.plist").read_bytes() == b"first"
    assert leftovers(str(tmp_path), "x/y.plist") == []


def test_local_write_replaces_and_creates_parents(tmp_path):
    target = LocalDirTarget(str(tmp_path))
    target.write_atomic("deep/nested/file", b"one")
    target.write_atomic("deep/nested/file", b"two")
    assert (tmp_path / "deep" / "nested" / "file").read_bytes() == b"two"
    assert leftovers(str(tmp_path), "deep/nested/file") == []


def test_local_target_refuses_what_it_cannot_store(tmp_path):
    LocalDirTarget(str(tmp_path)).write_atomic("keep", b"existing")
    target = StoringTarget(str(tmp_path), corrupt_prefix="target.plist")
    with pytest.raises(TargetError):
        target.write_atomic("target.plist", b"payload")
    assert (tmp_path / "target.plist").exists() is False
    assert (tmp_path / "keep").read_bytes() == b"existing"


def test_local_stat_reports_hash_and_size_and_none_for_missing(tmp_path):
    target = LocalDirTarget(str(tmp_path))
    target.write_atomic("a.plist", b"hello")
    info = target.stat("a.plist")
    assert (info.sha256, info.size) == (sha(b"hello"), 5)
    assert target.stat("nope") is None


def test_ssh_target_writes_temp_then_renames_and_verifies():
    shell = FakeSsh()
    SshTarget("t6-nas", "/repo", runner=shell).write_atomic("manifests/site_default", b"manifest")
    shapes = [c.split()[0] for c, _ in shell.commands]
    assert shapes == ["mkdir", "cat", "if", "mv", "if"], shapes
    assert shell.files["/repo/manifests/site_default"] == b"manifest"
    assert not [p for p in shell.files if p.endswith(".tmp")], "temporary file survived"


def test_ssh_target_refuses_a_corrupting_remote_and_cleans_up():
    shell = FakeSsh(corrupt_writes=True)
    with pytest.raises(TargetError):
        SshTarget("t6-nas", "/repo", runner=shell).write_atomic("catalogs/all", b"catalog")
    assert shell.files == {}, f"nothing should survive a failed write: {shell.files}"
    assert not [c for c, _ in shell.commands if c.startswith("mv")], "a failed write must not rename"


def test_ssh_target_quotes_paths_containing_spaces():
    shell = FakeSsh()
    target = SshTarget("t6-nas", "/repo", runner=shell)
    target.write_atomic("manifests/303B iMac", b"m")
    assert shell.files["/repo/manifests/303B iMac"] == b"m"


def test_ssh_target_reports_a_failing_remote_command():
    shell = FakeSsh(fail_on="cat > ")
    with pytest.raises(TargetError):
        SshTarget("t6-nas", "/repo", runner=shell).write_atomic("catalogs/all", b"catalog")


def test_ssh_read_returns_remote_bytes():
    shell = FakeSsh()
    shell.files["/repo/catalogs/all"] = b"remote bytes"
    assert SshTarget("t6-nas", "/repo", runner=shell).read("catalogs/all") == b"remote bytes"


def test_ssh_stat_is_none_when_the_remote_file_is_absent():
    assert SshTarget("t6-nas", "/repo", runner=FakeSsh()).stat("catalogs/all") is None
