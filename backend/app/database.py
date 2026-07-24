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


def _create_assessment_sessions_table(connection, table_name: str) -> None:
    allowed_names = {
        "assessment_sessions",
        "assessment_sessions__run_index_new",
    }
    if table_name not in allowed_names:
        raise ValueError(f"Unexpected assessment-session table name: {table_name}")
    connection.exec_driver_sql(
        f"""
        CREATE TABLE {table_name} (
            id INTEGER NOT NULL,
            asset_id INTEGER NOT NULL,
            condition VARCHAR(20) NOT NULL,
            run_index INTEGER NOT NULL DEFAULT 0,
            image_ids JSON NOT NULL,
            analysis_result_id INTEGER,
            analysis_result JSON,
            prompt_template_sha256 VARCHAR(64) NOT NULL,
            rendered_request_sha256 VARCHAR(64),
            schema_version VARCHAR(20) NOT NULL,
            model_deployment VARCHAR(200) NOT NULL,
            settings JSON,
            run_at DATETIME,
            run_order INTEGER NOT NULL,
            operator VARCHAR(200),
            PRIMARY KEY (id),
            CONSTRAINT uq_assessment_asset_condition_run_index
                UNIQUE (asset_id, condition, run_index),
            FOREIGN KEY(asset_id) REFERENCES experiment_assets (id)
                ON DELETE CASCADE
        )
        """
    )


def _create_assessment_session_indexes(connection) -> None:
    connection.exec_driver_sql(
        "CREATE INDEX ix_assessment_sessions_id ON assessment_sessions (id)"
    )
    connection.exec_driver_sql(
        "CREATE INDEX ix_assessment_sessions_asset_id "
        "ON assessment_sessions (asset_id)"
    )


def _assessment_session_unique_columns(connection) -> set[tuple[str, ...]]:
    unique_columns: set[tuple[str, ...]] = set()
    for index_row in connection.exec_driver_sql(
        "PRAGMA index_list(assessment_sessions)"
    ):
        if not index_row[2]:
            continue
        index_name = str(index_row[1]).replace("'", "''")
        columns = tuple(
            str(column_row[2])
            for column_row in connection.exec_driver_sql(
                f"PRAGMA index_info('{index_name}')"
            )
        )
        unique_columns.add(columns)
    return unique_columns


def _migrate_assessment_session_hash_columns(connection) -> None:
    columns = {
        row[1]
        for row in connection.exec_driver_sql(
            "PRAGMA table_info(assessment_sessions)"
        )
    }
    if "prompt_template_sha256" not in columns:
        if "prompt_sha256" not in columns:
            raise RuntimeError(
                "Cannot migrate assessment_sessions: no prompt hash column exists."
            )
        connection.exec_driver_sql(
            """
            ALTER TABLE assessment_sessions
            RENAME COLUMN prompt_sha256 TO prompt_template_sha256
            """
        )
        columns.remove("prompt_sha256")
        columns.add("prompt_template_sha256")
    if "rendered_request_sha256" not in columns:
        connection.exec_driver_sql(
            """
            ALTER TABLE assessment_sessions
            ADD COLUMN rendered_request_sha256 VARCHAR(64)
            """
        )


def _migrate_assessment_session_run_index(connection) -> None:
    columns = {
        row[1]
        for row in connection.exec_driver_sql(
            "PRAGMA table_info(assessment_sessions)"
        )
    }
    unique_columns = _assessment_session_unique_columns(connection)
    required_unique = ("asset_id", "condition", "run_index")
    legacy_unique = ("asset_id", "condition")
    if (
        "run_index" in columns
        and required_unique in unique_columns
        and legacy_unique not in unique_columns
    ):
        return

    staging_table = "assessment_sessions__run_index_new"
    staging_exists = connection.exec_driver_sql(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (staging_table,),
    ).first()
    if staging_exists is not None:
        raise RuntimeError(
            "Cannot migrate assessment_sessions: staging table already exists."
        )

    _create_assessment_sessions_table(connection, staging_table)
    run_index_expression = (
        "COALESCE(run_index, 0)" if "run_index" in columns else "0"
    )
    connection.exec_driver_sql(
        f"""
        INSERT INTO {staging_table} (
            id,
            asset_id,
            condition,
            run_index,
            image_ids,
            analysis_result_id,
            analysis_result,
            prompt_template_sha256,
            rendered_request_sha256,
            schema_version,
            model_deployment,
            settings,
            run_at,
            run_order,
            operator
        )
        SELECT
            id,
            asset_id,
            condition,
            {run_index_expression},
            image_ids,
            analysis_result_id,
            analysis_result,
            prompt_template_sha256,
            rendered_request_sha256,
            schema_version,
            model_deployment,
            settings,
            run_at,
            run_order,
            operator
        FROM assessment_sessions
        """
    )
    connection.exec_driver_sql("DROP TABLE assessment_sessions")
    connection.exec_driver_sql(
        f"ALTER TABLE {staging_table} RENAME TO assessment_sessions"
    )
    _create_assessment_session_indexes(connection)


def apply_sqlite_startup_migrations(bind: Engine) -> None:
    """Apply focused compatibility migrations to existing local databases."""
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

        if "observations" in tables and "ai_analysis_records" not in tables:
            connection.exec_driver_sql(
                """
                CREATE TABLE ai_analysis_records (
                    id INTEGER NOT NULL,
                    observation_id INTEGER NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    provider VARCHAR(200) NOT NULL,
                    diagnostic TEXT,
                    created_at DATETIME NOT NULL,
                    PRIMARY KEY (id),
                    FOREIGN KEY(observation_id) REFERENCES observations (id)
                        ON DELETE CASCADE
                )
                """
            )
            connection.exec_driver_sql(
                "CREATE INDEX ix_ai_analysis_records_id "
                "ON ai_analysis_records (id)"
            )
            connection.exec_driver_sql(
                "CREATE INDEX ix_ai_analysis_records_observation_id "
                "ON ai_analysis_records (observation_id)"
            )

        if "experiment_assets" not in tables:
            connection.exec_driver_sql(
                """
                CREATE TABLE experiment_assets (
                    id INTEGER NOT NULL,
                    external_asset_id VARCHAR(200) NOT NULL,
                    site_label VARCHAR(200),
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

        experiment_asset_columns = {
            row[1]
            for row in connection.exec_driver_sql(
                "PRAGMA table_info(experiment_assets)"
            )
        }
        if "site_label" not in experiment_asset_columns:
            connection.exec_driver_sql(
                "ALTER TABLE experiment_assets ADD COLUMN site_label VARCHAR(200)"
            )

        if "assessment_sessions" not in tables:
            _create_assessment_sessions_table(connection, "assessment_sessions")
            _create_assessment_session_indexes(connection)
        else:
            _migrate_assessment_session_hash_columns(connection)
            _migrate_assessment_session_run_index(connection)


def get_db():
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
