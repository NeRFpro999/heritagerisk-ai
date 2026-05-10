from datetime import datetime
from sqlalchemy import Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


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


class Observation(Base):
    __tablename__ = "observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    site_id: Mapped[int] = mapped_column(Integer, ForeignKey("sites.id"), nullable=False)
    image_filename: Mapped[str] = mapped_column(String(300), nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=True)
    # Comma-separated damage tags, e.g. "crack,graffiti,vegetation"
    damage_tags: Mapped[str] = mapped_column(String(300), nullable=True, default="")
    # Severity 1 (minor) to 5 (severe)
    severity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # ── AI analysis fields (all nullable — populated by /analyze route) ────────
    # Possible values: "not_run", "running", "complete", "failed"
    ai_analysis_status: Mapped[str] = mapped_column(String(20), nullable=True, default="not_run")
    ai_summary: Mapped[str] = mapped_column(Text, nullable=True)
    ai_confidence: Mapped[int] = mapped_column(Integer, nullable=True)
    ai_provider: Mapped[str] = mapped_column(String(50), nullable=True)
    ai_recommended_action: Mapped[str] = mapped_column(Text, nullable=True)
    # Raw JSON string from the provider (useful for debugging)
    ai_raw_response: Mapped[str] = mapped_column(Text, nullable=True)

    site: Mapped["Site"] = relationship("Site", back_populates="observations")
    risk_case: Mapped["RiskCase"] = relationship(
        "RiskCase", back_populates="observation", uselist=False, cascade="all, delete-orphan"
    )

    @property
    def tags_list(self) -> list[str]:
        """Return damage_tags as a Python list."""
        if not self.damage_tags:
            return []
        return [t.strip() for t in self.damage_tags.split(",") if t.strip()]


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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    observation: Mapped["Observation"] = relationship("Observation", back_populates="risk_case")

    STATUSES = ["Draft", "Needs Review", "Verified", "Routed", "Closed"]
