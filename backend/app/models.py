from datetime import datetime
from enum import Enum as PythonEnum

from sqlalchemy import Enum as SqlEnum
from sqlalchemy import JSON, Integer, String, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.case_status import CASE_STATUSES
from app.database import Base


class HumanReviewStatus(str, PythonEnum):
    PENDING = "Pending"
    APPROVED_FOR_AI = "ApprovedForAI"
    REJECTED = "Rejected"
    SENSITIVE = "Sensitive"


class AssessmentCondition(str, PythonEnum):
    SINGLE_MEDIUM = "single_medium"
    THREE_VIEW = "three_view"


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    location: Mapped[str] = mapped_column(String(200), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    observations: Mapped[list["Observation"]] = relationship(
        "Observation", back_populates="site", cascade="all, delete-orphan"
    )
    experiment_assets: Mapped[list["ExperimentAsset"]] = relationship(
        "ExperimentAsset", back_populates="site"
    )


class Observation(Base):
    __tablename__ = "observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    site_id: Mapped[int] = mapped_column(Integer, ForeignKey("sites.id"), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=True)
    # Comma-separated damage tags, e.g. "crack,graffiti,vegetation"
    damage_tags: Mapped[str] = mapped_column(String(300), nullable=True, default="")
    # Severity 1 (minor) to 5 (severe)
    severity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    human_review_status: Mapped[HumanReviewStatus] = mapped_column(
        SqlEnum(
            HumanReviewStatus,
            values_callable=lambda enum: [status.value for status in enum],
            name="human_review_status",
            native_enum=False,
            validate_strings=True,
        ),
        nullable=False,
        default=HumanReviewStatus.PENDING,
    )
    reviewed_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    contributor_original: Mapped[dict | None] = mapped_column(
        JSON(none_as_null=True),
        nullable=True,
    )

    # Possible values: "not_run", "running", "complete", "mock", "failed"
    ai_analysis_status: Mapped[str] = mapped_column(String(20), nullable=True, default="not_run")
    ai_summary: Mapped[str] = mapped_column(Text, nullable=True)
    ai_confidence: Mapped[int] = mapped_column(Integer, nullable=True)
    ai_provider: Mapped[str] = mapped_column(String(50), nullable=True)
    ai_recommended_action: Mapped[str] = mapped_column(Text, nullable=True)
    # Raw JSON string from the provider (useful for debugging)
    ai_raw_response: Mapped[str] = mapped_column(Text, nullable=True)
    # Human decisions are separate so reviewing cannot rewrite the AI proposal.
    ai_review_decision: Mapped[dict | None] = mapped_column(
        JSON(none_as_null=True),
        nullable=True,
    )

    site: Mapped["Site"] = relationship("Site", back_populates="observations")
    images: Mapped[list["ObservationImage"]] = relationship(
        "ObservationImage",
        back_populates="observation",
        cascade="all, delete-orphan",
        order_by="ObservationImage.created_at",
    )
    analysis_records: Mapped[list["AIAnalysisRecord"]] = relationship(
        "AIAnalysisRecord",
        back_populates="observation",
        cascade="all, delete-orphan",
        order_by="AIAnalysisRecord.id",
    )
    risk_case: Mapped["RiskCase"] = relationship(
        "RiskCase", back_populates="observation", uselist=False, cascade="all, delete-orphan"
    )

    @property
    def tags_list(self) -> list[str]:
        """Return damage_tags as a Python list."""
        if not self.damage_tags:
            return []
        return [t.strip() for t in self.damage_tags.split(",") if t.strip()]

    @property
    def primary_image_url(self) -> str | None:
        """Return the first image as a browser URL."""
        if not self.images:
            return None
        image_url = self.images[0].image_url
        if image_url.startswith(("/", "http://", "https://")):
            return image_url
        return f"/uploads/{image_url}"

    @property
    def primary_image_label(self) -> str | None:
        """Return a short label for the first image."""
        image_url = self.primary_image_url
        if not image_url:
            return None
        return image_url.rsplit("/", 1)[-1]


class ObservationImage(Base):
    __tablename__ = "observation_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    observation_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("observations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    image_url: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    observation: Mapped["Observation"] = relationship(
        "Observation", back_populates="images"
    )


class AIAnalysisRecord(Base):
    __tablename__ = "ai_analysis_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    observation_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("observations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    provider: Mapped[str] = mapped_column(String(200), nullable=False)
    diagnostic: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    observation: Mapped["Observation"] = relationship(
        "Observation",
        back_populates="analysis_records",
    )


class RiskCase(Base):
    __tablename__ = "risk_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    observation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("observations.id"), unique=True, nullable=False
    )
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    risk_band: Mapped[str] = mapped_column(String(20), nullable=False, default="Low")
    # Allowed: Draft, Needs Review, Verified, Routed, Closed
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="Draft")
    routed_to: Mapped[str] = mapped_column(String(200), nullable=True)
    report_path: Mapped[str] = mapped_column(String(300), nullable=True)
    final_snapshot: Mapped[dict | None] = mapped_column(
        JSON(none_as_null=True),
        nullable=True,
    )
    finalized_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    observation: Mapped["Observation"] = relationship("Observation", back_populates="risk_case")
    events: Mapped[list["CaseEvent"]] = relationship(
        "CaseEvent",
        back_populates="case",
        cascade="all, delete-orphan",
        order_by="CaseEvent.created_at",
    )

    STATUSES = CASE_STATUSES


class CaseEvent(Base):
    __tablename__ = "case_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    case_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("risk_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_status: Mapped[str] = mapped_column(String(50), nullable=False)
    to_status: Mapped[str] = mapped_column(String(50), nullable=False)
    reviewer: Mapped[str] = mapped_column(String(200), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    case: Mapped["RiskCase"] = relationship("RiskCase", back_populates="events")


class ExperimentAsset(Base):
    __tablename__ = "experiment_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    external_asset_id: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    site_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    site_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("sites.id"), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    site: Mapped["Site | None"] = relationship("Site", back_populates="experiment_assets")
    sessions: Mapped[list["AssessmentSession"]] = relationship(
        "AssessmentSession",
        back_populates="asset",
        cascade="all, delete-orphan",
        order_by=lambda: (
            AssessmentSession.run_index,
            AssessmentSession.run_order,
        ),
    )


class AssessmentSession(Base):
    __tablename__ = "assessment_sessions"
    __table_args__ = (
        UniqueConstraint(
            "asset_id",
            "condition",
            "run_index",
            name="uq_assessment_asset_condition_run_index",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    asset_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("experiment_assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    condition: Mapped[AssessmentCondition] = mapped_column(
        SqlEnum(
            AssessmentCondition,
            values_callable=lambda enum: [condition.value for condition in enum],
            name="assessment_condition",
            native_enum=False,
            validate_strings=True,
        ),
        nullable=False,
    )
    run_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    image_ids: Mapped[list[int]] = mapped_column(JSON(none_as_null=True), nullable=False)
    analysis_result_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    analysis_result: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    prompt_template_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    rendered_request_sha256: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False)
    model_deployment: Mapped[str] = mapped_column(String(200), nullable=False)
    settings: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    run_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    run_order: Mapped[int] = mapped_column(Integer, nullable=False)
    operator: Mapped[str | None] = mapped_column(String(200), nullable=True)

    asset: Mapped["ExperimentAsset"] = relationship(
        "ExperimentAsset", back_populates="sessions"
    )
