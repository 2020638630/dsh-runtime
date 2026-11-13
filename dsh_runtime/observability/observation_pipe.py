"""Serialize bounded observation frames without blocking their producers."""

import os


def write_observation_frame(pipe, fd: int | None, line: str, lock) -> None:
    # The lock belongs to one Run, never the process/module.
    # Only background senders acquire this lock. It prevents C1 and B frames
    # from interleaving if a pipe write is partial; their queues remain separate.
    with lock:
        if fd is None:
            pipe.write(line)
            pipe.flush()
        else:
            remaining = memoryview(line.encode("utf-8"))
            while remaining:
                written = os.write(fd, remaining)
                if written <= 0:
                    raise OSError("observation pipe made no progress")
                remaining = remaining[written:]
