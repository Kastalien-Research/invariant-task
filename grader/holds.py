"""Hold predicates: things that must stay true regardless of the change.

H1 visible tests pass
H2 tests/ and relay/faults.py are byte-identical to the lock
H3 sqlite is opened only in relay/store.py
H4 the fault hook is still live (a fault spec still kills the process)
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from harness import HERE, cmd, run_life, task_dir

LOCK = HERE / "lock.json"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def locked_files(root: Path) -> dict[str, str]:
    files = sorted(list((root / "tests").glob("*.py")) + [root / "relay" / "faults.py"])
    return {str(f.relative_to(root)): _sha(f) for f in files}


def write_lock(root: Path) -> None:
    LOCK.write_text(json.dumps(locked_files(root), indent=1) + "\n")


def h1_visible_tests(root: Path) -> tuple[bool, str]:
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"],
                       cwd=root, capture_output=True, text=True, timeout=300)
    tail = (p.stdout.strip().splitlines() or ["?"])[-1].strip()
    return p.returncode == 0, tail


def h2_lock(root: Path) -> tuple[bool, str]:
    if not LOCK.exists():
        return False, "no lock.json; run `python -m holds --lock` against S0"
    expected = json.loads(LOCK.read_text())
    actual = locked_files(root)
    diff = sorted(set(expected.items()) ^ set(actual.items()))
    return not diff, "modified/missing: " + ", ".join(sorted({k for k, _ in diff})) if diff else "ok"


def h3_single_sqlite_entry(root: Path) -> tuple[bool, str]:
    bad = []
    for f in (root / "relay").rglob("*.py"):
        if f.name in ("store.py", "faults.py"):  # faults.py is hash-locked by H2
            continue
        if re.search(r"sqlite3\s*\.\s*connect\s*\(", f.read_text()):
            bad.append(str(f.relative_to(root)))
    return not bad, ("ok" if not bad else "sqlite opened outside store.py: " + ", ".join(bad))


def h4_fault_hook_live(root: Path) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory() as d:
        db = Path(d) / "relay.db"
        life = run_life(db, "http://127.0.0.1:9/notify", [{"handle": cmd("create", "j1")}], fault="write:1")
        return life.crashed, f"exit={life.exit_code}"


CHECKS = [
    ("H1 visible tests green", h1_visible_tests),
    ("H2 tests/ and faults.py unmodified", h2_lock),
    ("H3 sqlite opened only via store.py", h3_single_sqlite_entry),
    ("H4 fault hook still live", h4_fault_hook_live),
]


def run_holds(root: Path | None = None) -> dict[str, tuple[bool, str]]:
    root = root or task_dir()
    return {name: fn(root) for name, fn in CHECKS}


if __name__ == "__main__":
    if "--lock" in sys.argv:
        write_lock(task_dir())
        print(f"locked {len(json.loads(LOCK.read_text()))} files -> {LOCK}")
    else:
        for name, (okk, detail) in run_holds().items():
            print(f"{'PASS' if okk else 'FAIL'}  {name}  ({detail})")
