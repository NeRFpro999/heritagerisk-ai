import io
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from PIL import ExifTags, Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from tests.auth_helpers import (
    configure_test_reviewer,
    login_reviewer,
    post_form,
    restore_test_reviewer,
)
from tests.image_helpers import TINY_PNG, make_gps_jpeg, make_oriented_jpeg


MISMATCH_DETAIL = "Image content does not match its file extension."
INVALID_IMAGE_DETAIL = "Uploaded file is not a valid JPG, PNG, or WEBP image."


@pytest.fixture()
def upload_context(tmp_path):
    from app.database import Base, get_db
    from app.main import app
    import app.main as main_module
    from app.models import Site

    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    TestSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=test_engine,
    )

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    original_uploads_dir = main_module.UPLOADS_DIR
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir()
    main_module.UPLOADS_DIR = uploads_dir

    db = TestSessionLocal()
    site = Site(name="Upload Security Test Site")
    db.add(site)
    db.commit()

    reviewer_settings = configure_test_reviewer()
    client = TestClient(app, raise_server_exceptions=True)
    yield {
        "client": client,
        "db": db,
        "site_id": site.id,
        "uploads_dir": uploads_dir,
    }

    db.close()
    restore_test_reviewer(reviewer_settings)
    app.dependency_overrides.pop(get_db, None)
    main_module.UPLOADS_DIR = original_uploads_dir
    test_engine.dispose()


def _post_upload(context, upload_path, filename, content, content_type):
    client = context["client"]
    site_id = context["site_id"]
    upload = (filename, io.BytesIO(content), content_type)

    if upload_path == "public":
        return post_form(
            client,
            "/observations/submit",
            data={"site_id": str(site_id), "severity": "1"},
            files=[("images", upload)],
        )
    login_reviewer(client)
    return post_form(
        client,
        "/sites",
        data={"name": "Rejected Reviewer Intake"},
        files=[("images", upload)],
        follow_redirects=False,
    )


def _assert_no_upload_side_effects(context, site_count, observation_count):
    from app.models import Observation, Site

    db = context["db"]
    db.expire_all()
    assert db.query(Site).count() == site_count
    assert db.query(Observation).count() == observation_count
    assert list(context["uploads_dir"].iterdir()) == []


def _stored_path(context, response) -> Path:
    image_url = response.json()["image_urls"][0]
    return context["uploads_dir"] / image_url.rsplit("/", 1)[-1]


@pytest.mark.parametrize("upload_path", ["public", "reviewer"])
def test_png_renamed_as_jpeg_is_rejected_by_every_upload_path(
    upload_context,
    upload_path,
):
    from app.models import Observation, Site
    from app.services.ai_analysis import AIAnalysisResult

    db = upload_context["db"]
    site_count = db.query(Site).count()
    observation_count = db.query(Observation).count()
    db.commit()
    fallback_result = AIAnalysisResult(
        damage_tags=[],
        severity=1,
        confidence=0,
        summary="Mock result must not be reached for an invalid upload.",
        recommended_action="Human review required.",
        provider="mock",
    )

    with patch(
        "app.main.analyze_observation_images",
        return_value=fallback_result,
    ) as analyze_mock:
        response = _post_upload(
            upload_context,
            upload_path,
            "evidence.jpg",
            TINY_PNG,
            "image/jpeg",
        )

    assert response.status_code == 400
    assert response.json()["detail"] == MISMATCH_DETAIL
    analyze_mock.assert_not_called()
    _assert_no_upload_side_effects(
        upload_context,
        site_count,
        observation_count,
    )


def test_text_named_as_png_is_rejected(upload_context):
    from app.models import Observation, Site

    db = upload_context["db"]
    site_count = db.query(Site).count()
    observation_count = db.query(Observation).count()
    db.commit()

    response = _post_upload(
        upload_context,
        "public",
        "notes.png",
        b"This is text, not an image.",
        "image/png",
    )

    assert response.status_code == 400
    assert response.json()["detail"] == INVALID_IMAGE_DETAIL
    _assert_no_upload_side_effects(
        upload_context,
        site_count,
        observation_count,
    )


def test_stored_jpeg_has_no_exif_or_gps_metadata(upload_context):
    gps_jpeg = make_gps_jpeg()
    with Image.open(io.BytesIO(gps_jpeg)) as source:
        source_exif = source.getexif()
        assert source_exif.get_ifd(ExifTags.IFD.GPSInfo)

    response = _post_upload(
        upload_context,
        "public",
        "location.jpg",
        gps_jpeg,
        "image/jpeg",
    )

    assert response.status_code == 200
    stored_path = _stored_path(upload_context, response)
    assert stored_path.exists()
    assert stored_path.name != "location.jpg"
    assert stored_path.suffix == ".jpg"
    assert len(stored_path.stem) == 32
    int(stored_path.stem, 16)

    stored_bytes = stored_path.read_bytes()
    assert b"Exif\x00\x00" not in stored_bytes
    with Image.open(stored_path) as stored:
        stored.load()
        assert stored.format == "JPEG"
        assert dict(stored.getexif()) == {}
        assert stored.getexif().get_ifd(ExifTags.IFD.GPSInfo) == {}


def test_orientation_is_applied_before_metadata_is_removed(upload_context):
    oriented_jpeg = make_oriented_jpeg()
    with Image.open(io.BytesIO(oriented_jpeg)) as source:
        assert source.size == (40, 20)
        assert source.getexif()[ExifTags.Base.Orientation] == 6

    response = _post_upload(
        upload_context,
        "public",
        "rotated.jpg",
        oriented_jpeg,
        "image/jpeg",
    )

    assert response.status_code == 200
    stored_path = _stored_path(upload_context, response)
    with Image.open(stored_path) as stored:
        stored.load()
        assert stored.size == (20, 40)
        assert dict(stored.getexif()) == {}
        pixels = stored.convert("RGB")

    top_pixel = pixels.getpixel((10, 5))
    bottom_pixel = pixels.getpixel((10, 35))
    assert top_pixel[0] > 200 and top_pixel[2] < 50
    assert bottom_pixel[2] > 200 and bottom_pixel[0] < 50


def test_image_over_ten_mib_is_rejected(upload_context):
    from app.main import MAX_IMAGE_SIZE_BYTES
    from app.models import Observation, Site

    oversized_png = TINY_PNG + b"\x00" * (
        MAX_IMAGE_SIZE_BYTES + 1 - len(TINY_PNG)
    )
    assert len(oversized_png) == 10 * 1024 * 1024 + 1

    db = upload_context["db"]
    site_count = db.query(Site).count()
    observation_count = db.query(Observation).count()
    db.commit()
    response = _post_upload(
        upload_context,
        "public",
        "oversized.png",
        oversized_png,
        "image/png",
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Image must be 10 MB or smaller."
    _assert_no_upload_side_effects(
        upload_context,
        site_count,
        observation_count,
    )
