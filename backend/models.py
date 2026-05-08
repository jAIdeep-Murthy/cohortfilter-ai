"""Pydantic models for CohortFilter AI."""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from enum import Enum


class Dealbreaker(BaseModel):
    rule: str  # e.g. "No solo founders"
    field_hint: Optional[str] = None  # CSV column to check, if known


class RubricDimension(BaseModel):
    name: str  # e.g. "Traction"
    weight: float  # 0.0–1.0, all must sum to 1.0
    description: str = ""  # What the scorer should look for


class RubricConfig(BaseModel):
    program_focus: str = ""
    dealbreakers: List[Dealbreaker] = []
    dimensions: List[RubricDimension] = []


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage] = []


class DimensionScore(BaseModel):
    score: int = Field(ge=0, le=1000)
    reason: str = ""


class ApplicationResult(BaseModel):
    application_id: str
    startup_name: str
    founder_name: str
    total_score: int = Field(ge=0, le=1000)
    dimension_scores: Dict[str, DimensionScore] = {}
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str = ""
    risk_flags: List[str] = []
    duplicate_hint: Optional[str] = None
    website_status: str = "unknown"  # live | dead | unknown
    dealbreaker_hit: bool = False
    dealbreaker_reason: Optional[str] = None
    rank: Optional[int] = None
    raw_data: Dict = {}  # Original CSV row


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ScoringJob(BaseModel):
    job_id: str
    status: JobStatus = JobStatus.PENDING
    progress: int = 0
    total: int = 0
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    results: Optional[List[ApplicationResult]] = None
    duplicates: List[Dict] = []
    error: Optional[str] = None
