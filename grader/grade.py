"""Grade a task directory: hold predicates + four invariants. Binary per invariant.

    python grade.py [--task DIR] [--json OUT]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
INVARIANTS = [
    ("I1 retries cannot create duplicate effects", "test_i1_idempotency.py"),
    ("I2 terminal transitions cannot regress", "test_i2_terminal.py"),
    ("I3 ancillary failure cannot veto the core operation", "test_i3_ancillary.py"),
    ("I4 crash/restart preserves intended state", "test_i4_crash.py"),
]


def run_invariant(test_file: str, task: Path) -> tuple[bool, str]:
    env = dict(os.environ, RELAY_TASK_DIR=str(task))
    p = subprocess.run([sys.executable, "-m", "pytest", test_file, "-q", "-p", "no:cacheprovider", "-x"],
                       cwd=HERE, env=env, capture_output=True, text=True, timeout=900)
    lines = [l for l in p.stdout.splitlines() if l.strip()]
    summary = lines[-1] if lines else p.stderr.strip().splitlines()[-1:] or ["?"]
    first_fail = next((l.strip() for l in lines if l.startswith("E ") or "AssertionError" in l), "")
    return p.returncode == 0, (summary if isinstance(summary, str) else summary[0]) + (f" | {first_fail}" if first_fail else "")


def grade(task: Path) -> dict:
    sys.path.insert(0, str(HERE))
    os.environ["RELAY_TASK_DIR"] = str(task)
    from holds import run_holds  # noqa: E402

    holds = {k: {"pass": v[0], "detail": v[1]} for k, v in run_holds(task).items()}
    inv = {}
    for name, f in INVARIANTS:
        okk, detail = run_invariant(f, task)
        inv[name] = {"pass": okk, "detail": detail}
    return {"task": str(task), "holds": holds, "invariants": inv,
            "holds_pass": all(h["pass"] for h in holds.values()),
            "score": sum(1 for i in inv.values() if i["pass"])}


def render(report: dict) -> str:
    out = [f"task: {report['task']}", "", "| check | result | detail |", "|---|---|---|"]
    for k, v in report["holds"].items():
        out.append(f"| {k} | {'PASS' if v['pass'] else 'FAIL'} | {v['detail']} |")
    for k, v in report["invariants"].items():
        out.append(f"| {k} | {'PASS' if v['pass'] else 'FAIL'} | {v['detail']} |")
    out.append("")
    out.append(f"holds: {'PASS' if report['holds_pass'] else 'FAIL'}   invariants: {report['score']}/4")
    return "\n".join(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default=str(HERE.parent / "task"))
    ap.add_argument("--json")
    a = ap.parse_args()
    rep = grade(Path(a.task).resolve())
    print(render(rep))
    if a.json:
        Path(a.json).write_text(json.dumps(rep, indent=1) + "\n")
