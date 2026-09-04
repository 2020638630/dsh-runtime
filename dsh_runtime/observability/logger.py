"""JSON-line event logger with no external dependency."""

import json
import logging
from datetime import datetime, timezone
from typing import Any


logger = logging.getLogger("dsh_runtime")


def record(event: str, **fields: Any) -> None:
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **fields,
    }
    logger.info(json.dumps(payload, ensure_ascii=False, default=str))
