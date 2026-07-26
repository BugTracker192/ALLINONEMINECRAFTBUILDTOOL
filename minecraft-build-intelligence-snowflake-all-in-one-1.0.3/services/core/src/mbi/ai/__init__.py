"""AI protocols, grounded tools, and optional provider adapters.

The mandatory offline profile must not import networking or cryptography packages.
Provider and encrypted-vault classes are loaded lazily only when explicitly used.
"""
from __future__ import annotations

from typing import Any

from .construction import AutonomousConstructionExecutor, ConstructionBrief, ConstructionRun, ConstructionStage, create_blank_document
from .context import ContextBudget, EvidenceItem, build_project_synopsis, choose_context, run_length_slice
from .orchestrator import AIOrchestrator, AIRunRecord, AIRunStatus
from .protocol import ModelEvent, ModelEventType, ModelRequest, ModelResponse, MultimodalProvider, ProviderCapabilities
from .tools import BuildToolExecutor

_OPTIONAL = {
    "EncryptedKeyVault": (".key_vault", "EncryptedKeyVault"),
    "AnthropicMessagesProvider": (".providers", "AnthropicMessagesProvider"),
    "OpenAICompatibleChatProvider": (".providers", "OpenAICompatibleChatProvider"),
    "OpenAIResponsesProvider": (".providers", "OpenAIResponsesProvider"),
}


def __getattr__(name: str) -> Any:
    target = _OPTIONAL.get(name)
    if target is None:
        raise AttributeError(name)
    import importlib

    module = importlib.import_module(target[0], __name__)
    value = getattr(module, target[1])
    globals()[name] = value
    return value


__all__ = [
    "AIOrchestrator", "AIRunRecord", "AIRunStatus", "AnthropicMessagesProvider",
    "AutonomousConstructionExecutor", "BuildToolExecutor", "ConstructionBrief", "ConstructionRun", "ConstructionStage",
    "ContextBudget", "EncryptedKeyVault", "EvidenceItem", "ModelEvent", "ModelEventType", "ModelRequest",
    "ModelResponse", "MultimodalProvider", "OpenAICompatibleChatProvider", "OpenAIResponsesProvider",
    "ProviderCapabilities", "build_project_synopsis", "choose_context", "create_blank_document", "run_length_slice",
]
