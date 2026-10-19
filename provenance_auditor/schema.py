"""Structured types the agents produce and pass between each other."""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class owner_role(str, Enum):
    collector = "collector"
    dealer = "dealer"
    auction_house = "auction_house"
    museum = "museum"
    artist = "artist"
    heir = "heir"
    government = "government"
    unknown = "unknown"


class acquisition_method(str, Enum):
    purchase = "purchase"
    gift = "gift"
    inheritance = "inheritance"
    auction = "auction"
    commission = "commission"
    confiscation = "confiscation"
    forced_sale = "forced_sale"
    restitution = "restitution"
    unknown = "unknown"


class ownership_event(BaseModel):
    """One link in the chain of ownership."""

    owner_name: str = Field(description="Owner exactly as named in the source text")
    role: owner_role = owner_role.unknown
    location: Optional[str] = Field(
        default=None, description="City and/or country, as stated"
    )
    start_year: Optional[int] = None
    end_year: Optional[int] = None
    method: acquisition_method = acquisition_method.unknown
    is_vague: bool = Field(
        default=False,
        description="True for placeholders like 'Private collection' that name no one",
    )
    confidence: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Parser confidence in this event"
    )
    source_text: str = Field(
        default="", description="The span of the original record this came from"
    )


class gap_severity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class gap_kind(str, Enum):
    unaccounted_years = "unaccounted_years"
    vague_owner = "vague_owner"
    unexplained_location_change = "unexplained_location_change"
    nazi_era_window = "nazi_era_window"
    missing_acquisition_method = "missing_acquisition_method"
    chain_start_unclear = "chain_start_unclear"


class provenance_gap(BaseModel):
    """A specific defect found in the ownership chain."""

    kind: gap_kind
    severity: gap_severity
    description: str
    start_year: Optional[int] = None
    end_year: Optional[int] = None
    related_event_indexes: List[int] = Field(default_factory=list)


class crossref_hit(BaseModel):
    """One match for an owner name in an external or local source."""

    owner_name: str
    source: str = Field(description="wikidata, getty_ulan, red_flag_list, or lostart_cache")
    matched_label: str
    identifier: Optional[str] = None
    note: str = ""
    is_red_flag: bool = False


class risk_verdict(str, Enum):
    clear = "clear"
    review = "review"
    high_risk = "high_risk"


class artwork(BaseModel):
    """What the record says the object is, plus what Wikidata knows about it."""

    title: Optional[str] = None
    artist: Optional[str] = None
    year_created: Optional[int] = None
    medium: Optional[str] = None

    # Filled in by the Wikidata lookup, not by the parser.
    image_url: Optional[str] = None
    wikidata_id: Optional[str] = None
    sitelink_count: int = Field(
        default=0,
        description="How many Wikipedia language editions cover this work or "
        "artist. Used as a rough, public measure of prominence.",
    )
    matched_label: Optional[str] = None
    match_kind: Optional[str] = Field(
        default=None,
        description="'work' when the painting itself was found, 'artist' when "
        "only the artist was, so the picture shown is a portrait not the work.",
    )


class score_component(BaseModel):
    """One line of the score breakdown, so the number is never a black box."""

    label: str
    points: float = Field(description="Negative values are deductions")
    detail: str = ""


class provenance_score(BaseModel):
    """A 0-100 confidence score. 100 means nothing was found to doubt."""

    value: int = Field(default=100, ge=0, le=100)
    band: str = "unknown"
    components: List[score_component] = Field(default_factory=list)
    method_note: str = ""


class token_usage(BaseModel):
    """Measured usage for the tokenomics section of the report."""

    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    call_count: int = 0

    def add(self, other: "token_usage") -> "token_usage":
        return token_usage(
            input_tokens=self.input_tokens + other.input_tokens,
            cached_input_tokens=self.cached_input_tokens + other.cached_input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cost_usd=round(self.cost_usd + other.cost_usd, 8),
            call_count=self.call_count + other.call_count,
        )


class audit_result(BaseModel):
    """Everything one run of the auditor produces."""

    work: artwork = Field(default_factory=artwork)
    score: provenance_score = Field(default_factory=provenance_score)
    events: List[ownership_event] = Field(default_factory=list)
    gaps: List[provenance_gap] = Field(default_factory=list)
    crossref_hits: List[crossref_hit] = Field(default_factory=list)
    verdict: risk_verdict = risk_verdict.review
    reasoning: str = ""
    usage: token_usage = Field(default_factory=token_usage)
    warnings: List[str] = Field(default_factory=list)
