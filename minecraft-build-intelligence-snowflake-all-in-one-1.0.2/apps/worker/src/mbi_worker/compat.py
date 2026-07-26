from __future__ import annotations

import os
from dataclasses import dataclass
from functools import update_wrapper
from typing import Any, Callable


@dataclass
class InlineResult:
    value: Any = None
    error: Exception | None = None

    def get(self, timeout: float | None = None) -> Any:
        del timeout
        if self.error:
            raise self.error
        return self.value


class InlineTask:
    def __init__(self, function: Callable[..., Any], *, bind: bool, name: str) -> None:
        self.function = function
        self.bind = bind
        self.name = name
        update_wrapper(self, function)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        if self.bind:
            return self.function(_InlineContext(), *args, **kwargs)
        return self.function(*args, **kwargs)

    def delay(self, *args: Any, **kwargs: Any) -> InlineResult:
        try:
            return InlineResult(self(*args, **kwargs))
        except Exception as exc:
            return InlineResult(error=exc)

    apply_async = delay


class _InlineContext:
    def __init__(self) -> None:
        self.states: list[tuple[str, dict[str, Any] | None]] = []

    def update_state(self, *, state: str, meta: dict[str, Any] | None = None) -> None:
        self.states.append((state, meta))


class InlineCelery:
    """Development-only execution shim used when Celery is unavailable.

    It is intentionally rejected in production so a deployment cannot accidentally
    claim durable execution while running jobs in-process.
    """

    def __init__(self, main: str, **_: Any) -> None:
        if os.getenv("MBI_ENV", "development") == "production":
            raise RuntimeError("Celery is required in production; inline worker fallback is disabled")
        self.main = main
        self.tasks: dict[str, InlineTask] = {}
        self.conf = _InlineConfig()

    def task(self, *decorator_args: Any, **decorator_kwargs: Any):
        def decorate(function: Callable[..., Any]) -> InlineTask:
            task = InlineTask(function, bind=bool(decorator_kwargs.get("bind", False)), name=decorator_kwargs.get("name", function.__name__))
            self.tasks[task.name] = task
            return task
        if decorator_args and callable(decorator_args[0]):
            return decorate(decorator_args[0])
        return decorate


class _InlineConfig(dict):
    def update(self, *args: Any, **kwargs: Any) -> None:
        super().update(*args, **kwargs)
