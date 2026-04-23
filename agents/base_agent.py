"""
Base class for all migration agents.
"""
from __future__ import annotations
import logging
import time
import json
import traceback
from pathlib import Path
from typing import Any, Callable, Optional


class AgentResult:
    def __init__(self, success: bool, data: Any = None, error: str = ""):
        self.success = success
        self.data = data
        self.error = error

    def __repr__(self):
        status = "OK" if self.success else f"FAIL({self.error[:60]})"
        return f"AgentResult({status})"


class BaseAgent:
    """
    Base migration agent. Subclasses override `run()`.
    Provides:
      - Structured logging
      - Retry with exponential back-off
      - State persistence (JSON sidecar in workspace)
      - Progress reporting
    """
    name: str = "base"

    def __init__(self, workspace_dir: str, log_dir: str):
        self.workspace_dir = Path(workspace_dir)
        self.log_dir = Path(log_dir)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.log = logging.getLogger(self.name)
        self._state_file = self.workspace_dir / f"{self.name}_state.json"
        self._state: dict[str, Any] = self._load_state()
        self._progress_callbacks: list[Callable] = []

    # ── state persistence ─────────────────────────────────────────────────────

    def _load_state(self) -> dict[str, Any]:
        if self._state_file.exists():
            try:
                return json.loads(self._state_file.read_text())
            except Exception:
                pass
        return {}

    def _save_state(self) -> None:
        self._state_file.write_text(json.dumps(self._state, indent=2, default=str))

    def get_state(self, key: str, default=None):
        return self._state.get(key, default)

    def set_state(self, key: str, value) -> None:
        self._state[key] = value
        self._save_state()

    def mark_done(self, item_key: str) -> None:
        done = self._state.setdefault("done", [])
        if item_key not in done:
            done.append(item_key)
            self._save_state()

    def is_done(self, item_key: str) -> bool:
        return item_key in self._state.get("done", [])

    # ── progress ──────────────────────────────────────────────────────────────

    def add_progress_callback(self, cb: Callable) -> None:
        self._progress_callbacks.append(cb)

    def _report(self, message: str, current: int = 0, total: int = 0) -> None:
        self.log.info("[%s] %s (%d/%d)", self.name, message, current, total)
        for cb in self._progress_callbacks:
            try:
                cb(agent=self.name, message=message, current=current, total=total)
            except Exception:
                pass

    # ── retry ─────────────────────────────────────────────────────────────────

    def retry(self, fn: Callable, *args,
               attempts: int = 3, delay: float = 2.0,
               label: str = "", **kwargs) -> Any:
        last_exc: Optional[Exception] = None
        for attempt in range(1, attempts + 1):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                self.log.warning(
                    "[%s] attempt %d/%d failed for %s: %s",
                    self.name, attempt, attempts, label, exc,
                )
                if attempt < attempts:
                    time.sleep(delay * (2 ** (attempt - 1)))
        raise RuntimeError(
            f"All {attempts} attempts failed for {label}: {last_exc}"
        ) from last_exc

    # ── abstract ──────────────────────────────────────────────────────────────

    def run(self, **kwargs) -> AgentResult:
        raise NotImplementedError

    def execute(self, **kwargs) -> AgentResult:
        """Public entry point with top-level exception capture."""
        try:
            return self.run(**kwargs)
        except Exception as exc:
            self.log.error(
                "[%s] Unhandled exception: %s\n%s",
                self.name, exc, traceback.format_exc(),
            )
            return AgentResult(success=False, error=str(exc))
