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


class ProbeConfig(BaseModel):
    id: str
    text: str
    intent: str
    priority: Literal["high", "medium", "low"]
    seed_topic: str = "general"
    perturbation_class: str = "seed"   # seed | A | B | C
    perturbation_type: str = "seed"    # seed | typo | simplify | best | recommend | spanish |
                                       # persona-regulated | persona-casual | pain | competitor |
                                       # use-case | requirements | price-budget | price-premium | how-to


class AEProbeRow(BaseModel):
    run_date: date
    engine: str
    probe_id: str
    probe_text: str
    brand_mentioned: bool
    brand_context: Optional[str] = None
    competitors_mentioned: list[str] = []
    cited_urls: list[str] = []
    cited_domains: list[str] = []
    sponsored_domains: list[str] = []  # domains appearing in paid ad slots
    raw_response: Optional[str] = None
    seed_topic: str = "general"
    perturbation_class: str = "seed"
    perturbation_type: str = "seed"


class CrossReferenceRow(BaseModel):
    run_date: date
    url: str
    domain: str
    serp_weighted_score: float
    serp_queries_appearing_in: int
    engines_citing_url: list[str] = []
    engine_citation_count: int = 0
    brand_mentioned_on_page: Optional[bool] = None
    action_priority: Literal["critical", "high", "medium", "low"] = "medium"
