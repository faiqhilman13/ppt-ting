from datetime import datetime
from typing import Literal
from typing import Any

from pydantic import BaseModel, Field, model_validator


class TemplateOut(BaseModel):
    id: str
    name: str
    status: str
    created_at: datetime


class TemplateDeleteOut(BaseModel):
    template_id: str
    deleted: bool
    archived: bool = False
    deleted_files: list[str] = Field(default_factory=list)


class TemplateCleanupRequest(BaseModel):
    dry_run: bool = False
    include_scratch: bool = True
    include_test: bool = True
    only_unreferenced: bool = True


class TemplateCleanupOut(BaseModel):
    dry_run: bool
    matched_ids: list[str] = Field(default_factory=list)
    deleted_ids: list[str] = Field(default_factory=list)
    deleted_file_count: int = 0
    skipped: list[dict[str, str]] = Field(default_factory=list)


class DocumentOut(BaseModel):
    id: str
    filename: str
    created_at: datetime


class GenerateDeckRequest(BaseModel):
    prompt: str = Field(min_length=3)
    creation_mode: Literal["template", "scratch"] = "template"
    template_id: str | None = None
    doc_ids: list[str] = Field(default_factory=list)
    slide_count: int = Field(default=20, ge=1, le=30)
    provider: str | None = None
    scratch_theme: str | None = None
    extra_instructions: str | None = None
    outline: dict[str, Any] | None = None
    agent_mode: Literal["off", "bounded"] = "bounded"
    quality_profile: Literal["fast", "balanced", "high_fidelity"] = "balanced"
    max_correction_passes: int | None = Field(default=None, ge=0, le=2)

    @model_validator(mode="after")
    def _validate_template_requirements(self):
        if self.creation_mode == "template" and not self.template_id:
            raise ValueError("template_id is required when creation_mode='template'")
        return self


class ReviseDeckRequest(BaseModel):
    prompt: str = Field(min_length=3)
    provider: str | None = None
    slide_indices: list[int] | None = None
    agent_mode: Literal["off", "bounded"] = "bounded"
    quality_profile: Literal["fast", "balanced", "high_fidelity"] = "balanced"
    max_correction_passes: int | None = Field(default=None, ge=0, le=2)


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


class JsonRenderDemoQueryRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    max_points: int = Field(default=12, ge=6, le=24)
    provider: str | None = None
    agentic: bool = True


class JsonRenderDemoQueryOut(BaseModel):
    query: str
    intent: str
    narrative: str
    data_sources: list[str] = Field(default_factory=list)
    state: dict[str, Any] = Field(default_factory=dict)
    spec: dict[str, Any] = Field(default_factory=dict)
    suggested_followups: list[str] = Field(default_factory=list)


class EditorSessionRequest(BaseModel):
    deck_id: str


class EditorSessionOut(BaseModel):
    config: dict[str, Any]


class EditorCallbackPayload(BaseModel):
    status: int
    url: str | None = None
    key: str | None = None


class OutlineDeckRequest(BaseModel):
    prompt: str = Field(min_length=3)
    creation_mode: Literal["template", "scratch"] = "template"
    template_id: str | None = None
    doc_ids: list[str] = Field(default_factory=list)
    slide_count: int = Field(default=20, ge=1, le=30)
    provider: str | None = None
    scratch_theme: str | None = None
    extra_instructions: str | None = None

    @model_validator(mode="after")
    def _validate_template_requirements(self):
        if self.creation_mode == "template" and not self.template_id:
            raise ValueError("template_id is required when creation_mode='template'")
        return self


class OutlineResultOut(BaseModel):
    job_id: str
    status: str
    prompt: str | None = None
    thesis: str | None = None
    slides: list[dict[str, Any]] = Field(default_factory=list)


class JobEventOut(BaseModel):
    id: int
    job_id: str
    ts: datetime
    stage: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    severity: str = "info"


class QualityReportOut(BaseModel):
    deck_id: str
    version: int
    score: float | None = None
    passes_used: int = 0
    issues: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
