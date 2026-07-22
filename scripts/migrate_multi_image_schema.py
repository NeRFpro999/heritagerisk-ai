#!/usr/bin/env python3
"""Run the app's idempotent SQLite startup migration for a local database."""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

from sqlalchemy import create_engine


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
DEFAULT_DB_PATH = REPO_ROOT / "data" / "heritagerisk.db"

sys.path.insert(0, str(BACKEND_DIR))

from app.database import Base, apply_sqlite_startup_migrations  # noqa: E402
from app import models as _models  # noqa: E402,F401


def _migrate_file(db_path: Path) -> None:
    migration_engine = create_engine(f"sqlite:///{db_path}")
    try:
        Base.metadata.create_all(bind=migration_engine)
        apply_sqlite_startup_migrations(migration_engine)
    finally:
        migration_engine.dispose()


def migrate(db_path: Path, dry_run: bool = False) -> None:
    if not db_path.exists():
        raise FileNotFoundError(f"Database file not found: {db_path}")

    if dry_run:
        with tempfile.TemporaryDirectory() as temp_dir:
            temporary_db = Path(temp_dir) / db_path.name
            shutil.copy2(db_path, temporary_db)
            _migrate_file(temporary_db)
        print("Dry run completed on a temporary database copy.")
        return

    _migrate_file(db_path)
    print(f"Migration completed for {db_path}.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply HeritageRisk AI SQLite startup migrations."
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"SQLite database path. Default: {DEFAULT_DB_PATH}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run against a temporary copy and leave the source unchanged.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    migrate(args.database, dry_run=args.dry_run)
