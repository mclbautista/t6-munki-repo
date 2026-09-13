"""Evidence pointers in tickets and ADRs must resolve to a file git actually tracks.

A ticket that cites evidence nobody can open is the same defect as a claim with no source: it reads
as verification while offering none. This caught a real one - a ticket pointing at
`docs/evidence/07-initial-promotion-plan.txt` when the file existed only in the ignored scratch
directory.
"""
import os
import re
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POINTER = re.compile(r"docs/evidence/[A-Za-z0-9._/\-]+")


def tracked_evidence():
    out = subprocess.run(["git", "ls-files", "docs/evidence"], cwd=ROOT, capture_output=True,
                         text=True)
    if out.returncode != 0:
        pytest.skip("not a git checkout")
    return set(out.stdout.split())


def test_every_evidence_pointer_resolves_to_a_tracked_file():
    tracked = tracked_evidence()
    if not tracked:
        pytest.skip("no evidence is tracked yet")
    documents = []
    for base in ("docs", ".scratch"):
        for root, dirs, files in os.walk(os.path.join(ROOT, base)):
            dirs[:] = [d for d in dirs if d != "evidence"]
            documents += [os.path.join(root, f) for f in files if f.endswith(".md")]
    unresolved = []
    for path in documents:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for ref in POINTER.findall(fh.read()):
                ref = ref.rstrip(".,)`")
                if ref not in tracked:
                    unresolved.append(f"{os.path.relpath(path, ROOT)} -> {ref}")
    assert not unresolved, "evidence cited but not in git:\n" + "\n".join(sorted(set(unresolved)))
