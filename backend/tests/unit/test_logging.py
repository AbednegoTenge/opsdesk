import json
import logging

from apps.core.logging import JsonFormatter


def test_json_formatter_includes_extra_fields():
    record = logging.makeLogRecord(
        {
            "name": "opsdesk",
            "levelname": "INFO",
            "msg": "hello %s",
            "args": ("world",),
            "user_id": 7,
        }
    )
    out = json.loads(JsonFormatter().format(record))
    assert out["message"] == "hello world"
    assert out["user_id"] == 7
    assert out["level"] == "INFO"
