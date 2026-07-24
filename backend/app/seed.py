"""
Demo seed data — three sites covering High/Medium/Low risk and all workflow stages.
Idempotent: skips records that already exist. Safe to run multiple times.

  Old Stone Church     — crack + erosion + water_staining, sev 4 → score 84 → High,   Needs Review
  Historic Iron Bridge — corrosion + vegetation_growth + water_staining, sev 3 → score 51 → Medium, Verified
  Memorial Statue      — graffiti + other, sev 2                 → score 10 → Low,    Routed
"""

import json
from datetime import datetime, timedelta, timezone

from app.database import (
    Base,
    SessionLocal,
    apply_sqlite_startup_migrations,
    engine,
)
from app.models import HumanReviewStatus, Site, Observation, RiskCase
from app.provenance import build_case_snapshot, build_contributor_original
from app.reports import generate_report

Base.metadata.create_all(bind=engine)
apply_sqlite_startup_migrations(engine)

SEED_SITES = [
    {
        "name": "Old Stone Church",
        "location": "Kilkenny, Ireland",
        "description": (
            "Medieval limestone church, approximate construction 12th century. "
            "Category A protected structure. Listed with the National Inventory of "
            "Architectural Heritage. Managed by the local diocese."
        ),
    },
    {
        "name": "Historic Iron Bridge",
        "location": "Brunel Quarter, Bristol, UK",
        "description": (
            "Victorian wrought-iron pedestrian bridge spanning the River Avon. "
            "Grade II listed. Last full professional inspection 2019. "
            "High public footfall; adjacent to residential development."
        ),
    },
    {
        "name": "Memorial Statue",
        "location": "Victoria Square, Birmingham, UK",
        "description": (
            "Bronze memorial sculpture erected 1925. Honours local casualties of WWI. "
            "Grade II* listed. Subject of an ongoing community monitoring programme."
        ),
    },
]

SEED_OBSERVATIONS = [
    # ── Old Stone Church — crack + erosion + water_staining, sev 4 → score 84 → High, Needs Review ──
    {
        "site_name": "Old Stone Church",
        "notes": (
            "Vertical crack visible on the south-east wall face, approximately 80 cm long. "
            "Water staining is visible below the crack and across the lower stone courses. "
            "Several nearby stones show surface erosion and small areas of missing mortar. "
            "The notes suggest this area should be reviewed by a qualified person before any "
            "conservation action is considered."
        ),
        "damage_tags": "crack,erosion,water_staining",
        "severity": 4,
        "ai_analysis_status": "mock",
        "ai_summary": (
            "Visible indicators detected: crack, erosion, water_staining. "
            "The combination of cracking, staining, and surface erosion makes this a clear "
            "high-priority triage example for human review. "
            "This is a mock/fallback result — connect Azure OpenAI Vision for real image analysis. "
            "AI suggests visible risk indicators only. Humans verify. The system tracks."
        ),
        "ai_confidence": 35,
        "ai_provider": "mock",
        "ai_recommended_action": (
            "Visible indicators suggest this should be reviewed by a qualified person. "
            "Contributors should record evidence only and should not attempt repair."
        ),
        "case": {
            "status": "Needs Review",
            "routed_to": None,
        },
    },
    # ── Historic Iron Bridge — corrosion + vegetation_growth + water_staining, sev 3 → score 51 → Medium, Verified ──
    {
        "site_name": "Historic Iron Bridge",
        "notes": (
            "Corrosion is visible on the north railing and around several exposed rivets. "
            "Paint has flaked in small patches, leaving bare metal visible. Water staining is "
            "visible below part of the deck edge. Vegetation growth is present at the base of "
            "both bridge abutments and appears close to mortar joints. "
            "This is useful as a medium-risk demo because the visible indicators are notable "
            "but not presented as an emergency diagnosis."
        ),
        "damage_tags": "corrosion,vegetation_growth,water_staining",
        "severity": 3,
        "ai_analysis_status": "mock",
        "ai_summary": (
            "Visible indicators detected: corrosion, vegetation_growth, water_staining. "
            "Corrosion, staining, and vegetation growth are visible enough to justify review "
            "and tracking, but this mock result does not make a structural judgement. "
            "This is a mock/fallback result — connect Azure OpenAI Vision for real image analysis. "
            "AI suggests visible risk indicators only. Humans verify. The system tracks."
        ),
        "ai_confidence": 35,
        "ai_provider": "mock",
        "ai_recommended_action": (
            "Visible indicators suggest this should be monitored and reviewed by the responsible "
            "heritage or maintenance team if appropriate."
        ),
        "case": {
            "status": "Verified",
            "routed_to": "Bristol City Council — Heritage Structures Team",
        },
    },
    # ── Memorial Statue — graffiti + other, sev 2 → score 10 → Low, Routed ──────────────
    {
        "site_name": "Memorial Statue",
        "notes": (
            "Graffiti is visible on the rear face of the stone plinth, approximately 30 cm wide "
            "and 15 cm tall. A small area of general surface marking is also visible nearby. "
            "No cracks, corrosion, water staining, or vegetation growth are recorded in this "
            "observation. This is a low-risk demo example for basic evidence capture and routing."
        ),
        "damage_tags": "graffiti,other",
        "severity": 2,
        "ai_analysis_status": "mock",
        "ai_summary": (
            "Visible indicators detected: graffiti, other. "
            "The visible issue appears limited to surface marking in this observation, so it is "
            "a low-risk triage example for human review and routine routing. "
            "This is a mock/fallback result — connect Azure OpenAI Vision for real image analysis. "
            "AI suggests visible risk indicators only. Humans verify. The system tracks."
        ),
        "ai_confidence": 35,
        "ai_provider": "mock",
        "ai_recommended_action": (
            "Record the evidence for non-urgent review and routing. Contributors should not "
            "clean, touch, or physically intervene."
        ),
        "case": {
            "status": "Routed",
            "routed_to": "Birmingham City Council — Public Monuments Team",
        },
    },
]


def seed(db=None, reviewer_username: str | None = None) -> dict:
    """
    Insert demo data. Returns a summary dict.
    If db is None, opens its own session.
    Idempotent — skips sites that already exist by name.
    """
    close_after = db is None
    if db is None:
        db = SessionLocal()

    sites_created = 0
    obs_created = 0
    cases_created = 0

    try:
        site_map: dict[str, Site] = {}
        for s_data in SEED_SITES:
            existing = db.query(Site).filter(Site.name == s_data["name"]).first()
            if existing:
                site_map[s_data["name"]] = existing
                continue
            site = Site(
                name=s_data["name"],
                location=s_data["location"],
                description=s_data["description"],
                created_at=datetime.utcnow() - timedelta(days=14),
            )
            db.add(site)
            db.flush()
            site_map[s_data["name"]] = site
            sites_created += 1

        for i, o_data in enumerate(SEED_OBSERVATIONS):
            site = site_map.get(o_data["site_name"])
            if not site:
                continue

            # Skip if an observation with the same notes already exists for this site
            already = (
                db.query(Observation)
                .filter(
                    Observation.site_id == site.id,
                    Observation.notes == o_data["notes"],
                )
                .first()
            )
            if already:
                continue

            obs_age = timedelta(days=10 - i * 2)
            submitted_at = datetime.utcnow() - obs_age
            original_tags = [
                tag.strip()
                for tag in o_data["damage_tags"].split(",")
                if tag.strip()
            ]
            obs = Observation(
                site_id=site.id,
                notes=o_data["notes"],
                damage_tags=o_data["damage_tags"],
                severity=o_data["severity"],
                human_review_status=HumanReviewStatus.APPROVED_FOR_AI,
                ai_analysis_status=o_data["ai_analysis_status"],
                ai_summary=o_data["ai_summary"],
                ai_confidence=o_data["ai_confidence"],
                ai_provider=o_data["ai_provider"],
                ai_recommended_action=o_data["ai_recommended_action"],
                ai_raw_response=json.dumps(
                    {
                        "damage_tags": original_tags,
                        "severity": o_data["severity"],
                        "confidence": o_data["ai_confidence"],
                        "summary": o_data["ai_summary"],
                        "recommended_action": o_data["ai_recommended_action"],
                        "uncertainty": (
                            "Mock output requires human verification against "
                            "the submitted evidence."
                        ),
                    }
                ),
                created_at=submitted_at,
                contributor_original=build_contributor_original(
                    notes=o_data["notes"],
                    tags=original_tags,
                    severity=o_data["severity"],
                    submitted_at=submitted_at,
                ),
                reviewed_by=reviewer_username,
            )
            db.add(obs)
            db.flush()
            obs_created += 1

            case_data = o_data["case"]
            case_age = obs_age - timedelta(days=1)
            reviewed_at = (
                datetime.now(timezone.utc) - case_age
            ).isoformat()
            review = {
                "decision": "Accepted",
                "reviewer_notes": "Seeded demonstration case.",
                "reviewed_at": reviewed_at,
                "reviewed_by": reviewer_username,
            }
            obs.ai_review_decision = review
            snapshot = build_case_snapshot(
                observation=obs,
                final_tags=original_tags,
                final_severity=o_data["severity"],
                final_summary=o_data["ai_summary"],
                final_recommended_action=o_data["ai_recommended_action"],
                reviewer_decision=review,
                finalized_by=reviewer_username,
            )
            case = RiskCase(
                observation_id=obs.id,
                risk_score=snapshot["capped_score"],
                risk_band=snapshot["band"],
                status=case_data["status"],
                routed_to=case_data.get("routed_to"),
                final_snapshot=snapshot,
                finalized_by=reviewer_username,
                created_at=datetime.utcnow() - case_age,
                updated_at=datetime.utcnow() - case_age,
            )
            db.add(case)
            db.flush()

            report_path = generate_report(case)
            case.report_path = report_path
            cases_created += 1

        db.commit()

    finally:
        if close_after:
            db.close()

    return {
        "sites_created": sites_created,
        "observations_created": obs_created,
        "cases_created": cases_created,
    }


if __name__ == "__main__":
    result = seed()
    print(
        f"Seed complete: {result['sites_created']} sites, "
        f"{result['observations_created']} observations, "
        f"{result['cases_created']} cases created."
    )
    if result["sites_created"] == 0 and result["observations_created"] == 0:
        print("(All records already exist — nothing was duplicated.)")
