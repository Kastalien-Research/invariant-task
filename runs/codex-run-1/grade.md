task: /Users/b.c.nims/dev/employment-ops-home/mechanize/invariant-task/runs/codex-run-1/work

| check | result | detail |
|---|---|---|
| H1 visible tests green | PASS | 17 passed in 0.06s |
| H2 tests/ and faults.py unmodified | FAIL | modified/missing: tests/test_reliability.py |
| H3 sqlite opened only via store.py | PASS | ok |
| H4 fault hook still live | PASS | exit=137 |
| I1 retries cannot create duplicate effects | PASS | ...                                                                      [100%] |
| I2 terminal transitions cannot regress | PASS | ....                                                                     [100%] |
| I3 ancillary failure cannot veto the core operation | PASS | ..                                                                       [100%] |
| I4 crash/restart preserves intended state | PASS | ......ssssssssss...............s                                         [100%] |

holds: FAIL   invariants: 4/4
