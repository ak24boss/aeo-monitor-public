from __future__ import annotations
import logging
import re

import httpx

from providers.base import ProviderResponse

log = logging.getLogger(__name__)

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_URL_RE = re.compile(r"https?://[^\s\)\]\"'<>]+")
_DEFAULT_MODEL = "openai/gpt-4o-mini"


class OpenAIProvider:
    engine_name = "openai"

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
            "model": _DEFAULT_MODEL,
            "messages": [{"role": "user", "content": probe_text}],
        }
        resp = httpx.post(_OPENROUTER_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        response_text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        cited_urls = list(dict.fromkeys(_URL_RE.findall(response_text)))

        return ProviderResponse(
            engine="openai",
            probe_id=probe_id,
            response_text=response_text,
            cited_urls=cited_urls,
            raw=data,
        )
