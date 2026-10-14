"""A tamper-evident trace (Chapter 15).

Each entry carries a fingerprint (hash) of the entry before it. If anyone
changes an old entry, every fingerprint after it breaks.
Rule: log what happened and why (rule names, counts, IDs), never the data.
"""
import hashlib
import json
import time
import uuid


def _digest(prev, event):
    body = json.dumps(event, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256((prev + body).encode("utf-8")).hexdigest()


class Trace:
    def __init__(self, run_id=None):
        self.run_id = run_id or uuid.uuid4().hex[:8]
        self.entries = []
        self._t0 = time.monotonic()

    def log(self, step, status, **facts):
        event = {
            "run_id": self.run_id,
            "step": step,
            "status": status,
            "t_ms": round((time.monotonic() - self._t0) * 1000),
            **facts,
        }
        prev = self.entries[-1]["hash"] if self.entries else "0" * 64
        self.entries.append({"event": event, "prev": prev, "hash": _digest(prev, event)})
        return event

    def verify(self):
        prev = "0" * 64
        for entry in self.entries:
            if entry["prev"] != prev or entry["hash"] != _digest(prev, entry["event"]):
                return False
            prev = entry["hash"]
        return True

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            for e in self.entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
