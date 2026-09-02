"""Evaluator qualification: the grader must separate S0, reference and
witnesses exactly as declared BEFORE any agent is run against it.

    python qualify.py

Each overlay directory under reference/ and witnesses/ is copied over a
fresh copy of task/, then graded. EXPECT maps overlay -> set of invariants
expected to FAIL (all holds expected to PASS everywhere).
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from grade import grade  # noqa: E402

ALL = {"I1", "I2", "I3", "I4", "I5"}
EXPECT: dict[str, set[str]] = {
    "task": ALL,                       # S0: baseline gate, must fail everything
    "reference": set(),
    "witnesses/w1-inmemory-idempotency": {"I1"},
    "witnesses/w2-start-regresses-terminal": {"I2"},
    "witnesses/w3-notify-failure-vetoes": {"I3", "I5"},   # rollback under a poisoned job rejects commands
    "witnesses/w3b-swallow-and-drop": {"I3", "I4", "I5"},  # dropped poisoned notifications; others lost too
    "witnesses/w4-separate-transactions": {"I4"},
    "witnesses/w4b-mark-before-send": {"I4"},
    "witnesses/w5-head-of-line-blocking": {"I5"},
}


def materialize(overlay: str, dest: Path) -> Path:
    shutil.copytree(ROOT / "task", dest, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".venv"))
    if overlay.startswith("witnesses/"):
        # witnesses are deltas on the reference, not on S0
        shutil.copytree(ROOT / "reference", dest, dirs_exist_ok=True)
    if overlay != "task":
        shutil.copytree(ROOT / overlay, dest, dirs_exist_ok=True)
    return dest


def main() -> int:
    rows = []
    bad = 0
    for overlay, expect_fail in EXPECT.items():
        if not (ROOT / overlay).exists():
            rows.append((overlay, "MISSING", "", ""))
            bad += 1
            continue
        with tempfile.TemporaryDirectory() as d:
            task = materialize(overlay, Path(d) / "t")
            rep = grade(task)
        failed = {k.split()[0] for k, v in rep["invariants"].items() if not v["pass"]}
        holds_ok = rep["holds_pass"]
        verdict = "OK" if (failed == expect_fail and holds_ok) else "MISMATCH"
        bad += verdict != "OK"
        rows.append((overlay, verdict, "fails " + (",".join(sorted(failed)) or "none"),
                     "holds " + ("pass" if holds_ok else "FAIL: " + "; ".join(k for k, v in rep["holds"].items() if not v["pass"]))))
    w = max(len(r[0]) for r in rows)
    for r in rows:
        print(f"{r[0]:<{w}}  {r[1]:<9} {r[2]:<24} {r[3]}")
    print("\nQUALIFIED" if bad == 0 else f"\nUNQUALIFIED ({bad} mismatch)")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
