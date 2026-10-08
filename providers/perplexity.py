from __future__ import annotations
import hashlib
import json
import logging
import re
from pathlib import Path

import httpx

from providers.base import ProviderResponse

log = logging.getLogger(__name__)

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_URL_RE = re.compile(r"https?://[^\s\)\]\"'<>]+")


class PerplexityProvider:
    engine_name = "perplexity"

    def __init__(self, api_key: str, brand_domain: str = ""):
        self._api_key = api_key
        self._brand_domain = brand_domain

    def run(self, probe_text: str, probe_id: str) -> ProviderResponse:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Referer": f"https://{self._brand_domain}" if self._brand_domain else "",
        }
        payload = {
            "model": "perplexity/sonar",
            "messages": [{"role": "user", "content": probe_text}],
        }
        resp = httpx.post(_OPENROUTER_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        cited_urls = _extract_citations(data)
        response_text = data.get("choices", [{}])[0].get("message", {}).get("content", "")

        return ProviderResponse(
            engine="perplexity",
            probe_id=probe_id,
            response_text=response_text,
            cited_urls=cited_urls,
            raw=data,
        )


def _extract_citations(data: dict) -> list[str]:
    urls: list[str] = []
    for citation in data.get("citations", []):
        if isinstance(citation, str):
            urls.append(citation)
        elif isinstance(citation, dict):
            url = citation.get("url") or citation.get("link", "")
            if url:
                urls.append(url)
    if not urls:
        # Perplexity via OpenRouter: citations in message.annotations[].url_citation.url
        for choice in data.get("choices", []):
            for ann in choice.get("message", {}).get("annotations", []):
                # Standard OpenRouter Perplexity format
                url = (
                    ann.get("url_citation", {}).get("url")  # most common
                    or ann.get("url")
                    or ann.get("link", "")
                )
                if url:
                    urls.append(url)
        if not urls:
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            urls = _URL_RE.findall(content)
    return list(dict.fromkeys(urls))  # dedupe, preserve order
