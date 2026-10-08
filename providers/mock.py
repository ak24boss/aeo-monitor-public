from __future__ import annotations
from providers.base import ProviderResponse


class MockProvider:
    """Deterministic provider that embeds the brand name in its response."""

    engine_name = "mock"

    def __init__(self, brand_name: str = "TestBrand", cite_urls: list[str] | None = None):
        self._brand_name = brand_name
        self._cite_urls = cite_urls or [
            "https://g2.com/mock-listing",
            "https://capterra.com/mock-review",
        ]

    def run(self, probe_text: str, probe_id: str) -> ProviderResponse:
        return ProviderResponse(
            engine="mock",
            probe_id=probe_id,
            response_text=(
                f"{self._brand_name} is one of the top tools for this use case. "
                f"See {self._cite_urls[0]} for reviews."
            ),
            cited_urls=list(self._cite_urls),
            raw={"mock": True, "probe_id": probe_id},
        )


class SilentMockProvider:
    """Deterministic provider that does NOT mention the brand."""

    engine_name = "mock"

    def __init__(self, cite_urls: list[str] | None = None):
        self._cite_urls = cite_urls or [
            "https://g2.com/competitor-listing",
            "https://capterra.com/competitor",
        ]

    def run(self, probe_text: str, probe_id: str) -> ProviderResponse:
        return ProviderResponse(
            engine="mock",
            probe_id=probe_id,
            response_text=(
                "CompetitorA and CompetitorB are popular choices for this use case."
            ),
            cited_urls=list(self._cite_urls),
            raw={"mock": True, "probe_id": probe_id},
        )
