task: /Users/b.c.nims/dev/employment-ops-home/mechanize/invariant-task/runs/codex-run-2/work

| check | result | detail |
|---|---|---|
| H1 visible tests green | PASS | 9 passed in 0.04s |
| H2 tests/ and faults.py unmodified | PASS | ok |
| H3 sqlite opened only via store.py | PASS | ok |
| H4 fault hook still live | PASS | exit=137 |
| I1 retries cannot create duplicate effects | PASS | ...                                                                      [100%] |
| I2 terminal transitions cannot regress | PASS | ....                                                                     [100%] |
| I3 ancillary failure cannot veto the core operation | PASS | ..                                                                       [100%] |
| I4 crash/restart preserves intended state | PASS | ......ssssssssss...............s                                         [100%] |
| I5 one undeliverable notification cannot block the others | PASS | ..                                                                       [100%] |

holds: PASS   invariants: 5/5
