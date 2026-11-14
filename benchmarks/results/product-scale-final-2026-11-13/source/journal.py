"""Append only, locally tamper evident evidence journal."""

import fcntl
import io
import json
import os
import stat
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from sentinel_replay.canonical import CanonicalizationError, event_digest, load_json_unique

GENESIS = "sha256:" + "0" * 64
MAX_BATCH_EVENTS = 50_000
MAX_BATCH_BYTES = 64 * 1024 * 1024
WRITE_CHUNK_ROWS = 1_024


class JournalCorruption(ValueError):
    """The journal is malformed or its hash chain does not verify."""


@dataclass(frozen=True)
class Verification:
    records: int
    root: str


def _read_verified_stream(
    source: BinaryIO,
    *,
    collect: bool = True,
    visit: Callable[[int, object], None] | None = None,
) -> tuple[list[dict[str, Any]], Verification]:
    records: list[dict[str, Any]] = []
    previous = GENESIS
    count = 0
    for index, raw_line in enumerate(source, 1):
        try:
            if not raw_line.endswith(b"\n"):
                raise JournalCorruption("unterminated line")
            row = load_json_unique(raw_line.decode("utf-8"))
            if not isinstance(row, dict) or set(row) != {"index", "previous", "event", "hash"}:
                raise JournalCorruption("invalid record shape")
            if type(row["index"]) is not int or not all(
                isinstance(row[field], str) for field in ("previous", "hash")
            ):
                raise JournalCorruption("invalid record field types")
            if row["index"] != index or row["previous"] != previous:
                raise JournalCorruption("broken sequence or previous hash")
            expected = event_digest({"index": index, "previous": previous, "event": row["event"]})
            if row["hash"] != expected:
                raise JournalCorruption("hash mismatch")
        except (CanonicalizationError, UnicodeDecodeError, TypeError) as error:
            raise JournalCorruption(f"record {index}: {error}") from error
        except JournalCorruption as error:
            raise JournalCorruption(f"record {index}: {error}") from error
        if collect:
            records.append(row)
        if visit is not None:
            visit(index - 1, row["event"])
        previous = expected
        count = index
    return records, Verification(count, previous)


def verify_journal_bytes(data: bytes) -> Verification:
    """Verify a journal already held in memory, without trusting a filesystem path."""
    return _read_verified_stream(io.BytesIO(data), collect=False)[1]


def _encode_record(index: int, previous: str, event: object) -> tuple[bytes, str]:
    digest = event_digest({"index": index, "previous": previous, "event": event})
    row = {"index": index, "previous": previous, "event": event, "hash": digest}
    try:
        encoded = (
            json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise CanonicalizationError(f"journal event is not JSON compatible: {error}") from error
    return encoded, digest


def _open_writer(path: Path) -> tuple[BinaryIO, bool]:
    created = not path.exists() and not path.is_symlink()
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise JournalCorruption("journal path must be a regular file")
        return os.fdopen(descriptor, "a+b"), created
    except BaseException:
        os.close(descriptor)
        raise


def _fsync_parent(path: Path) -> None:
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


class JournalWriter:
    """Exclusive durable per-event writer for a bounded recording session."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._destination: BinaryIO | None = None
        self.verification: Verification | None = None

    def __enter__(self) -> "JournalWriter":
        if self._destination is not None:
            raise RuntimeError("journal writer is already open")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        destination, created = _open_writer(self.path)
        try:
            fcntl.flock(destination.fileno(), fcntl.LOCK_EX)
            destination.seek(0)
            self.verification = _read_verified_stream(destination, collect=False)[1]
            if created:
                _fsync_parent(self.path)
        except BaseException:
            destination.close()
            raise
        self._destination = destination
        return self

    def append(self, event: object) -> Verification:
        destination = self._destination
        current = self.verification
        if destination is None or current is None:
            raise RuntimeError("journal writer is not open")
        encoded, digest = _encode_record(current.records + 1, current.root, event)
        destination.seek(0, os.SEEK_END)
        destination.write(encoded)
        destination.flush()
        os.fsync(destination.fileno())
        self.verification = Verification(current.records + 1, digest)
        return self.verification

    def read_verified(self) -> tuple[list[object], Verification]:
        """Read a consistent verified journal through the held, exclusive descriptor."""
        destination = self._destination
        current = self.verification
        if destination is None or current is None:
            raise RuntimeError("journal writer is not open")
        destination.flush()
        destination.seek(0)
        rows, verified = _read_verified_stream(destination)
        if verified != current:
            raise JournalCorruption("journal changed during locked read")
        return [row["event"] for row in rows], verified

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        if self._destination is not None:
            self._destination.close()
            self._destination = None


class Journal:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _read_verified(self) -> tuple[list[dict[str, Any]], Verification]:
        if not self.path.exists():
            return [], Verification(0, GENESIS)
        with self.path.open("rb") as source:
            return _read_verified_stream(source)

    def verify(self) -> Verification:
        """Validate every record and return its final root."""
        if not self.path.exists():
            raise FileNotFoundError(f"journal does not exist: {self.path}")
        with self.path.open("rb") as source:
            return _read_verified_stream(source, collect=False)[1]

    def events(self) -> list[object]:
        """Read events only after the complete chain has verified."""
        return [row["event"] for row in self._read_verified()[0]]

    def read_verified(self) -> tuple[list[object], Verification]:
        """Return events and root from one complete verified read."""
        if not self.path.exists():
            raise FileNotFoundError(f"journal does not exist: {self.path}")
        rows, verified = self._read_verified()
        return [row["event"] for row in rows], verified

    def scan_verified(self, visit: Callable[[int, object], None]) -> Verification:
        """Scan without retaining rows; visitor must have no external side effects.

        The visitor sees a verified prefix. If any later record is corrupt, this
        method raises instead of returning a root; callers must discard derived
        state and never publish partial results.
        """
        if not self.path.exists():
            raise FileNotFoundError(f"journal does not exist: {self.path}")
        with self.path.open("rb") as source:
            return _read_verified_stream(source, collect=False, visit=visit)[1]

    def append(self, event: object) -> Verification:
        """Lock the writer, verify existing evidence, then durably append one row."""
        return self.append_many((event,))

    def writer(self) -> JournalWriter:
        """Create a context-managed per-event writer with one initial chain scan."""
        return JournalWriter(self.path)

    def append_many(self, events: Iterable[object]) -> Verification:
        """Verify once and append a bounded batch with one durable flush.

        The batch is fully encoded before writing, so invalid events cannot cause
        a partial batch. A process crash during the write may leave a torn tail,
        which the verifier rejects; crash repair is a separate release feature.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        destination, created = _open_writer(self.path)
        with destination:
            fcntl.flock(destination.fileno(), fcntl.LOCK_EX)
            destination.seek(0)
            current = _read_verified_stream(destination, collect=False)[1]
            if created:
                _fsync_parent(self.path)
            previous = current.root
            encoded_rows: list[bytes] = []
            total_bytes = 0
            for offset, event in enumerate(events, 1):
                if offset > MAX_BATCH_EVENTS:
                    raise ValueError("journal batch exceeds event limit")
                index = current.records + offset
                encoded, digest = _encode_record(index, previous, event)
                total_bytes += len(encoded)
                if total_bytes > MAX_BATCH_BYTES:
                    raise ValueError("journal batch exceeds byte limit")
                encoded_rows.append(encoded)
                previous = digest
            if not encoded_rows:
                return current
            destination.seek(0, os.SEEK_END)
            for start in range(0, len(encoded_rows), WRITE_CHUNK_ROWS):
                destination.write(b"".join(encoded_rows[start : start + WRITE_CHUNK_ROWS]))
            destination.flush()
            os.fsync(destination.fileno())
        return Verification(current.records + len(encoded_rows), previous)
