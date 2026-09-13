"""The version relationship between the tools that build metadata and the clients that read it.

The same metadata builds differently under different Munki tool versions. A `makecatalogs` 6.6.0
build and a 7.3.0 build of one tree differ in the order of same-name entries, and since a client
takes the first entry matching a name, that changes which installer it receives (ticket 09's
evidence). So the toolchain decides whether a rebuild is a no-op or a behaviour change, and aligning
it is not bookkeeping.

Two things this module deliberately does *not* do: install anything, and guess. Versions are read by
running the tool on the machine that holds it, and the relationship is computed from what came back.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

MUNKI_DIR = "/usr/local/munki"
TOOLS = ("makecatalogs", "managedsoftwareupdate", "munkiimport")
VERSION_COMMAND = ("for tool in {tools}; do "
                   "if [ -x {dir}/$tool ]; then printf '%s=%s\n' \"$tool\" "
                   "\"$({dir}/$tool --version 2>/dev/null | head -1)\"; fi; done")


@dataclass
class ToolVersion:
    host: str
    tool: str
    version: str
    command: str

    def to_json(self) -> dict:
        return {"host": self.host, "tool": self.tool, "version": self.version,
                "command": self.command}


@dataclass
class Relationship:
    builders: List[dict] = field(default_factory=list)
    clients: List[dict] = field(default_factory=list)
    findings: List[str] = field(default_factory=list)
    aligned: bool = True

    def to_json(self) -> dict:
        return {"builders": self.builders, "clients": self.clients,
                "findings": self.findings, "aligned": self.aligned}


def major(version: str) -> Optional[int]:
    head = (version or "").split(".")[0]
    return int(head) if head.isdigit() else None


def read_versions(runner, host: str) -> List[ToolVersion]:
    """Run each admin tool's `--version` on the machine that holds it and record what it said."""
    command = VERSION_COMMAND.format(tools=" ".join(TOOLS), dir=MUNKI_DIR)
    returncode, stdout, stderr = runner(host, command, None)
    if returncode != 0:
        raise RuntimeError(f"could not read tool versions on {host}: "
                           f"{stderr.decode('utf-8', 'replace').strip()[:120]}")
    versions = []
    for line in stdout.decode("utf-8", "replace").splitlines():
        if "=" not in line:
            continue
        tool, _, version = line.partition("=")
        versions.append(ToolVersion(host=host, tool=tool.strip(), version=version.strip(),
                                    command=f"{MUNKI_DIR}/{tool.strip()} --version"))
    if not versions:
        raise RuntimeError(f"no Munki tools found under {MUNKI_DIR} on {host}")
    return versions


def client_versions(store_path: Optional[str], records: Optional[Sequence] = None) -> List[dict]:
    """What each observed client reports about its own Munki version (ticket 05's store)."""
    if records is None:
        if not store_path:
            return []
        from .probe import ObservationStore
        records = ObservationStore(store_path).read()
    clients: Dict[str, dict] = {}
    for record in records:
        body = record if isinstance(record, dict) else json.loads(record)
        if body.get("kind") == "run" or body.get("outcome") != "observed":
            continue
        state = body.get("state") or {}
        machine = body.get("machine") or {}
        serial = machine.get("serial") or (body.get("target") or {}).get("serial")
        if not serial or not state.get("munki_version"):
            continue
        observed = body.get("observed_at")
        current = clients.get(serial)
        if current is None or (observed or "") > (current.get("observed_at") or ""):
            clients[serial] = {"serial": serial, "host": (body.get("target") or {}).get("host"),
                               "munki_version": state["munki_version"], "observed_at": observed}
    return [clients[key] for key in sorted(clients)]


def relationship(builders: Sequence[ToolVersion], clients: Sequence[dict]) -> Relationship:
    """Compare the tool that builds catalogs against the versions the clients actually run.

    The rule is one major version, and the builder is the stricter side of it: a builder older than a
    client can reorder same-name entries under the client's feet, and a builder newer than every
    client can write a catalog no client has been tested against.
    """
    out = Relationship()
    builds = [v for v in builders if v.tool == "makecatalogs"]
    out.builders = [v.to_json() for v in builds]
    out.clients = [dict(c) for c in clients]
    if not builds or not clients:
        out.findings.append("cannot state the relationship: "
                            + ("no makecatalogs version recorded" if not builds
                               else "no client version observed"))
        out.aligned = False
        return out

    for builder in builds:
        builder_major = major(builder.version)
        for client in clients:
            client_major = major(client["munki_version"])
            if builder_major is None or client_major is None:
                out.findings.append(f"{builder.host} {builder.version} vs {client['serial']} "
                                    f"{client['munki_version']}: unreadable version")
                out.aligned = False
            elif builder_major < client_major:
                out.findings.append(
                    f"{builder.host} builds with Munki {builder.version} while {client['serial']} "
                    f"runs {client['munki_version']}: the builder is a major version behind a client, "
                    f"so a rebuild can reorder entries the client is already being served")
                out.aligned = False
            elif builder_major > client_major:
                out.findings.append(
                    f"{builder.host} builds with Munki {builder.version}, newer than every client "
                    f"({client['serial']} runs {client['munki_version']}): the catalog format has not "
                    f"been exercised on a client")
                out.aligned = False
    return out


def compare_build_to(before, build_result, names: Sequence[str]) -> dict:
    """Byte-compare a build against a pre-image, and explain any difference item by item.

    `before` is a callable returning the pre-image bytes for a catalog name — the same function
    serves a directory of saved catalogs, a served target, or a fixture — and `names` is the union of
    the catalog names on both sides, passed in because a lazy callable cannot enumerate itself.
    """
    from .catalogs import CatalogError, compare_catalogs
    results = {}
    for name in sorted(set(names)):
        old = before(name)
        new = build_result.catalogs.get(name)
        entry = {"before_sha256": hashlib.sha256(old).hexdigest() if old is not None else None,
                 "after_sha256": hashlib.sha256(new).hexdigest() if new is not None else None,
                 "before_present": old is not None, "after_present": new is not None}
        if old is None or new is None:
            entry["explanation"] = ("the catalog exists only on one side, so the difference is not a "
                                    "rebuild difference")
            entry["identical"] = False
            results[name] = entry
            continue
        entry["identical"] = old == new
        if entry["identical"]:
            entry["item_diff"] = "no item-level changes"
            entry["has_item_changes"] = False
            entry["explanation"] = "identical bytes"
            results[name] = entry
            continue
        try:
            diff = compare_catalogs(old, new)
        except CatalogError as exc:
            # A pre-image can be old, partial or corrupt: say so rather than crashing the harness
            # that exists to compare exactly these artifacts.
            entry["item_diff"] = None
            entry["has_item_changes"] = None
            entry["explanation"] = f"the difference cannot be explained item by item: {exc}"
            results[name] = entry
            continue
        entry["item_diff"] = diff.describe()
        entry["has_item_changes"] = diff.has_item_changes()
        if not entry["identical"] and not diff.is_empty():
            entry["explanation"] = "every difference is explained by the item-level diff"
        elif not entry["identical"]:
            entry["explanation"] = ("the bytes differ with no item-level difference: the same entries "
                                    "serialised or ordered differently, which is what a different "
                                    "tool version produces")
        else:
            entry["explanation"] = "identical bytes"
        results[name] = entry
    return results
