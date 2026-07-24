from sqlalchemy import create_engine

from app.database import apply_sqlite_startup_migrations


def _sqlite_engine(tmp_path, name: str):
    return create_engine(f"sqlite:///{tmp_path / name}")


def _create_legacy_tables(engine) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE observations (
                id INTEGER PRIMARY KEY,
                image_filename VARCHAR(300),
                created_at DATETIME
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE observation_images (
                id INTEGER PRIMARY KEY,
                observation_id INTEGER NOT NULL,
                image_url VARCHAR(500) NOT NULL,
                created_at DATETIME NOT NULL
            )
            """
        )


def test_startup_migration_adds_review_status_and_backfills_once(tmp_path):
    engine = _sqlite_engine(tmp_path, "legacy.db")
    _create_legacy_tables(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            INSERT INTO observations (id, image_filename, created_at)
            VALUES (1, 'legacy.jpg', '2026-06-02 12:00:00')
            """
        )

    apply_sqlite_startup_migrations(engine)
    apply_sqlite_startup_migrations(engine)

    with engine.connect() as connection:
        columns = {
            row[1]
            for row in connection.exec_driver_sql(
                "PRAGMA table_info(observations)"
            )
        }
        status = connection.exec_driver_sql(
            "SELECT human_review_status FROM observations WHERE id = 1"
        ).scalar_one()
        reviewed_by = connection.exec_driver_sql(
            "SELECT reviewed_by FROM observations WHERE id = 1"
        ).scalar_one()
        images = connection.exec_driver_sql(
            """
            SELECT observation_id, image_url
            FROM observation_images
            ORDER BY id
            """
        ).all()

    assert "human_review_status" in columns
    assert "reviewed_by" in columns
    assert status == "ApprovedForAI"
    assert reviewed_by is None
    assert images == [(1, "legacy.jpg")]


def test_startup_migration_preserves_existing_pending_status(tmp_path):
    engine = _sqlite_engine(tmp_path, "current.db")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE observations (
                id INTEGER PRIMARY KEY,
                human_review_status VARCHAR(20) NOT NULL DEFAULT 'Pending'
            )
            """
        )
        connection.exec_driver_sql(
            "INSERT INTO observations (id, human_review_status) VALUES (1, 'Pending')"
        )

    apply_sqlite_startup_migrations(engine)
    apply_sqlite_startup_migrations(engine)

    with engine.connect() as connection:
        status = connection.exec_driver_sql(
            "SELECT human_review_status FROM observations WHERE id = 1"
        ).scalar_one()

    assert status == "Pending"


def test_startup_migration_adds_nullable_provenance_without_image_table(tmp_path):
    engine = _sqlite_engine(tmp_path, "legacy_provenance.db")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE observations (
                id INTEGER PRIMARY KEY,
                created_at DATETIME
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE risk_cases (
                id INTEGER PRIMARY KEY,
                observation_id INTEGER NOT NULL,
                risk_score INTEGER NOT NULL,
                risk_band VARCHAR(20) NOT NULL
            )
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO observations (id, created_at)
            VALUES (1, '2026-06-02 12:00:00')
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO risk_cases (
                id, observation_id, risk_score, risk_band
            ) VALUES (1, 1, 24, 'Low')
            """
        )

    apply_sqlite_startup_migrations(engine)
    apply_sqlite_startup_migrations(engine)

    with engine.connect() as connection:
        tables = {
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        observation_columns = {
            row[1]
            for row in connection.exec_driver_sql(
                "PRAGMA table_info(observations)"
            )
        }
        case_columns = {
            row[1]
            for row in connection.exec_driver_sql(
                "PRAGMA table_info(risk_cases)"
            )
        }
        contributor_original, ai_review_decision, reviewed_by = (
            connection.exec_driver_sql(
                """
                SELECT contributor_original, ai_review_decision, reviewed_by
                FROM observations
                WHERE id = 1
                """
            ).one()
        )
        final_snapshot, finalized_by = connection.exec_driver_sql(
            "SELECT final_snapshot, finalized_by FROM risk_cases WHERE id = 1"
        ).one()

    assert "observation_images" not in tables
    assert "case_events" in tables
    assert {
        "contributor_original",
        "ai_review_decision",
        "reviewed_by",
    } <= observation_columns
    assert {"final_snapshot", "finalized_by"} <= case_columns
    # Legacy rows cannot truthfully reconstruct values that were never recorded.
    assert contributor_original is None
    assert ai_review_decision is None
    assert reviewed_by is None
    assert final_snapshot is None
    assert finalized_by is None


def test_startup_migration_preserves_existing_provenance_byte_for_byte(tmp_path):
    engine = _sqlite_engine(tmp_path, "current_provenance.db")
    contributor_original = (
        '{"notes":"Submitted notes","tags":["crack"],"severity":3,'
        '"submitted_at":"2026-07-22T09:30:00"}'
    )
    ai_review_decision = (
        '{"decision":"AcceptedWithEdits","reviewed_at":"2026-07-22T10:00:00"}'
    )
    final_snapshot = (
        '{"final_tags":["crack"],"final_severity":4,"capped_score":32,'
        '"band":"Medium"}'
    )
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE observations (
                id INTEGER PRIMARY KEY,
                human_review_status VARCHAR(20) NOT NULL DEFAULT 'Pending',
                contributor_original JSON,
                ai_review_decision JSON,
                reviewed_by VARCHAR(200)
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE risk_cases (
                id INTEGER PRIMARY KEY,
                observation_id INTEGER NOT NULL,
                final_snapshot JSON,
                finalized_by VARCHAR(200)
            )
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO observations (
                id, human_review_status, contributor_original, ai_review_decision,
                reviewed_by
            ) VALUES (1, 'ApprovedForAI', ?, ?, 'reviewer-one')
            """,
            (contributor_original, ai_review_decision),
        )
        connection.exec_driver_sql(
            """
            INSERT INTO risk_cases (
                id, observation_id, final_snapshot, finalized_by
            ) VALUES (1, 1, ?, 'reviewer-two')
            """,
            (final_snapshot,),
        )

    apply_sqlite_startup_migrations(engine)
    apply_sqlite_startup_migrations(engine)

    with engine.connect() as connection:
        stored_original, stored_decision, stored_reviewer = (
            connection.exec_driver_sql(
                """
                SELECT contributor_original, ai_review_decision, reviewed_by
                FROM observations
                WHERE id = 1
                """
            ).one()
        )
        stored_snapshot, stored_finalizer = connection.exec_driver_sql(
            "SELECT final_snapshot, finalized_by FROM risk_cases WHERE id = 1"
        ).one()

    assert stored_original == contributor_original
    assert stored_decision == ai_review_decision
    assert stored_reviewer == "reviewer-one"
    assert stored_snapshot == final_snapshot
    assert stored_finalizer == "reviewer-two"


def test_startup_migration_adds_experiment_tables_idempotently(tmp_path):
    engine = _sqlite_engine(tmp_path, "experiment_migration.db")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE sites (
                id INTEGER PRIMARY KEY,
                name VARCHAR(200) NOT NULL
            )
            """
        )

    apply_sqlite_startup_migrations(engine)
    apply_sqlite_startup_migrations(engine)

    with engine.connect() as connection:
        tables = {
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        asset_columns = {
            row[1]
            for row in connection.exec_driver_sql(
                "PRAGMA table_info(experiment_assets)"
            )
        }
        session_columns = {
            row[1]
            for row in connection.exec_driver_sql(
                "PRAGMA table_info(assessment_sessions)"
            )
        }
        unique_indexes = {
            row[1]
            for row in connection.exec_driver_sql(
                "PRAGMA index_list(assessment_sessions)"
            )
            if row[2]
        }

    assert {"experiment_assets", "assessment_sessions"} <= tables
    assert {"external_asset_id", "site_id", "notes"} <= asset_columns
    assert {
        "asset_id",
        "condition",
        "image_ids",
        "analysis_result_id",
        "analysis_result",
        "prompt_sha256",
        "schema_version",
        "model_deployment",
        "settings",
        "run_at",
        "run_order",
        "operator",
    } <= session_columns
    assert unique_indexes
