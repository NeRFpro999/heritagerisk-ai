"""
Demo seed data — three sites covering High/Medium/Low risk and all workflow stages.
Idempotent: skips records that already exist. Safe to run multiple times.

  Old Stone Church     — crack + water_staining, sev 5 → score 70 → High,   Needs Review
  Historic Iron Bridge — corrosion + vegetation_growth, sev 4 → score 44 → Medium, Verified
  Memorial Statue      — graffiti, sev 2               → score  6 → Low,    Routed
"""

from datetime import datetime, timedelta

from app.database import SessionLocal, engine, Base
from app.models import Site, Observation, RiskCase
from app.risk import calculate_risk
from app.reports import generate_report

Base.metadata.create_all(bind=engine)

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
    # ── Old Stone Church — crack + water_staining, sev 5 → score 70 → High, Needs Review ──
    {
        "site_name": "Old Stone Church",
        "notes": (
            "Vertical crack visible on the south-east wall face, approximately 80 cm in length "
            "and widening at the base. Significant water staining extends across the lower "
            "course of stones in the same bay. Mortar loss observed between several stones. "
            "Crack appears to have opened since the last community observation six months ago."
        ),
        "damage_tags": "crack,water_staining",
        "severity": 5,
        "ai_analysis_status": "mock",
        "ai_summary": (
            "Visible indicators detected: crack, water_staining. "
            "A widening vertical crack combined with active water staining is a recognised "
            "pattern associated with structural movement or sustained water ingress. "
            "This is a mock/fallback result — connect Azure OpenAI Vision for real image analysis. "
            "AI suggests visible risk indicators only. Humans verify. The system tracks."
        ),
        "ai_confidence": 35,
        "ai_provider": "mock",
        "ai_recommended_action": (
            "Human reviewer should inspect the evidence and prioritise professional review. "
            "Do not attempt repair."
        ),
        "case": {
            "status": "Needs Review",
            "routed_to": None,
        },
    },
    # ── Historic Iron Bridge — corrosion + vegetation_growth, sev 4 → score 44 → Medium, Verified ──
    {
        "site_name": "Historic Iron Bridge",
        "notes": (
            "Active corrosion visible on the north railing and on at least two exposed rivets; "
            "paint surface has flaked exposing bare metal in several patches. "
            "Vegetation growth observed at the base of both bridge abutments, with roots "
            "beginning to penetrate mortar joints. No immediate structural failure signs noted, "
            "but deterioration is clearly progressing since the 2019 inspection record."
        ),
        "damage_tags": "corrosion,vegetation_growth",
        "severity": 4,
        "ai_analysis_status": "mock",
        "ai_summary": (
            "Visible indicators detected: corrosion, vegetation_growth. "
            "Active corrosion with paint failure combined with vegetation root ingress "
            "indicates progressive deterioration. Warrants monitoring and professional review. "
            "This is a mock/fallback result — connect Azure OpenAI Vision for real image analysis. "
            "AI suggests visible risk indicators only. Humans verify. The system tracks."
        ),
        "ai_confidence": 35,
        "ai_provider": "mock",
        "ai_recommended_action": (
            "Verified visible deterioration. Monitor and route to the responsible heritage "
            "or maintenance authority if appropriate."
        ),
        "case": {
            "status": "Verified",
            "routed_to": "Bristol City Council — Heritage Structures Team",
        },
    },
    # ── Memorial Statue — graffiti, sev 2 → score 6 → Low, Routed ──────────────
    {
        "site_name": "Memorial Statue",
        "notes": (
            "Graffiti tag visible on the rear face of the stone plinth, approximately 30 cm wide "
            "and 15 cm tall. Appears to be marker pen, applied recently. "
            "No structural damage or cracking observed in the immediate area. "
            "The memorial surface is otherwise intact and weathering normally for its age."
        ),
        "damage_tags": "graffiti",
        "severity": 2,
        "ai_analysis_status": "mock",
        "ai_summary": (
            "Visible indicators detected: graffiti. "
            "Surface graffiti with no structural implications noted in this observation. "
            "This is a mock/fallback result — connect Azure OpenAI Vision for real image analysis. "
            "AI suggests visible risk indicators only. Humans verify. The system tracks."
        ),
        "ai_confidence": 35,
        "ai_provider": "mock",
        "ai_recommended_action": (
            "Routed for non-urgent review. No public cleaning or physical intervention "
            "should be attempted by contributors."
        ),
        "case": {
            "status": "Routed",
            "routed_to": "Birmingham City Council — Public Monuments Team",
        },
    },
]


def seed(db=None) -> dict:
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
            obs = Observation(
                site_id=site.id,
                image_filename=None,
                notes=o_data["notes"],
                damage_tags=o_data["damage_tags"],
                severity=o_data["severity"],
                ai_analysis_status=o_data["ai_analysis_status"],
                ai_summary=o_data["ai_summary"],
                ai_confidence=o_data["ai_confidence"],
                ai_provider=o_data["ai_provider"],
                ai_recommended_action=o_data["ai_recommended_action"],
                created_at=datetime.utcnow() - obs_age,
            )
            db.add(obs)
            db.flush()
            obs_created += 1

            score, band = calculate_risk(
                [t.strip() for t in o_data["damage_tags"].split(",") if t.strip()],
                o_data["severity"],
            )
            case_data = o_data["case"]
            case_age = obs_age - timedelta(days=1)
            case = RiskCase(
                observation_id=obs.id,
                risk_score=score,
                risk_band=band,
                status=case_data["status"],
                routed_to=case_data.get("routed_to"),
                created_at=datetime.utcnow() - case_age,
                updated_at=datetime.utcnow() - case_age,
            )
            db.add(case)
            db.flush()

            report_path = generate_report(case, obs, site)
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
