import logging
from typing import List


class TextualLogHandler(logging.Handler):
    """A minimal logging handler that appends formatted messages to a list.

    The actual Textual UI will read from this sink and render messages.
    """

    def __init__(self, sink: List[str]):
        super().__init__()
        self.sink = sink

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
        except Exception:  # pragma: no cover - formatting error should not crash
            msg = record.getMessage()
        self.sink.append(msg)

