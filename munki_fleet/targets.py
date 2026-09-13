"""Publish targets: the seam that keeps the publish path testable without SSH.

A target stores metadata files at relative paths. `LocalDirTarget` is used by tests and dry runs;
`SshTarget` is the real NAS path. One `write_atomic` implementation is shared by both, so the
write-verify-rename invariant is stated once and cannot drift between transports.

The invariant, in order: put the bytes at a temporary name derived from their own hash, read that
back and compare hash *and* size, and only then replace the destination. On any mismatch the
temporary file is removed and the destination is left exactly as it was.
"""
from __future__ import annotations

import hashlib
import os
import shlex
import subprocess
from dataclasses import dataclass
from typing import Callable, Optional


class TargetError(Exception):
    """A target could not store or read what it was asked to."""


@dataclass(frozen=True)
class FileStat:
    sha256: str
    size: int


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Target:
    """Shared atomic-write behaviour over transport-specific primitives."""

    # --- primitives subclasses must provide ---------------------------------
    def stat(self, relpath: str) -> Optional[FileStat]:
        raise NotImplementedError

    def read(self, relpath: str) -> bytes:
        raise NotImplementedError

    def _put(self, relpath: str, data: bytes) -> None:
        raise NotImplementedError

    def _replace(self, relpath: str, destination: str) -> None:
        raise NotImplementedError

    def _remove(self, relpath: str) -> None:
        raise NotImplementedError

    def remove(self, relpath: str) -> None:
        """Delete a file from the target. Used to undo a write that created one."""
        self._remove(relpath)

    def list_files(self, dirs) -> list:
        """Every file under the given top-level directories, as relative paths."""
        raise NotImplementedError

    def exists(self, relpath: str) -> bool:
        """Whether a path is present. Deliberately does not read it: a payload can be gigabytes."""
        raise NotImplementedError

    # --- the invariant -------------------------------------------------------
    def temp_name(self, relpath: str, data: bytes) -> str:
        return f"{relpath}.{sha256_bytes(data)[:12]}.tmp"

    def write_atomic(self, relpath: str, data: bytes) -> FileStat:
        digest = sha256_bytes(data)
        tmp = self.temp_name(relpath, data)
        self._put(tmp, data)
        try:
            readback = self.stat(tmp)
            if readback is None or readback.sha256 != digest or readback.size != len(data):
                raise TargetError(
                    f"read-back verification failed for {relpath}: "
                    f"stored {readback.sha256[:12] if readback else 'nothing'}, expected {digest[:12]}"
                )
            self._replace(tmp, relpath)
            placed = self.stat(relpath)
            if placed is None or placed.sha256 != digest:
                raise TargetError(f"destination verification failed for {relpath} after rename")
        except TargetError:
            self._remove(tmp)
            raise
        return FileStat(sha256=digest, size=len(data))


class LocalDirTarget(Target):
    """A target rooted at a local directory: tests, dry runs, and pre-image capture."""

    def __init__(self, root: str) -> None:
        self.root = os.path.abspath(root)

    def _full(self, relpath: str) -> str:
        return os.path.join(self.root, relpath)

    def stat(self, relpath: str) -> Optional[FileStat]:
        full = self._full(relpath)
        if not os.path.isfile(full):
            return None
        try:
            with open(full, "rb") as fh:
                data = fh.read()
        except OSError as exc:
            raise TargetError(f"could not read {relpath}: {exc}") from exc
        return FileStat(sha256=sha256_bytes(data), size=len(data))

    def read(self, relpath: str) -> bytes:
        try:
            with open(self._full(relpath), "rb") as fh:
                return fh.read()
        except OSError as exc:
            raise TargetError(f"could not read {relpath}: {exc}") from exc

    def _put(self, relpath: str, data: bytes) -> None:
        full = self._full(relpath)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as fh:
            fh.write(data)

    def _replace(self, relpath: str, destination: str) -> None:
        os.replace(self._full(relpath), self._full(destination))

    def _remove(self, relpath: str) -> None:
        full = self._full(relpath)
        if os.path.exists(full):
            os.remove(full)

    def exists(self, relpath: str) -> bool:
        return os.path.isfile(self._full(relpath))

    def list_files(self, dirs) -> list:
        out = []
        for d in dirs:
            base = self._full(d)
            if not os.path.isdir(base):
                continue
            for dirpath, _, files in os.walk(base):
                for f in files:
                    if f.startswith(".") or f.endswith(".tmp"):
                        continue
                    out.append(os.path.relpath(os.path.join(dirpath, f), self.root))
        return sorted(out)


def default_ssh_runner(host: str, timeout: int = 60):
    """Run a command on `host` over ssh, multiplexing so a publish is not N handshakes."""

    def run(command: str, stdin: Optional[bytes] = None):
        argv = [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", "ControlMaster=auto",
            "-o", f"ControlPath=/tmp/munki-fleet-{host}.sock",
            "-o", "ControlPersist=120s",
            host,
            command,
        ]
        try:
            completed = subprocess.run(argv, input=stdin, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise TargetError(f"ssh timed out after {timeout}s: {command}") from exc
        return completed.returncode, completed.stdout, completed.stderr

    return run


class SshTarget(Target):
    """A target on a remote host reached over SSH.

    The QNAP's SSH service offers no SCP/SFTP subsystem this project can rely on, so bytes are
    streamed over stdin. `runner` is injectable so the whole sequence can be exercised without a
    network in tests.
    """

    def __init__(self, host: str, root: str, runner: Optional[Callable] = None) -> None:
        self.host = host
        self.root = root.rstrip("/")
        self._run = runner or default_ssh_runner(host)

    def _abs(self, relpath: str) -> str:
        return f"{self.root}/{relpath}"

    def _command(self, command: str, stdin: Optional[bytes] = None):
        returncode, stdout, stderr = self._run(command, stdin)
        if returncode != 0:
            raise TargetError(
                f"remote command failed ({returncode}): {command} :: "
                f"{stderr.decode('utf-8', 'replace')[:200]}"
            )
        return stdout

    def stat(self, relpath: str) -> Optional[FileStat]:
        path = shlex.quote(self._abs(relpath))
        out = self._command(
            f"if [ -f {path} ]; then sha256sum {path}; wc -c < {path}; else echo MISSING; fi"
        ).decode("utf-8", "replace").strip()
        if out.startswith("MISSING"):
            return None
        lines = [line for line in out.splitlines() if line.strip()]
        if len(lines) < 2:
            raise TargetError(f"unexpected remote stat output for {relpath}: {out[:200]}")
        return FileStat(sha256=lines[0].split()[0], size=int(lines[1].strip()))

    def read(self, relpath: str) -> bytes:
        return self._command(f"cat {shlex.quote(self._abs(relpath))}")

    def _put(self, relpath: str, data: bytes) -> None:
        parent = os.path.dirname(self._abs(relpath))
        self._command(f"mkdir -p {shlex.quote(parent)}")
        self._command(f"cat > {shlex.quote(self._abs(relpath))}", stdin=data)

    def _replace(self, relpath: str, destination: str) -> None:
        self._command(
            f"mv -f {shlex.quote(self._abs(relpath))} {shlex.quote(self._abs(destination))}"
        )

    def _remove(self, relpath: str) -> None:
        self._command(f"rm -f {shlex.quote(self._abs(relpath))}")

    def exists(self, relpath: str) -> bool:
        out = self._command(
            f"if [ -f {shlex.quote(self._abs(relpath))} ]; then echo PRESENT; else echo MISSING; fi"
        ).decode("utf-8", "replace")
        return out.startswith("PRESENT")

    def list_files(self, dirs) -> list:
        """List files under the given directories on the remote host."""
        dirs_arg = " ".join(shlex.quote(self._abs(d)) for d in dirs)
        out = self._command(f"find {dirs_arg} -type f 2>/dev/null").decode("utf-8", "replace")
        return sorted(
            os.path.relpath(line.strip(), self.root)
            for line in out.splitlines()
            if line.strip() and not os.path.basename(line.strip()).startswith(".")
            and not line.strip().endswith(".tmp")
        )
