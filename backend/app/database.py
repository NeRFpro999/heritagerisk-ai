from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# Resolve the data directory relative to the repo root (two levels up from this file)
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "heritagerisk.db"
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
        if "observations" not in tables:
            return

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

        if "observation_images" not in tables:
            return

        legacy_image_column = next(
            (
                column_name
                for column_name in ("image_filename", "image_path")
                if column_name in columns
            ),
            None,
        )
        if legacy_image_column is None:
            return

        created_at_expression = (
            "COALESCE(observations.created_at, CURRENT_TIMESTAMP)"
            if "created_at" in columns
            else "CURRENT_TIMESTAMP"
        )
        connection.exec_driver_sql(
            f"""
            INSERT INTO observation_images (observation_id, image_url, created_at)
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


def get_db():
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
