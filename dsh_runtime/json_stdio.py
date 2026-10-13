"""UTF-8 helpers for the Runtime's JSON process boundaries."""

from __future__ import annotations

import io
import json
from typing import Any, BinaryIO, Iterator, TextIO


def _byte_stream(stream: TextIO | BinaryIO) -> TextIO | BinaryIO:
    buffer = getattr(stream, "buffer", None)
    return buffer if buffer is not None else stream


def read_json_document(stream: TextIO | BinaryIO) -> Any:
    """Read one JSON document, using UTF-8 when the stream exposes bytes."""

    payload = _byte_stream(stream).read()
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    return json.loads(payload)


def iter_input_lines(stream: TextIO | BinaryIO) -> Iterator[str | bytes]:
    """Iterate over a stream's raw lines without applying a locale encoding."""

    yield from _byte_stream(stream)


def write_json_line(
    stream: TextIO | BinaryIO, value: Any, *, sort_keys: bool = False
) -> None:
    """Write compact JSON as UTF-8, escaping only unencodable surrogates."""

    payload = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=sort_keys,
    )
    encoded = payload.encode("utf-8", errors="backslashreplace") + b"\n"
    buffer = getattr(stream, "buffer", None)
    if buffer is not None:
        buffer.write(encoded)
        buffer.flush()
        return
    if isinstance(stream, (io.BufferedIOBase, io.RawIOBase)):
        stream.write(encoded)
        stream.flush()
        return

    # StringIO and similar test streams have no byte buffer. The serialized
    # text is valid UTF-8 because isolated surrogates were escaped above.
    stream.write(encoded.decode("utf-8"))
    stream.flush()
