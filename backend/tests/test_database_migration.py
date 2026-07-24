import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError

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


def _unique_index_columns(connection, table_name: str) -> set[tuple[str, ...]]:
    unique_columns = set()
    for index_row in connection.exec_driver_sql(
        f"PRAGMA index_list({table_name})"
    ):
        if not index_row[2]:
            continue
        index_name = str(index_row[1]).replace("'", "''")
        unique_columns.add(
            tuple(
                str(column_row[2])
                for column_row in connection.exec_driver_sql(
                    f"PRAGMA index_info('{index_name}')"
                )
            )
        )
    return unique_columns


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
        connection.exec_driver_sql(
            """
            CREATE TABLE experiment_assets (
                id INTEGER PRIMARY KEY,
                external_asset_id VARCHAR(200) NOT NULL UNIQUE,
                site_id INTEGER,
                notes TEXT
            )
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO experiment_assets (
                id, external_asset_id, site_id, notes
            ) VALUES (1, 'legacy-asset', NULL, 'Legacy notes')
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
        session_column_info = {
            row[1]: row
            for row in connection.exec_driver_sql(
                "PRAGMA table_info(assessment_sessions)"
            )
        }
        unique_columns = _unique_index_columns(
            connection,
            "assessment_sessions",
        )
        legacy_site_label = connection.exec_driver_sql(
            """
            SELECT site_label
            FROM experiment_assets
            WHERE external_asset_id = 'legacy-asset'
            """
        ).scalar_one()

    assert {"experiment_assets", "assessment_sessions"} <= tables
    assert {"external_asset_id", "site_label", "site_id", "notes"} <= asset_columns
    assert {
        "asset_id",
        "condition",
        "run_index",
        "image_ids",
        "analysis_result_id",
        "analysis_result",
        "prompt_template_sha256",
        "rendered_request_sha256",
        "schema_version",
        "model_deployment",
        "settings",
        "run_at",
        "run_order",
        "operator",
    } <= session_columns
    assert session_column_info["run_index"][3] == 1
    assert str(session_column_info["run_index"][4]).strip("'\"") == "0"
    assert session_column_info["prompt_template_sha256"][3] == 1
    assert session_column_info["rendered_request_sha256"][3] == 0
    assert "prompt_sha256" not in session_columns
    assert ("asset_id", "condition", "run_index") in unique_columns
    assert ("asset_id", "condition") not in unique_columns
    assert legacy_site_label is None


def test_startup_migration_rebuilds_legacy_assessment_session_constraint(tmp_path):
    engine = _sqlite_engine(tmp_path, "legacy_repeatability.db")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE experiment_assets (
                id INTEGER PRIMARY KEY,
                external_asset_id VARCHAR(200) NOT NULL UNIQUE,
                site_label VARCHAR(200),
                site_id INTEGER,
                notes TEXT
            )
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO experiment_assets (
                id, external_asset_id, site_label, notes
            ) VALUES (1, 'asset-a', 'site-north', 'Legacy notes')
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE assessment_sessions (
                id INTEGER PRIMARY KEY,
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
                CONSTRAINT uq_assessment_asset_condition
                    UNIQUE (asset_id, condition),
                FOREIGN KEY(asset_id) REFERENCES experiment_assets (id)
                    ON DELETE CASCADE
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE INDEX ix_assessment_sessions_id
            ON assessment_sessions (id)
            """
        )
        connection.exec_driver_sql(
            """
            CREATE INDEX ix_assessment_sessions_asset_id
            ON assessment_sessions (asset_id)
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO assessment_sessions (
                id,
                asset_id,
                condition,
                image_ids,
                analysis_result_id,
                analysis_result,
                prompt_sha256,
                schema_version,
                model_deployment,
                settings,
                run_at,
                run_order,
                operator
            ) VALUES (
                7,
                1,
                'single_medium',
                '[101]',
                7,
                '{"status":"mock"}',
                'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                '2',
                'mock',
                '{"mode":"mock"}',
                '2026-07-24 10:00:00',
                1,
                'test-operator'
            )
            """
        )

    apply_sqlite_startup_migrations(engine)
    apply_sqlite_startup_migrations(engine)

    with engine.connect() as connection:
        unique_columns = _unique_index_columns(
            connection,
            "assessment_sessions",
        )
        stored = connection.exec_driver_sql(
            """
            SELECT
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
            FROM assessment_sessions
            """
        ).one()
        indexes = {
            row[1]
            for row in connection.exec_driver_sql(
                "PRAGMA index_list(assessment_sessions)"
            )
        }
        staging_exists = connection.exec_driver_sql(
            """
            SELECT COUNT(*)
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'assessment_sessions__run_index_new'
            """
        ).scalar_one()
        foreign_key_errors = connection.exec_driver_sql(
            "PRAGMA foreign_key_check(assessment_sessions)"
        ).all()

    assert stored == (
        7,
        1,
        "single_medium",
        0,
        "[101]",
        7,
        '{"status":"mock"}',
        "a" * 64,
        None,
        "2",
        "mock",
        '{"mode":"mock"}',
        "2026-07-24 10:00:00",
        1,
        "test-operator",
    )
    assert ("asset_id", "condition", "run_index") in unique_columns
    assert ("asset_id", "condition") not in unique_columns
    assert {
        "ix_assessment_sessions_id",
        "ix_assessment_sessions_asset_id",
    } <= indexes
    assert staging_exists == 0
    assert foreign_key_errors == []

    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            INSERT INTO assessment_sessions (
                id,
                asset_id,
                condition,
                run_index,
                image_ids,
                prompt_template_sha256,
                schema_version,
                model_deployment,
                run_order
            ) VALUES (
                8, 1, 'single_medium', 1, '[101]', ?, '2', 'mock', 1
            )
            """,
            ("b" * 64,),
        )

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                INSERT INTO assessment_sessions (
                    id,
                    asset_id,
                    condition,
                    run_index,
                    image_ids,
                    prompt_template_sha256,
                    schema_version,
                    model_deployment,
                    run_order
                ) VALUES (
                    9, 1, 'single_medium', 1, '[101]', ?, '2', 'mock', 2
                )
                """,
                ("c" * 64,),
            )


def test_startup_migration_renames_hash_on_current_run_index_schema(tmp_path):
    engine = _sqlite_engine(tmp_path, "current_run_index_legacy_hash.db")
    legacy_hash = "d" * 64
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE experiment_assets (
                id INTEGER PRIMARY KEY,
                external_asset_id VARCHAR(200) NOT NULL UNIQUE,
                site_label VARCHAR(200),
                site_id INTEGER,
                notes TEXT
            )
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO experiment_assets (
                id, external_asset_id, site_label, notes
            ) VALUES (1, 'asset-current', 'site-south', 'Current notes')
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE assessment_sessions (
                id INTEGER PRIMARY KEY,
                asset_id INTEGER NOT NULL,
                condition VARCHAR(20) NOT NULL,
                run_index INTEGER NOT NULL DEFAULT 0,
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
                CONSTRAINT uq_assessment_asset_condition_run_index
                    UNIQUE (asset_id, condition, run_index),
                FOREIGN KEY(asset_id) REFERENCES experiment_assets (id)
                    ON DELETE CASCADE
            )
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO assessment_sessions (
                id,
                asset_id,
                condition,
                run_index,
                image_ids,
                analysis_result_id,
                analysis_result,
                prompt_sha256,
                schema_version,
                model_deployment,
                settings,
                run_at,
                run_order,
                operator
            ) VALUES (
                11,
                1,
                'three_view',
                2,
                '[101,102,103]',
                11,
                '{"status":"mock"}',
                ?,
                '2',
                'mock',
                '{"asset_set":"pilot"}',
                '2026-07-24 11:00:00',
                2,
                'test-operator'
            )
            """,
            (legacy_hash,),
        )

    apply_sqlite_startup_migrations(engine)
    apply_sqlite_startup_migrations(engine)

    with engine.connect() as connection:
        columns = {
            row[1]
            for row in connection.exec_driver_sql(
                "PRAGMA table_info(assessment_sessions)"
            )
        }
        unique_columns = _unique_index_columns(
            connection,
            "assessment_sessions",
        )
        stored = connection.exec_driver_sql(
            """
            SELECT
                id,
                condition,
                run_index,
                prompt_template_sha256,
                rendered_request_sha256
            FROM assessment_sessions
            """
        ).one()

    assert "prompt_sha256" not in columns
    assert {
        "prompt_template_sha256",
        "rendered_request_sha256",
    } <= columns
    assert stored == (11, "three_view", 2, legacy_hash, None)
    assert ("asset_id", "condition", "run_index") in unique_columns
    assert ("asset_id", "condition") not in unique_columns


def test_startup_migration_adds_analysis_records_without_backfill(tmp_path):
    engine = _sqlite_engine(tmp_path, "analysis_records_migration.db")
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
            INSERT INTO observations (id, created_at)
            VALUES (1, '2026-07-24 09:00:00')
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
        columns = {
            row[1]
            for row in connection.exec_driver_sql(
                "PRAGMA table_info(ai_analysis_records)"
            )
        }
        indexes = {
            row[1]
            for row in connection.exec_driver_sql(
                "PRAGMA index_list(ai_analysis_records)"
            )
        }
        record_count = connection.exec_driver_sql(
            "SELECT COUNT(*) FROM ai_analysis_records"
        ).scalar_one()

    assert "ai_analysis_records" in tables
    assert {
        "id",
        "observation_id",
        "status",
        "provider",
        "diagnostic",
        "created_at",
    } <= columns
    assert "ix_ai_analysis_records_observation_id" in indexes
    assert record_count == 0
