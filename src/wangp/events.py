from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, TextIO


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Event:
    type: str
    data: dict[str, Any] = field(default_factory=dict)
    time: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.update(self.data)
        payload.pop("data", None)
        return payload


class Emitter:
    def __init__(self, fmt: str = "text", stream: TextIO | None = None) -> None:
        if fmt not in {"text", "json"}:
            raise ValueError(f"unsupported format: {fmt}")
        self.fmt = fmt
        self.stream = stream or sys.stdout

    def emit(self, type: str, **data: Any) -> Event:
        event = Event(type=type, data=data)
        if self.fmt == "json":
            self.stream.write(json.dumps(event.to_dict(), ensure_ascii=True) + "\n")
        else:
            self.stream.write(self._format_text(event) + "\n")
        self.stream.flush()
        return event

    def _format_text(self, event: Event) -> str:
        if event.type == "progress":
            phase = event.data.get("phase", "")
            current = event.data.get("step")
            total = event.data.get("total")
            status = event.data.get("status") or phase
            if current is not None and total:
                return f"  [{current}/{total}] {status}"
            return f"  {status}"
        if event.type == "status":
            return str(event.data.get("message", ""))
        if event.type == "file":
            return f"  saved {event.data.get('path')}"
        if event.type == "error":
            return f"error: {event.data.get('message')}"
        if event.type == "done":
            ok = event.data.get("success", False)
            elapsed = event.data.get("elapsed")
            suffix = f" in {elapsed}" if elapsed else ""
            return f"{'done' if ok else 'failed'}{suffix}"
        if event.type == "step":
            return f"[{event.data.get('index')}/{event.data.get('count')}] {event.data.get('id')}: {event.data.get('kind')}"
        parts = [event.type]
        if event.data:
            parts.append(json.dumps(event.data, ensure_ascii=True))
        return " ".join(parts)
