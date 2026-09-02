"""relay: a small job dispatcher.

Commands come in (`Dispatcher.handle`), state changes are appended to an
event log (`Store`), and each state change is announced to an external sink
(`Notifier`).
"""
