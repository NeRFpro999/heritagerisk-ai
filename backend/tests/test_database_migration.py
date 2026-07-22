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
        images = connection.exec_driver_sql(
            """
            SELECT observation_id, image_url
            FROM observation_images
            ORDER BY id
            """
        ).all()

    assert "human_review_status" in columns
    assert status == "ApprovedForAI"
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
