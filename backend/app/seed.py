"""
Demo seed data for HeritageRisk AI.

Idempotent: checks for existing site names before inserting.
Safe to run multiple times — will not duplicate records.

Usage:
    cd backend
    python3 -m app.seed          # run directly
    # or visit http://127.0.0.1:8000/seed after starting the server
"""

from datetime import datetime, timedelta

from app.database import SessionLocal, engine, Base
from app.models import Site, Observation, RiskCase
from app.risk import calculate_risk
from app.reports import generate_report

# Ensure tables exist (safe to call multiple times — create_all is idempotent)
Base.metadata.create_all(bind=engine)

SEED_SITES = [
    {
        "name": "Old Stone Church Wall",
        "location": "Kilkenny, Ireland",
        "description": (
            "Medieval limestone boundary wall associated with St. Canice's Cathedral. "
            "Listed structure, Category A protected. Approximate construction 12th century."
        ),
    },
    {
        "name": "Historic Railway Bridge",
        "location": "Brunel Quarter, Bristol, UK",
        "description": (
            "Victorian wrought-iron railway bridge spanning the River Avon. "
            "Grade II listed. Last full inspection 2019. "
            "Adjacent to residential development."
        ),
    },
    {
        "name": "War Memorial Statue",
        "location": "Victoria Square, Birmingham, UK",
        "description": (
            "Bronze memorial sculpture erected 1925. Honours local casualties of WWI. "
            "Grade II* listed. Subject of ongoing community monitoring programme."
        ),
    },
]

SEED_OBSERVATIONS = [
    # ── Old Stone Church Wall ──────────────────────────────────────────────────
    {
        "site_name": "Old Stone Church Wall",
        "notes": (
            "Possible vertical crack visible near the left-hand section of the wall, "
            "approximately 60 cm in length. Crack appears to widen slightly at the base. "
            "Some loss of mortar between stones in the same area."
        ),
        "damage_tags": "crack,erosion",
        "severity": 3,
        "ai_analysis_status": "mock",
        "ai_summary": (
            "Keyword scan detected: crack, erosion. "
            "Vertical cracking with mortar loss is a common indicator of structural movement "
            "or water ingress. This is a mock result — connect Azure OpenAI Vision for real image analysis."
        ),
        "ai_confidence": 35,
        "ai_provider": "mock",
        "ai_recommended_action": "Schedule an in-person inspection to verify these findings before any action.",
        "case": {
            "status": "Needs Review",
            "routed_to": None,
        },
    },
    {
        "site_name": "Old Stone Church Wall",
        "notes": (
            "Graffiti visible on the lower section of the east-facing wall face, "
            "approximately 1.2 m wide and 0.4 m tall. Appears to be spray paint applied recently. "
            "No structural damage observed in this area."
        ),
        "damage_tags": "graffiti",
        "severity": 2,
        "ai_analysis_status": "mock",
        "ai_summary": (
            "Keyword scan detected: graffiti. "
            "Surface graffiti with no structural implications noted. "
            "This is a mock result — connect Azure OpenAI Vision for real image analysis."
        ),
        "ai_confidence": 35,
        "ai_provider": "mock",
        "ai_recommended_action": "Schedule an in-person inspection to verify these findings before any action.",
        "case": {
            "status": "Verified",
            "routed_to": "Kilkenny County Council — Heritage Office",
        },
    },
    # ── Historic Railway Bridge ────────────────────────────────────────────────
    {
        "site_name": "Historic Railway Bridge",
        "notes": (
            "Rust and corrosion clearly visible near the north bridge railing and on two of "
            "the exposed rivets. Paint surface has flaked in multiple places exposing bare metal. "
            "Water staining visible on the underside of the eastern span."
        ),
        "damage_tags": "corrosion,water_staining",
        "severity": 4,
        "ai_analysis_status": "mock",
        "ai_summary": (
            "Keyword scan detected: corrosion, water_staining. "
            "Active corrosion with paint failure and water staining indicates potential "
            "long-term structural risk if untreated. This is a mock result — connect Azure OpenAI Vision for real image analysis."
        ),
        "ai_confidence": 35,
        "ai_provider": "mock",
        "ai_recommended_action": "Schedule an in-person inspection to verify these findings before any action.",
        "case": {
            "status": "Routed",
            "routed_to": "Network Rail — Heritage Structures Team",
        },
    },
    # ── War Memorial Statue ────────────────────────────────────────────────────
    {
        "site_name": "War Memorial Statue",
        "notes": (
            "Water staining visible around the stone base plinth, particularly on the north face "
            "where rainwater pools. Moss and vegetation growth observed in mortar joints at the "
            "base. Some surface erosion to the bronze lettering on the dedication panel."
        ),
        "damage_tags": "water_staining,vegetation_growth,erosion",
        "severity": 3,
        "ai_analysis_status": "mock",
        "ai_summary": (
            "Keyword scan detected: water_staining, vegetation_growth, erosion. "
            "Combined water ingress, biological growth, and surface erosion suggest active "
            "deterioration requiring prompt review. "
            "This is a mock result — connect Azure OpenAI Vision for real image analysis."
        ),
        "ai_confidence": 35,
        "ai_provider": "mock",
        "ai_recommended_action": "Schedule an in-person inspection to verify these findings before any action.",
        "case": {
            "status": "Draft",
            "routed_to": None,
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
        # ── Create sites ───────────────────────────────────────────────────────
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

        # ── Create observations + cases ────────────────────────────────────────
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

            # Create risk case
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
