from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class ProviderResponse:
    engine: str
    probe_id: str
    response_text: str
    cited_urls: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


@runtime_checkable
class AIEngineProvider(Protocol):
    engine_name: str

    def run(self, probe_text: str, probe_id: str) -> ProviderResponse:
        ...
