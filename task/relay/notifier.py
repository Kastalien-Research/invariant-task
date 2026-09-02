"""Announce state changes to an external sink over HTTP."""
from __future__ import annotations

import json
import urllib.error
import urllib.request


class NotifyError(Exception):
    pass


class Notifier:
    def __init__(self, sink_url: str, timeout: float = 2.0):
        self.sink_url = sink_url
        self.timeout = timeout

    def send(self, notification: dict) -> None:
        """POST one notification. Raises NotifyError on any failure."""
        body = json.dumps(notification).encode()
        req = urllib.request.Request(
            self.sink_url, data=body, method="POST", headers={"content-type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status >= 300:
                    raise NotifyError(f"sink returned {resp.status}")
        except urllib.error.HTTPError as e:
            raise NotifyError(f"sink returned {e.code}") from e
        except (urllib.error.URLError, OSError) as e:
            raise NotifyError(f"sink unreachable: {e}") from e
