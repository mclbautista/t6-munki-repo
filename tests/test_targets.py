"""Tests for the publish targets: the seam that lets the publish path be tested with no SSH."""
import hashlib
import os

import pytest

from munki_fleet.targets import LocalDirTarget, SshTarget, TargetError


def sha(b):
    return hashlib.sha256(b).hexdigest()


def test_stat_reports_hash_and_size(tmp_path):
    target = LocalDirTarget(str(tmp_path))
    (tmp_path / "a.plist").write_bytes(b"hello")
    info = target.stat("a.plist")
    assert info.sha256 == sha(b"hello")
    assert info.size == 5


def test_stat_is_none_for_missing_file(tmp_path):
    assert LocalDirTarget(str(tmp_path)).stat("nope") is None


def test_write_atomic_replaces_and_leaves_no_temp(tmp_path):
    target = LocalDirTarget(str(tmp_path))
    target.write_atomic("x/y.plist", b"first")
    target.write_atomic("x/y.plist", b"second")
    assert (tmp_path / "x" / "y.plist").read_bytes() == b"second"
    leftovers = [p for p in os.listdir(tmp_path / "x") if p != "y.plist"]
    assert leftovers == [], f"temporary files left behind: {leftovers}"


def test_write_atomic_creates_parent_directories(tmp_path):
    LocalDirTarget(str(tmp_path)).write_atomic("deep/nested/file", b"v")
    assert (tmp_path / "deep" / "nested" / "file").read_bytes() == b"v"


def test_write_atomic_raises_when_readback_disagrees(tmp_path):
    """A target that does not store what it was given must not be trusted."""
    target = LocalDirTarget(str(tmp_path), corrupt_on_write=True)
    with pytest.raises(TargetError):
        target.write_atomic("y.plist", b"payload")
    assert not (tmp_path / "y.plist").exists(), "a file that failed verification must not be left in place"


def test_read_returns_bytes(tmp_path):
    (tmp_path / "b").write_bytes(b"bytes")
    assert LocalDirTarget(str(tmp_path)).read("b") == b"bytes"


def test_ssh_argv_multiplexes_connections():
    """A publish stats every path; without multiplexing that is one ssh handshake per file."""
    argv = SshTarget("t6-nas", "/repo").ssh_argv("echo hi")
    assert argv[0] == "ssh"
    assert "BatchMode=yes" in argv
    assert any(a.startswith("ControlMaster=") for a in argv)
    assert any(a.startswith("ControlPath=") for a in argv)
    assert any(a.startswith("ControlPersist=") for a in argv)
    assert argv[-2] == "t6-nas" and argv[-1] == "echo hi"


def test_ssh_target_builds_commands_without_shell_injection():
    """Paths from the repository are quoted; a path with a space must survive intact."""
    t = SshTarget("t6-nas", "/share/ZFS23_DATA/Web/MunkiRepo")
    cmd = t._remote_command("sha256sum", "manifests/303B iMac")
    assert "'manifests/303B iMac'" in cmd
    assert cmd.startswith("sha256sum ")
