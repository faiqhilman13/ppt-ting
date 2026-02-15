from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TemplateOut(BaseModel):
    id: str
    name: str
    status: str
    created_at: datetime


class DocumentOut(BaseModel):
    id: str
    filename: str
    created_at: datetime


class GenerateDeckRequest(BaseModel):
    prompt: str = Field(min_length=3)
    template_id: str
    doc_ids: list[str] = Field(default_factory=list)
    slide_count: int = Field(default=20, ge=1, le=30)
    provider: str | None = None
    extra_instructions: str | None = None


class ReviseDeckRequest(BaseModel):
    prompt: str = Field(min_length=3)
    provider: str | None = None


class JobOut(BaseModel):
    id: str
    job_type: str
    status: str
    phase: str
    progress_pct: int
    error_code: str | None
    error_message: str | None
    deck_id: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class DeckOut(BaseModel):
    id: str
    template_id: str
    latest_version: int
    created_at: datetime
    updated_at: datetime


class DeckDetailOut(DeckOut):
    versions: list[dict[str, Any]]


class SearchRequest(BaseModel):
    query: str = Field(min_length=3)
    max_results: int = Field(default=5, ge=1, le=10)


class SearchResult(BaseModel):
    source_id: str
    title: str
    url: str
    snippet: str


class EditorSessionRequest(BaseModel):
    deck_id: str


class EditorSessionOut(BaseModel):
    config: dict[str, Any]


class EditorCallbackPayload(BaseModel):
    status: int
    url: str | None = None
    key: str | None = None
