from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Template(Base):
    __tablename__ = "templates"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    manifest_path: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class DocumentAsset(Base):
    __tablename__ = "document_assets"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    extracted_text_path: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class Deck(Base):
    __tablename__ = "decks"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    template_id: Mapped[str] = mapped_column(ForeignKey("templates.id"), nullable=False)
    latest_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    versions: Mapped[list["DeckVersion"]] = relationship(back_populates="deck", cascade="all, delete-orphan")


class DeckVersion(Base):
    __tablename__ = "deck_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    deck_id: Mapped[str] = mapped_column(ForeignKey("decks.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    content_json_path: Mapped[str] = mapped_column(String, nullable=False)
    pptx_path: Mapped[str] = mapped_column(String, nullable=False)
    source_manifest_path: Mapped[str] = mapped_column(String, nullable=False)
    is_manual_edit: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    deck: Mapped[Deck] = relationship(back_populates="versions")


class DeckJob(Base):
    __tablename__ = "deck_jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    job_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="queued", nullable=False)
    phase: Mapped[str] = mapped_column(String, default="queued", nullable=False)
    progress_pct: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    deck_id: Mapped[str | None] = mapped_column(ForeignKey("decks.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DeckOutline(Base):
    __tablename__ = "deck_outlines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("deck_jobs.id"), nullable=False, unique=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    outline_json_path: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class JobEvent(Base):
    __tablename__ = "job_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("deck_jobs.id"), nullable=False, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    severity: Mapped[str] = mapped_column(String, nullable=False, default="info")


class ToolRun(Base):
    __tablename__ = "tool_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("deck_jobs.id"), nullable=False, index=True)
    tool_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_hash: Mapped[str] = mapped_column(String, nullable=False, default="")
    output_hash: Mapped[str] = mapped_column(String, nullable=False, default="")
    artifact_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class QualityReport(Base):
    __tablename__ = "quality_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    deck_id: Mapped[str] = mapped_column(ForeignKey("decks.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    issues_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    passes_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class DemoAsset(Base):
    __tablename__ = "demo_assets"

    symbol: Mapped[str] = mapped_column(String, primary_key=True)
    company: Mapped[str] = mapped_column(String, nullable=False)
    sector: Mapped[str] = mapped_column(String, nullable=False)
    country: Mapped[str] = mapped_column(String, nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class DemoPricePoint(Base):
    __tablename__ = "demo_price_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(ForeignKey("demo_assets.symbol"), nullable=False, index=True)
    price_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume_mn: Mapped[float] = mapped_column(Float, nullable=False)


class DemoFundamental(Base):
    __tablename__ = "demo_fundamentals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(ForeignKey("demo_assets.symbol"), nullable=False, index=True)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    revenue_musd: Mapped[float] = mapped_column(Float, nullable=False)
    ebit_margin_pct: Mapped[float] = mapped_column(Float, nullable=False)
    free_cash_flow_musd: Mapped[float] = mapped_column(Float, nullable=False)
