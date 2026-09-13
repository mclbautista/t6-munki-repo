"""Publish targets: the seam that keeps the publish path testable without SSH.

A target is anything that can store metadata files at relative paths. `LocalDirTarget` is used by
tests and for dry runs; `SshTarget` is the real NAS path. Keeping the two behind one small
interface is what makes the publish invariants testable at all.
"""
from __future__ import annotations

import hashlib
import os
import shlex
import subprocess
from dataclasses import dataclass
from typing import Optional


class TargetError(Exception):
    """A target could not store or read what it was asked to."""


@dataclass(frozen=True)
class FileStat:
    sha256: str
    size: int


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class LocalDirTarget:
    """A target rooted at a local directory. Used by tests and dry runs."""

    def __init__(self, root: str, corrupt_on_write: bool = False) -> None:
        self.root = os.path.abspath(root)
        self._corrupt_on_write = corrupt_on_write

    def _full(self, relpath: str) -> str:
        return os.path.join(self.root, relpath)

    def stat(self, relpath: str) -> Optional[FileStat]:
        full = self._full(relpath)
        if not os.path.isfile(full):
            return None
        with open(full, "rb") as fh:
            data = fh.read()
        return FileStat(sha256=sha256_bytes(data), size=len(data))

    def read(self, relpath: str) -> bytes:
        with open(self._full(relpath), "rb") as fh:
            return fh.read()

    def write_atomic(self, relpath: str, data: bytes) -> FileStat:
        full = self._full(relpath)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        tmp = f"{full}.{sha256_bytes(data)[:12]}.tmp"
        stored = b"corrupted by the test target" if self._corrupt_on_write else data
        with open(tmp, "wb") as fh:
            fh.write(stored)
        try:
            readback = self.stat(os.path.relpath(tmp, self.root))
            if readback is None or readback.sha256 != sha256_bytes(data):
                raise TargetError(f"read-back verification failed for {relpath}")
        except TargetError:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise
        os.replace(tmp, full)
        return FileStat(sha256=sha256_bytes(data), size=len(data))


class SshTarget:
    """A target reached over SSH (`cat > file`, checksum, atomic `mv`).

    The QNAP's SSH service has no SCP/SFTP subsystem that this project can rely on, so files are
    streamed over stdin and moved into place only after their checksum has been read back.
    """

    def __init__(self, host: str, root: str, timeout: int = 60) -> None:
        self.host = host
        self.root = root.rstrip("/")
        self.timeout = timeout

    def _remote_command(self, *parts: str) -> str:
        """Join a remote command: the first part is the command, the rest are quoted arguments."""
        if not parts or not parts[0]:
            raise TargetError("empty remote command")
        return " ".join([parts[0]] + [shlex.quote(p) for p in parts[1:]])

    def _abs(self, relpath: str) -> str:
        return f"{self.root}/{relpath}"

    def ssh_argv(self, command: str) -> list:
        """The ssh invocation, with connection multiplexing so a publish is not N handshakes."""
        socket = f"/tmp/munki-fleet-{self.host}.sock"
        return [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", "ControlMaster=auto",
            "-o", f"ControlPath={socket}",
            "-o", "ControlPersist=120s",
            self.host,
            command,
        ]

    def _run(self, command: str, stdin: Optional[bytes] = None) -> subprocess.CompletedProcess:
        argv = self.ssh_argv(command)
        try:
            return subprocess.run(argv, input=stdin, capture_output=True, timeout=self.timeout)
        except subprocess.TimeoutExpired as exc:
            raise TargetError(f"ssh timed out after {self.timeout}s: {command}") from exc

    def stat(self, relpath: str) -> Optional[FileStat]:
        path = self._abs(relpath)
        command = self._remote_command(
            f"if [ -f {shlex.quote(path)} ]; then sha256sum {shlex.quote(path)}; "
            f"wc -c < {shlex.quote(path)}; else echo MISSING; fi"
        )
        result = self._run(command)
        out = result.stdout.decode("utf-8", "replace").strip()
        if result.returncode != 0:
            raise TargetError(f"remote stat failed for {relpath}: {result.stderr.decode()[:200]}")
        if out.startswith("MISSING"):
            return None
        lines = [l for l in out.splitlines() if l.strip()]
        if len(lines) < 2:
            raise TargetError(f"unexpected remote stat output for {relpath}: {out[:200]}")
        digest = lines[0].split()[0]
        return FileStat(sha256=digest, size=int(lines[1].strip()))

    def read(self, relpath: str) -> bytes:
        path = self._abs(relpath)
        result = self._run(self._remote_command(f"cat {shlex.quote(path)}"))
        if result.returncode != 0:
            raise TargetError(f"remote read failed for {relpath}: {result.stderr.decode()[:200]}")
        return result.stdout

    def remove(self, relpath: str) -> None:
        path = self._abs(relpath)
        self._run(self._remote_command(f"rm -f {shlex.quote(path)}"))

    def write_atomic(self, relpath: str, data: bytes) -> FileStat:
        digest = sha256_bytes(data)
        path = self._abs(relpath)
        parent = os.path.dirname(path)
        tmp = f"{path}.{digest[:12]}.tmp"
        mkdir = self._run(self._remote_command(f"mkdir -p {shlex.quote(parent)}"))
        if mkdir.returncode != 0:
            raise TargetError(f"remote mkdir failed for {parent}: {mkdir.stderr.decode()[:200]}")
        upload = self._run(self._remote_command(f"cat > {shlex.quote(tmp)}"), stdin=data)
        if upload.returncode != 0:
            self.remove(os.path.relpath(tmp, self.root))
            raise TargetError(f"remote upload failed for {relpath}: {upload.stderr.decode()[:200]}")
        try:
            readback = self.stat(os.path.relpath(tmp, self.root))
            if readback is None or readback.sha256 != digest or readback.size != len(data):
                raise TargetError(f"read-back verification failed for {relpath}")
            moved = self._run(self._remote_command(f"mv -f {shlex.quote(tmp)} {shlex.quote(path)}"))
            if moved.returncode != 0:
                raise TargetError(f"remote rename failed for {relpath}: {moved.stderr.decode()[:200]}")
        except TargetError:
            self.remove(os.path.relpath(tmp, self.root))
            raise
        return FileStat(sha256=digest, size=len(data))
