from __future__ import annotations
from datetime import date
from typing import Literal, Optional
from pydantic import BaseModel

DomainType = Literal[
    "review_platform",
    "listicle",
    "competitor_owned",
    "reddit_forum",
    "vendor_neutral_media",
    "brand_owned",
    "other",
]


class QueryConfig(BaseModel):
    text: str
    intent: str
    vertical: str
    priority: Literal["high", "medium", "low"]
    category: Optional[str] = None


class SerpResult(BaseModel):
    run_date: date
    query: str
    position: int
    title: Optional[str] = None
    url: str
    domain: str
    snippet: Optional[str] = None
    ai_overview_box: Optional[str] = None
    raw_response_path: Optional[str] = None


class CitationRow(BaseModel):
    run_date: date
    url: str
    domain: str
    domain_type: DomainType
    weighted_score: float
    queries_appearing_in: int
    top_position: int


class SourceAnalysisRow(BaseModel):
    run_date: date
    url: str
    brand_mentioned: bool
    brand_context: Optional[str] = None
    competitors_mentioned: list[str] = []
    page_type: Optional[str] = None
    last_updated: Optional[str] = None
    pain_language: Optional[str] = None
    raw_response_path: Optional[str] = None


class AECitationRow(BaseModel):
    run_date: date
    query: str
    cited_url: str
    cited_domain: str
    position_in_response: int


class TrendRow(BaseModel):
    run_date: date
    keyword: str
    week: str
    interest: int
    rising_related: list[str] = []
