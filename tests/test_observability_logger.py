from __future__ import annotations

import json

from dsh_runtime.observability.logger import logger, record


def test_log_record_is_ascii_safe_for_lone_surrogates(monkeypatch) -> None:
    messages: list[str] = []
    monkeypatch.setattr(logger, "info", messages.append)

    record("task_failed", error="失败" + chr(0xDC94))

    assert len(messages) == 1
    messages[0].encode("ascii")
    assert json.loads(messages[0])["error"] == "失败" + chr(0xDC94)
