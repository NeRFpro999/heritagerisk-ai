"""Build immutable contributor and RiskCase provenance records."""

import json
from copy import deepcopy
from datetime import datetime, timezone

from app.risk import ALL_TAGS, build_risk_snapshot


def utc_iso(value: datetime | None = None) -> str:
    timestamp = value or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc).isoformat()


def build_contributor_original(
    notes: str | None,
    tags: list[str],
    severity: int,
    submitted_at: datetime,
) -> dict:
    """Return the contributor payload stored once with a new Observation."""
    return {
        "notes": notes,
        "tags": list(tags),
        "severity": severity,
        "submitted_at": utc_iso(submitted_at),
    }


def contributor_original(value) -> dict | None:
    """Return a valid original payload, or None for pre-provenance rows."""
    if not isinstance(value, dict):
        return None
    required = {"notes", "tags", "severity", "submitted_at"}
    if not required.issubset(value):
        return None
    if value["notes"] is not None and not isinstance(value["notes"], str):
        return None
    if not isinstance(value["tags"], list) or not all(
        isinstance(tag, str) for tag in value["tags"]
    ):
        return None
    if not isinstance(value["severity"], int) or isinstance(
        value["severity"], bool
    ):
        return None
    if not isinstance(value["submitted_at"], str):
        return None
    return value


def _raw_ai_data(raw_response: str | None) -> dict:
    if not raw_response:
        return {}
    try:
        data = json.loads(raw_response)
    except (json.JSONDecodeError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _image_urls(observation) -> list[str]:
    urls = []
    for image in getattr(observation, "images", None) or []:
        image_url = getattr(image, "image_url", None)
        if image_url:
            if image_url.startswith(("/", "http://", "https://")):
                urls.append(image_url)
            else:
                urls.append(f"/uploads/{image_url}")
    return urls


def _reviewer_identity(value) -> str | None:
    if not isinstance(value, str):
        return None
    identity = value.strip()
    return identity or None


def analysis_attempt_history(observation) -> list[dict]:
    """Return persisted analysis records in append order for display/snapshotting."""
    records = list(getattr(observation, "analysis_records", None) or [])
    indexed_records = list(enumerate(records))
    indexed_records.sort(
        key=lambda item: (
            getattr(item[1], "id", None) is None,
            getattr(item[1], "id", None) or item[0],
        )
    )
    history = []
    for _, record in indexed_records:
        created_at = getattr(record, "created_at", None)
        history.append(
            {
                "record_id": getattr(record, "id", None),
                "status": getattr(record, "status", None),
                "provider": getattr(record, "provider", None),
                "diagnostic": getattr(record, "diagnostic", None),
                "created_at": utc_iso(created_at) if created_at else None,
            }
        )
    return history


def build_case_snapshot(
    observation,
    final_tags: list[str],
    final_severity: int,
    final_summary: str,
    final_recommended_action: str,
    reviewer_decision: dict,
    finalized_by: str | None,
) -> dict:
    """Capture all observation-derived evidence used by a RiskCase report."""
    snapshot = build_risk_snapshot(final_tags, final_severity)
    raw_data = _raw_ai_data(getattr(observation, "ai_raw_response", None))
    is_v2 = raw_data.get("schema_version") == "2"
    v2_indicators = raw_data.get("indicators", []) if is_v2 else []
    if not isinstance(v2_indicators, list):
        v2_indicators = []
    ai_tags = (
        [
            indicator.get("indicator_type")
            for indicator in v2_indicators
            if isinstance(indicator, dict)
        ]
        if is_v2
        else raw_data.get("damage_tags", [])
    )
    if not isinstance(ai_tags, list):
        ai_tags = []
    ai_tags = [tag for tag in ai_tags if tag in ALL_TAGS]
    if is_v2:
        severities = [
            indicator.get("severity_contribution")
            for indicator in v2_indicators
            if isinstance(indicator, dict)
            and isinstance(indicator.get("severity_contribution"), int)
        ]
        ai_severity = max(severities) if severities else 1
    else:
        try:
            ai_severity = max(1, min(5, int(raw_data.get("severity"))))
        except (TypeError, ValueError):
            ai_severity = None

    human_status = getattr(observation, "human_review_status", None)
    human_status = getattr(human_status, "value", human_status)
    submitted = contributor_original(
        getattr(observation, "contributor_original", None)
    )
    site = getattr(observation, "site", None)
    reviewed_at = reviewer_decision.get("reviewed_at") or utc_iso()

    snapshot.update(
        {
            "version": 1,
            "snapshot_source": "case_creation",
            "captured_at": reviewed_at,
            "reviewed_by": _reviewer_identity(
                getattr(observation, "reviewed_by", None)
            ),
            "finalized_by": _reviewer_identity(finalized_by),
            "observation_id": observation.id,
            "observation_created_at": utc_iso(observation.created_at),
            "image_urls": _image_urls(observation),
            "analysis_attempts_available": True,
            "analysis_attempts": analysis_attempt_history(observation),
            "site": {
                "id": getattr(site, "id", None),
                "name": getattr(site, "name", None),
                "location": getattr(site, "location", None),
                "description": getattr(site, "description", None),
            },
            "contributor_original": deepcopy(submitted),
            "current_reviewed": {
                "notes": observation.notes,
                "tags": list(final_tags),
                "severity": final_severity,
                "human_review_status": human_status,
            },
            "ai_proposal": {
                "schema_version": raw_data.get("schema_version"),
                "evidence_sufficiency": raw_data.get("evidence_sufficiency"),
                "indicators": v2_indicators if is_v2 else [],
                "insufficient_reason": raw_data.get("insufficient_reason"),
                "analysis_status": observation.ai_analysis_status,
                "summary": observation.ai_summary,
                "overall_summary": raw_data.get("overall_summary"),
                "damage_tags": ai_tags,
                "severity": ai_severity,
                "confidence": observation.ai_confidence,
                "provider": observation.ai_provider,
                "recommended_action": observation.ai_recommended_action,
                "uncertainty": raw_data.get("uncertainty"),
                "raw_response": observation.ai_raw_response,
            },
            "reviewer_decision": deepcopy(reviewer_decision),
            "final_summary": final_summary,
            "final_recommended_action": final_recommended_action,
        }
    )
    return snapshot


def case_snapshot(case) -> dict:
    """Return a stored snapshot without consulting the linked Observation."""
    fallback = {
        "version": 0,
        "snapshot_source": "legacy_unavailable",
        "captured_at": None,
        "reviewed_by": None,
        "finalized_by": None,
        "observation_id": getattr(case, "observation_id", None),
        "observation_created_at": None,
        "image_urls": [],
        "analysis_attempts_available": False,
        "analysis_attempts": [],
        "site": {},
        "contributor_original": None,
        "current_reviewed": {},
        "ai_proposal": {},
        "reviewer_decision": {},
        "final_tags": [],
        "final_severity": None,
        "tag_weights": [],
        "multiplier": None,
        "tag_sum": None,
        "raw_score": None,
        "raw_equation": "Unavailable for a case created before provenance snapshots.",
        "capped": False,
        "capped_score": getattr(case, "risk_score", 0),
        "band": getattr(case, "risk_band", "Unknown"),
        "thresholds": {},
        "final_summary": None,
        "final_recommended_action": None,
    }
    stored = getattr(case, "final_snapshot", None)
    if not isinstance(stored, dict):
        return fallback

    normalized = deepcopy(fallback)
    normalized.update(deepcopy(stored))

    for key in ("reviewed_by", "finalized_by"):
        normalized[key] = _reviewer_identity(normalized.get(key))

    normalized["image_urls"] = [
        url
        for url in normalized.get("image_urls", [])
        if isinstance(url, str)
    ] if isinstance(normalized.get("image_urls"), list) else []
    normalized["final_tags"] = [
        tag
        for tag in normalized.get("final_tags", [])
        if isinstance(tag, str)
    ] if isinstance(normalized.get("final_tags"), list) else []

    attempts = []
    stored_attempts = normalized.get("analysis_attempts")
    if isinstance(stored_attempts, list):
        for item in stored_attempts:
            if not isinstance(item, dict):
                continue
            status = item.get("status")
            provider = item.get("provider")
            if not isinstance(status, str) or not isinstance(provider, str):
                continue
            diagnostic = item.get("diagnostic")
            created_at = item.get("created_at")
            record_id = item.get("record_id")
            attempts.append(
                {
                    "record_id": (
                        record_id
                        if isinstance(record_id, int)
                        and not isinstance(record_id, bool)
                        else None
                    ),
                    "status": status,
                    "provider": provider,
                    "diagnostic": (
                        diagnostic if isinstance(diagnostic, str) else None
                    ),
                    "created_at": (
                        created_at if isinstance(created_at, str) else None
                    ),
                }
            )
    normalized["analysis_attempts"] = attempts
    normalized["analysis_attempts_available"] = (
        normalized.get("analysis_attempts_available") is True
    )

    tag_weights = []
    stored_weights = normalized.get("tag_weights")
    if isinstance(stored_weights, list):
        for item in stored_weights:
            if not isinstance(item, dict):
                continue
            tag = item.get("tag")
            label = item.get("label")
            weight = item.get("weight")
            if (
                isinstance(tag, str)
                and isinstance(label, str)
                and isinstance(weight, (int, float))
                and not isinstance(weight, bool)
            ):
                tag_weights.append(
                    {"tag": tag, "label": label, "weight": weight}
                )
    normalized["tag_weights"] = tag_weights

    site = normalized.get("site")
    normalized["site"] = site if isinstance(site, dict) else {}

    thresholds = normalized.get("thresholds")
    if not isinstance(thresholds, dict) or not all(
        isinstance(thresholds.get(band), str)
        for band in ("Low", "Medium", "High")
    ):
        normalized["thresholds"] = {}

    original = contributor_original(normalized.get("contributor_original"))
    normalized["contributor_original"] = deepcopy(original)

    for key in ("current_reviewed", "ai_proposal", "reviewer_decision"):
        if not isinstance(normalized.get(key), dict):
            normalized[key] = {}

    current_tags = normalized["current_reviewed"].get("tags")
    normalized["current_reviewed"]["tags"] = [
        tag for tag in current_tags if isinstance(tag, str)
    ] if isinstance(current_tags, list) else []
    ai_tags = normalized["ai_proposal"].get("damage_tags")
    normalized["ai_proposal"]["damage_tags"] = [
        tag for tag in ai_tags if isinstance(tag, str)
    ] if isinstance(ai_tags, list) else []
    ai_indicators = normalized["ai_proposal"].get("indicators")
    normalized["ai_proposal"]["indicators"] = [
        indicator
        for indicator in ai_indicators
        if isinstance(indicator, dict)
    ] if isinstance(ai_indicators, list) else []

    for key in ("multiplier", "tag_sum", "raw_score"):
        value = normalized.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            normalized[key] = None
    score = normalized.get("capped_score")
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        normalized["capped_score"] = fallback["capped_score"]
    if not isinstance(normalized.get("band"), str):
        normalized["band"] = fallback["band"]
    if not isinstance(normalized.get("raw_equation"), str):
        normalized["raw_equation"] = fallback["raw_equation"]
    normalized["capped"] = normalized.get("capped") is True
    return normalized
