from __future__ import annotations
import re

_URL_RE = re.compile(r"https?://[^\s\)\]\"'<>]+")


def extract_citations(data: dict) -> list[str]:
    """Extract cited URLs from an OpenRouter chat completion response.

    Works for Perplexity sonar, OpenAI search preview, and any other
    OpenRouter model that embeds sources in data['citations'] or
    choices[0].message.annotations[].url_citation.url.
    Falls back to URL regex over the response text.
    """
    urls: list[str] = []

    for citation in data.get("citations", []):
        if isinstance(citation, str):
            urls.append(citation)
        elif isinstance(citation, dict):
            url = citation.get("url") or citation.get("link", "")
            if url:
                urls.append(url)

    if not urls:
        for choice in data.get("choices", []):
            for ann in choice.get("message", {}).get("annotations", []):
                url = (
                    ann.get("url_citation", {}).get("url")
                    or ann.get("url")
                    or ann.get("link", "")
                )
                if url:
                    urls.append(url)

    if not urls:
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        urls = _URL_RE.findall(content)

    return list(dict.fromkeys(urls))
