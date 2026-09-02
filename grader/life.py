"""One process lifetime of the dispatcher, driven by a JSON step script.

Steps:  {"handle": <command>}   -> records {"step", "result"} or {"step", "exception"}
        {"pump": <n>}           -> calls Dispatcher.pump() n times, records {"step", "pumped"}
Each record is flushed as soon as it is produced, so a crash leaves a
truthful prefix.
"""
from __future__ import annotations

import argparse
import json
import sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True)
    ap.add_argument("--db", required=True)
    ap.add_argument("--sink", required=True)
    ap.add_argument("--script", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    sys.path.insert(0, a.task)
    from relay.dispatcher import Dispatcher  # noqa: E402
    from relay.notifier import Notifier  # noqa: E402
    from relay.store import Store  # noqa: E402

    steps = json.loads(open(a.script).read())
    store = Store(a.db)
    d = Dispatcher(store, Notifier(a.sink))
    with open(a.out, "a") as out:
        for i, step in enumerate(steps):
            rec: dict = {"step": i}
            try:
                if "handle" in step:
                    rec["result"] = d.handle(step["handle"])
                elif "pump" in step:
                    total = 0
                    for _ in range(int(step["pump"])):
                        total += int(d.pump() or 0)
                    rec["pumped"] = total
                else:
                    rec["exception"] = f"unknown step {step!r}"
            except Exception as e:  # noqa: BLE001
                rec["exception"] = f"{type(e).__name__}: {e}"
            out.write(json.dumps(rec) + "\n")
            out.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
