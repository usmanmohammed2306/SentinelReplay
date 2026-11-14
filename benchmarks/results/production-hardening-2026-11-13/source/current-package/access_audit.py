"""One exclusive durable writer per running controller, serialized across requests.

Startup verifies the existing chain once. Every appended access record is fsynced
before access proceeds. The root is trusted controller storage; this is not an
immutability claim against a host administrator that can ignore advisory locks.
"""

import threading
from contextlib import AbstractContextManager
from pathlib import Path

from sentinel_replay.journal import Journal, JournalWriter, Verification


class AccessAudit:
    def __init__(self, path: Path) -> None:
        self.journal = Journal(path)
        self.guard = threading.Lock()
        self.context: AbstractContextManager[JournalWriter] | None = None
        self.writer: JournalWriter | None = None

    def start(self) -> None:
        with self.guard:
            if self.writer is not None:
                return
            context = self.journal.writer()
            writer = context.__enter__()
            self.context, self.writer = context, writer

    def append(self, event: object) -> Verification:
        with self.guard:
            return self.writer.append(event) if self.writer else self.journal.append(event)

    def close(self) -> None:
        with self.guard:
            if self.context is not None:
                self.context.__exit__(None, None, None)
            self.context, self.writer = None, None
