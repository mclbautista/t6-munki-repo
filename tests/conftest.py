"""Shared test fixtures and doubles.

The doubles live here so the tests exercise the production code through its own seams rather than
through hooks embedded in it.
"""
import hashlib
import os

import pytest

from munki_fleet.targets import LocalDirTarget, Target, TargetError


# --- catalog fixtures shared by the catalog, gate and CLI tests ------------------------------
def item(name, version="1.0", **extra):
    entry = {"name": name, "version": version, "catalogs": ["testing"],
             "installer_item_location": f"{name}.dmg"}
    entry.update(extra)
    return entry


def catalog_dict(items):
    """The dict-with-`items` shape."""
    import plistlib
    return plistlib.dumps({"items": items})


def catalog_array(items):
    """The top-level array shape that makecatalogs actually writes."""
    import plistlib
    return plistlib.dumps(items)


def catalog_runner(items_by_catalog):
    """A stand-in for makecatalogs: writes catalogs into <metadata_root>/catalogs and returns 0."""
    def run(metadata_root):
        out = os.path.join(metadata_root, "catalogs")
        os.makedirs(out, exist_ok=True)
        for name, items in items_by_catalog.items():
            with open(os.path.join(out, name), "wb") as fh:
                fh.write(catalog_array(items))
        return 0
    return run


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_file(root, relpath, content):
    full = os.path.join(root, relpath)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "wb") as fh:
        fh.write(content)
    return full


class StoringTarget(LocalDirTarget):
    """A local target that stores something other than what it was given, below one prefix.

    Simulates a target whose write path silently corrupts bytes, so the read-back verification can
    be tested without a production flag existing purely for tests.
    """

    def __init__(self, root, corrupt_prefix: str = "") -> None:
        super().__init__(root)
        self.corrupt_prefix = corrupt_prefix

    def _put(self, relpath: str, data: bytes) -> None:
        if relpath.startswith(self.corrupt_prefix):
            super()._put(relpath, b"corrupted on the way in")
            return
        super()._put(relpath, data)

    def _replace(self, relpath: str, destination: str) -> None:
        if relpath.startswith(self.corrupt_prefix):
            raise AssertionError("a corrupting target must never reach the rename step")
        super()._replace(relpath, destination)


class FakeSsh:
    """A minimal stand-in for a remote shell over ssh.

    Implements exactly the command shapes `SshTarget` issues, and can be told to corrupt writes so
    the remote read-back path is exercised too.
    """

    def __init__(self, corrupt_writes: bool = False, fail_on: str = None):
        self.files = {}
        self.commands = []
        self.corrupt_writes = corrupt_writes
        self.fail_on = fail_on

    def __call__(self, command, stdin=None):
        import shlex
        self.commands.append((command, stdin))
        if self.fail_on and command.startswith(self.fail_on):
            return 1, b"", b"simulated failure"
        tokens = shlex.split(command)          # shlex strips the quoting shlex.quote added
        if tokens[:2] == ["mkdir", "-p"]:
            return 0, b"", b""
        if tokens[:2] == ["cat", ">"]:
            path = tokens[2]
            self.files[path] = b"corrupted over the wire" if self.corrupt_writes else (stdin or b"")
            return 0, b"", b""
        if tokens[:2] == ["rm", "-f"]:
            self.files.pop(tokens[2], None)
            return 0, b"", b""
        if tokens[:2] == ["mv", "-f"]:
            self.files[tokens[3]] = self.files.pop(tokens[2])
            return 0, b"", b""
        if tokens[:1] == ["cat"]:
            return 0, self.files[tokens[1]], b""
        if tokens[:3] == ["if", "[", "-f"]:
            path = tokens[3]
            if path not in self.files:
                return 0, b"MISSING", b""
            data = self.files[path]
            return 0, f"{sha(data)}  {path}\n{len(data)}\n".encode(), b""
        raise AssertionError(f"unexpected command shape: {command}")


class FailingTarget(LocalDirTarget):
    """A local target that fails on writes to one path, to exercise rollback."""

    def __init__(self, root, fail_prefix):
        super().__init__(root)
        self.fail_prefix = fail_prefix

    def _put(self, relpath, data):
        if relpath.startswith(self.fail_prefix):
            raise TargetError(f"simulated failure writing {relpath}")
        super()._put(relpath, data)
