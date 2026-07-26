from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, AsyncIterator, Protocol


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    text_input: bool = True
    image_input: bool = False
    tool_calling: bool = False
    structured_output: bool = False
    streaming: bool = False
    max_images: int = 0
    max_context_tokens: int = 0
    max_output_tokens: int = 0
    supported_image_formats: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ModelRequest:
    model: str
    messages: tuple[dict[str, Any], ...]
    tools: tuple[dict[str, Any], ...] = ()
    max_output_tokens: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ModelResponse:
    request_id: str
    text: str
    tool_calls: tuple[dict[str, Any], ...]
    usage: dict[str, int]


class ModelEventType(StrEnum):
    TEXT_DELTA = "text_delta"
    TOOL_CALL = "tool_call"
    USAGE = "usage"
    COMPLETE = "complete"


@dataclass(frozen=True, slots=True)
class ModelEvent:
    type: ModelEventType
    payload: dict[str, Any]


class MultimodalProvider(Protocol):
    async def get_capabilities(self) -> ProviderCapabilities: ...
    async def count_or_estimate_tokens(self, request: ModelRequest) -> int: ...
    async def create_response(self, request: ModelRequest) -> ModelResponse: ...
    def stream_response(self, request: ModelRequest) -> AsyncIterator[ModelEvent]: ...
    async def cancel(self, request_id: str) -> None: ...
