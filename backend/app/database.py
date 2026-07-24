import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# Resolve the data directory relative to the repo root (two levels up from this file)
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = Path(os.environ.get("HERITAGERISK_DB_PATH", DATA_DIR / "heritagerisk.db"))
if not DB_PATH.is_absolute():
    DB_PATH = REPO_ROOT / DB_PATH
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # required for SQLite + FastAPI
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def apply_sqlite_startup_migrations(bind: Engine) -> None:
    """Apply the small additive migrations needed by existing local databases."""
    if bind.dialect.name != "sqlite":
        return

    with bind.begin() as connection:
        tables = {
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        if "observations" in tables:
            columns = {
                row[1]
                for row in connection.exec_driver_sql(
                    "PRAGMA table_info(observations)"
                )
            }
            added_review_status = "human_review_status" not in columns
            if added_review_status:
                connection.exec_driver_sql(
                    """
                    ALTER TABLE observations
                    ADD COLUMN human_review_status VARCHAR(20) NOT NULL
                    DEFAULT 'Pending'
                    CHECK (
                        human_review_status IN (
                            'Pending', 'ApprovedForAI', 'Rejected', 'Sensitive'
                        )
                    )
                    """
                )
                # Rows created before the review queue were already trusted MVP records.
                connection.exec_driver_sql(
                    """
                    UPDATE observations
                    SET human_review_status = 'ApprovedForAI'
                    """
                )
                columns.add("human_review_status")

            if "contributor_original" not in columns:
                connection.exec_driver_sql(
                    "ALTER TABLE observations ADD COLUMN contributor_original JSON"
                )
                columns.add("contributor_original")

            if "ai_review_decision" not in columns:
                connection.exec_driver_sql(
                    "ALTER TABLE observations ADD COLUMN ai_review_decision JSON"
                )
                columns.add("ai_review_decision")

            if "reviewed_by" not in columns:
                connection.exec_driver_sql(
                    "ALTER TABLE observations ADD COLUMN reviewed_by VARCHAR(200)"
                )
                columns.add("reviewed_by")

            if "observation_images" in tables:
                legacy_image_column = next(
                    (
                        column_name
                        for column_name in ("image_filename", "image_path")
                        if column_name in columns
                    ),
                    None,
                )
                if legacy_image_column is not None:
                    created_at_expression = (
                        "COALESCE(observations.created_at, CURRENT_TIMESTAMP)"
                        if "created_at" in columns
                        else "CURRENT_TIMESTAMP"
                    )
                    connection.exec_driver_sql(
                        f"""
                        INSERT INTO observation_images (
                            observation_id, image_url, created_at
                        )
                        SELECT
                            observations.id,
                            observations.{legacy_image_column},
                            {created_at_expression}
                        FROM observations
                        WHERE observations.{legacy_image_column} IS NOT NULL
                          AND TRIM(observations.{legacy_image_column}) <> ''
                          AND NOT EXISTS (
                              SELECT 1
                              FROM observation_images
                              WHERE observation_images.observation_id = observations.id
                                AND observation_images.image_url =
                                    observations.{legacy_image_column}
                          )
                        """
                    )

        if "risk_cases" in tables:
            case_columns = {
                row[1]
                for row in connection.exec_driver_sql(
                    "PRAGMA table_info(risk_cases)"
                )
            }
            if "final_snapshot" not in case_columns:
                connection.exec_driver_sql(
                    "ALTER TABLE risk_cases ADD COLUMN final_snapshot JSON"
                )
                case_columns.add("final_snapshot")

            if "finalized_by" not in case_columns:
                connection.exec_driver_sql(
                    "ALTER TABLE risk_cases ADD COLUMN finalized_by VARCHAR(200)"
                )
                case_columns.add("finalized_by")

        if "risk_cases" in tables and "case_events" not in tables:
            connection.exec_driver_sql(
                """
                CREATE TABLE case_events (
                    id INTEGER NOT NULL,
                    case_id INTEGER NOT NULL,
                    from_status VARCHAR(50) NOT NULL,
                    to_status VARCHAR(50) NOT NULL,
                    reviewer VARCHAR(200) NOT NULL,
                    note TEXT,
                    created_at DATETIME,
                    PRIMARY KEY (id),
                    FOREIGN KEY(case_id) REFERENCES risk_cases (id) ON DELETE CASCADE
                )
                """
            )
            connection.exec_driver_sql(
                "CREATE INDEX ix_case_events_id ON case_events (id)"
            )
            connection.exec_driver_sql(
                "CREATE INDEX ix_case_events_case_id ON case_events (case_id)"
            )

        if "experiment_assets" not in tables:
            connection.exec_driver_sql(
                """
                CREATE TABLE experiment_assets (
                    id INTEGER NOT NULL,
                    external_asset_id VARCHAR(200) NOT NULL,
                    site_id INTEGER,
                    notes TEXT,
                    PRIMARY KEY (id),
                    UNIQUE (external_asset_id),
                    FOREIGN KEY(site_id) REFERENCES sites (id)
                )
                """
            )
            connection.exec_driver_sql(
                "CREATE INDEX ix_experiment_assets_id ON experiment_assets (id)"
            )

        if "assessment_sessions" not in tables:
            connection.exec_driver_sql(
                """
                CREATE TABLE assessment_sessions (
                    id INTEGER NOT NULL,
                    asset_id INTEGER NOT NULL,
                    condition VARCHAR(20) NOT NULL,
                    image_ids JSON NOT NULL,
                    analysis_result_id INTEGER,
                    analysis_result JSON,
                    prompt_sha256 VARCHAR(64) NOT NULL,
                    schema_version VARCHAR(20) NOT NULL,
                    model_deployment VARCHAR(200) NOT NULL,
                    settings JSON,
                    run_at DATETIME,
                    run_order INTEGER NOT NULL,
                    operator VARCHAR(200),
                    PRIMARY KEY (id),
                    CONSTRAINT uq_assessment_asset_condition
                        UNIQUE (asset_id, condition),
                    FOREIGN KEY(asset_id) REFERENCES experiment_assets (id)
                        ON DELETE CASCADE
                )
                """
            )
            connection.exec_driver_sql(
                "CREATE INDEX ix_assessment_sessions_id ON assessment_sessions (id)"
            )
            connection.exec_driver_sql(
                "CREATE INDEX ix_assessment_sessions_asset_id ON assessment_sessions (asset_id)"
            )


def get_db():
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
