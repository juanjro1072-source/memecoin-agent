"""Memoria del radar: evita repetir alertas, salvo que el hype siga escalando."""

from __future__ import annotations

import json
import time
from pathlib import Path

TTL_SECONDS = 24 * 3600
ESCALATION_POINTS = 15  # re-alerta si el hype sube al menos esto desde la última alerta


class AlertMemory:
    def __init__(self, path: Path | None):
        self.path = path
        self.data: dict[str, dict] = {}
        if path and path.exists():
            try:
                self.data = json.loads(path.read_text())
            except (OSError, ValueError):
                self.data = {}
        self._prune()

    def _prune(self) -> None:
        cutoff = time.time() - TTL_SECONDS
        self.data = {k: v for k, v in self.data.items() if v.get("ts", 0) >= cutoff}

    def should_alert(self, key: str, hype: int) -> str | None:
        """Devuelve el motivo de la alerta ("nuevo", "escalando") o None."""
        prev = self.data.get(key)
        if prev is None:
            return "nuevo"
        if hype - prev.get("hype", 0) >= ESCALATION_POINTS:
            return f"escalando +{hype - prev['hype']}"
        return None

    def remember(self, key: str, hype: int) -> None:
        self.data[key] = {"hype": hype, "ts": time.time()}

    def save(self) -> None:
        if self.path:
            self.path.write_text(json.dumps(self.data, indent=2))
