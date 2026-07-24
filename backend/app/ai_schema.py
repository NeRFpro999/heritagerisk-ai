"""Versioned AI analysis response validation."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.risk import ALL_TAGS


EvidenceSufficiency = Literal["sufficient", "partial", "insufficient"]


class Indicator(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    indicator_type: str
    evidence_location: str = Field(min_length=1, max_length=300)
    image_refs: list[int]
    confidence: float = Field(ge=0, le=1)
    supporting_evidence: str = Field(min_length=1, max_length=500)
    severity_contribution: int = Field(ge=1, le=5)

    @field_validator("indicator_type")
    @classmethod
    def known_indicator_type(cls, value: str) -> str:
        if value not in ALL_TAGS:
            raise ValueError(f"Unknown indicator_type: {value}")
        return value

    @field_validator("image_refs")
    @classmethod
    def non_empty_image_refs(cls, value: list[int]) -> list[int]:
        if not value:
            raise ValueError("image_refs must contain at least one image id")
        return value


class AnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["2"]
    provider: str
    overall_summary: str = Field(min_length=1, max_length=1200)
    evidence_sufficiency: EvidenceSufficiency
    indicators: list[Indicator]
    insufficient_reason: str | None = Field(default=None, max_length=800)

    @field_validator("insufficient_reason")
    @classmethod
    def reason_required_when_insufficient(cls, value: str | None, info) -> str | None:
        evidence_sufficiency = info.data.get("evidence_sufficiency")
        if evidence_sufficiency == "insufficient" and not (value or "").strip():
            raise ValueError("insufficient_reason is required when evidence is insufficient")
        return value

    @field_validator("indicators")
    @classmethod
    def no_indicators_when_insufficient(cls, value: list[Indicator], info) -> list[Indicator]:
        evidence_sufficiency = info.data.get("evidence_sufficiency")
        if evidence_sufficiency == "insufficient" and value:
            raise ValueError("insufficient evidence must not include indicators")
        return value


def validate_analysis_result(
    payload: dict,
    *,
    allowed_image_ids: set[int] | None = None,
) -> AnalysisResult:
    """Validate schema v2 and reject indicators referencing unrelated images."""
    result = AnalysisResult.model_validate(payload)
    if allowed_image_ids is not None:
        invalid_refs = sorted(
            {
                image_ref
                for indicator in result.indicators
                for image_ref in indicator.image_refs
                if image_ref not in allowed_image_ids
            }
        )
        if invalid_refs:
            raise ValueError(
                "image_refs do not belong to this observation: "
                + ", ".join(str(ref) for ref in invalid_refs)
            )
    return result


def validation_error_text(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "; ".join(error["msg"] for error in exc.errors())
    return str(exc)
