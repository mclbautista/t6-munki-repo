"""The forced core: what Munki installs on every Mac whether anyone asked or not.

The spec's first problem statement is that 26 items were force-installed on every Mac without
anyone having approved that list per machine. Suspending it is therefore a real change to fleet
behaviour, and it is written to be reversible: the items are **moved** to `optional_installs` (so
they stay installable by hand instead of vanishing) and the list that was suspended is recorded with
its date, reason and author.

Suspending is not the same as deleting. Nothing is uninstalled by it: an item that leaves
`managed_installs` simply stops being installed and updated automatically.
"""
from __future__ import annotations

import json
import os
import plistlib
import re
from typing import Dict, List, Optional, Sequence

from .promote import _now

BASELINE_PATH = os.path.join("manifests", "all")
SUSPENSION_RECORD = os.path.join("data", "baseline-suspended.json")


class BaselineError(Exception):
    """The forced core could not be changed safely."""


def _array_block(text: str, key: str) -> Optional[re.Match]:
    return re.search(rf"\t<key>{key}</key>\n\t<array>\n(.*?)\t</array>\n", text, re.S)


def suspend_forced_installs(source_root: str, approved_by: str, reason: str,
                            at: Optional[str] = None,
                            record_path: str = SUSPENSION_RECORD) -> Dict:
    """Move every forced install to optional, and record what was suspended.

    Editing the published file in place rather than re-serialising it: a plist round-trip would
    reformat the whole manifest, and the diff a reviewer needs is the move itself.
    """
    at = at or _now()
    if not approved_by:
        raise BaselineError("suspending the forced core must record who approved it")
    if not reason.strip():
        raise BaselineError("suspending the forced core must record why")

    path = os.path.join(source_root, BASELINE_PATH)
    with open(path, "rb") as fh:
        body = plistlib.load(fh)
    forced = list(body.get("managed_installs") or [])
    if not forced:
        raise BaselineError(f"{BASELINE_PATH} force-installs nothing; there is nothing to suspend")

    already_optional = list(body.get("optional_installs") or [])
    merged = already_optional + [item for item in forced if item not in already_optional]

    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    managed = _array_block(text, "managed_installs")
    if not managed:
        raise BaselineError(f"{BASELINE_PATH} has no managed_installs array to empty")
    text = text[:managed.start()] + "\t<key>managed_installs</key>\n\t<array>\n\t</array>\n" \
        + text[managed.end():]

    block = "\t<key>optional_installs</key>\n\t<array>\n" \
        + "".join(f"\t\t<string>{item}</string>\n" for item in merged) + "\t</array>\n"
    existing_optional = _array_block(text, "optional_installs")
    if existing_optional:
        text = text[:existing_optional.start()] + block + text[existing_optional.end():]
    else:
        closing = text.rindex("</dict>")
        text = text[:closing] + block + text[closing:]

    try:
        result = plistlib.loads(text.encode("utf-8"))
    except Exception as exc:                                   # pragma: no cover - safety net
        raise BaselineError(f"the edit would break {BASELINE_PATH}: {exc}")
    if result.get("managed_installs") != []:
        raise BaselineError("the forced core did not end up empty")
    if result.get("optional_installs") != merged:
        raise BaselineError("the optional list did not end up as intended")

    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)

    record = {"at": at, "approved_by": approved_by, "reason": reason,
              "manifest": BASELINE_PATH, "item_count": len(forced),
              "items": forced, "now_listed_as": "optional_installs",
              "how_to_reverse": "move these items from optional_installs back to managed_installs "
                                "in manifests/all; this record is the list"}
    write = os.path.join(source_root, record_path)
    os.makedirs(os.path.dirname(write), exist_ok=True)
    with open(write, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, sort_keys=True)
    return record


def forced_installs(source_root: str) -> Dict[str, List[str]]:
    """Every forced-install section in every manifest, for the check that none is left."""
    from .drift import load_manifests
    forcing = ("managed_installs", "default_installs", "forced_installs")
    out: Dict[str, List[str]] = {}
    for name, body in load_manifests(source_root).items():
        for key in forcing:
            if body.get(key):
                out[f"{name}.{key}"] = list(body[key])
    return out
