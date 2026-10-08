from __future__ import annotations
import logging

import httpx

from providers.base import ProviderResponse

log = logging.getLogger(__name__)

_VALUESERP_URL = "https://api.valueserp.com/search"


class GoogleAIOverviewProvider:
    """Query ValueSERP for Google AI Overviews + sponsored ads.

    AI Overviews don't fire on every query — when absent response_text
    is empty and cited_urls is []. That is not an error.

    Ads data is included in raw['ads'] for sponsored mention analysis.
    """

    engine_name = "google"

    def __init__(self, api_key: str, brand_domain: str = ""):
        self._api_key = api_key
        self._brand_domain = brand_domain

    def run(self, probe_text: str, probe_id: str) -> ProviderResponse:
        params = {
            "api_key": self._api_key,
            "q": probe_text,
            "gl": "us",
            "hl": "en",
            "output": "json",
            "include_ai_overview": "true",
        }
        # AI Overview rendering takes longer than a standard SERP request.
        # Retry once on timeout before giving up.
        for attempt in range(2):
            try:
                resp = httpx.get(_VALUESERP_URL, params=params, timeout=90)
                break
            except httpx.TimeoutException:
                if attempt == 0:
                    log.warning("Phase 4A: google / %s — timeout, retrying", probe_id)
                else:
                    raise
        resp.raise_for_status()
        data = resp.json()

        ai_overview = data.get("ai_overview") or {}
        response_text = _extract_overview_text(ai_overview)
        cited_urls = [
            s["source_url"]
            for s in ai_overview.get("ai_overview_sources") or []
            if isinstance(s, dict) and s.get("source_url")
        ]

        if not response_text:
            log.info("Phase 4A: google / %s — no AI Overview fired", probe_id)
        else:
            log.info(
                "Phase 4A: google / %s — AI Overview fired, %d sources",
                probe_id, len(cited_urls),
            )

        # Include ads in raw so sponsored mention analysis can use them downstream.
        enriched = dict(data)
        enriched["_ads_domains"] = [
            a.get("displayed_link", "").lstrip("www.")
            for a in data.get("ads") or []
            if a.get("displayed_link")
        ]

        return ProviderResponse(
            engine="google",
            probe_id=probe_id,
            response_text=response_text,
            cited_urls=cited_urls,
            raw=enriched,
        )


def _extract_overview_text(ai_overview: dict) -> str:
    parts: list[str] = []
    for block in ai_overview.get("ai_overview_contents") or []:
        btype = block.get("type")
        if btype == "paragraph":
            parts.append(block.get("text", ""))
        elif btype == "header":
            parts.append(block.get("text", ""))
        elif btype == "list":
            for item in block.get("list") or []:
                parts.append(item.get("text", ""))
    return " ".join(p.strip() for p in parts if p.strip())
