import hashlib

import pytest
from sqlalchemy import select

from app import services
from app.config import settings
from app.models import DocumentEvent, DocumentFile


@pytest.fixture
async def sam(make_user):
    return await make_user("submitter")


def assert_error(resp, status, code, field=None):
    assert resp.status_code == status, resp.text
    error = resp.json()["error"]
    assert error["code"] == code
    if field:
        assert field in error["fields"]


def stored_files():
    return sorted(p for p in settings.storage_dir.rglob("*") if p.is_file())


async def test_create_happy_path(upload, sam, session):
    content = b"%PDF-1.7 quarterly numbers"
    resp = await upload(sam, description="  Q3 figures  ")
    assert resp.status_code == 201, resp.text
    doc = resp.json()
    assert doc["title"] == "Quarterly report"
    assert doc["description"] == "Q3 figures"
    assert doc["status"] == "pending"
    assert doc["version"] == 1
    assert doc["submitter"] == {"id": str(sam.id), "full_name": sam.full_name, "email": sam.email}
    assert doc["decided_by"] is None and doc["decided_at"] is None
    assert doc["file"]["original_name"] == "report.pdf"
    assert doc["file"]["content_type"] == "application/pdf"
    assert doc["file"]["size_bytes"] == len(content)
    assert doc["file"]["sha256"] == hashlib.sha256(content).hexdigest()

    row = await session.scalar(select(DocumentFile).where(DocumentFile.document_id == doc["id"]))
    assert (settings.storage_dir / row.storage_key).read_bytes() == content
    assert not list((settings.storage_dir / "tmp").glob("*"))


async def test_create_writes_submitted_event(upload, sam, session):
    doc = (await upload(sam)).json()
    events = list(
        await session.scalars(select(DocumentEvent).where(DocumentEvent.document_id == doc["id"]))
    )
    assert [(e.event, e.from_status, e.to_status, e.actor_id) for e in events] == [
        ("submitted", None, "pending", sam.id)
    ]


@pytest.mark.parametrize(
    ("filename", "content_type"),
    [
        ("notes.txt", "text/plain"),
        ("scan.PNG", "image/png"),
        ("photo.jpg", "image/jpeg"),
        ("photo.jpeg", "image/jpeg"),
        ("contract.docx", services.ALLOWED_TYPES[".docx"]),
    ],
)
async def test_create_allowed_types(upload, sam, filename, content_type):
    resp = await upload(sam, filename=filename, content=b"data")
    assert resp.status_code == 201
    assert resp.json()["file"]["content_type"] == content_type


async def test_create_blank_description_is_null(upload, sam):
    assert (await upload(sam, description="   ")).json()["description"] is None


async def test_create_strips_path_from_filename(upload, sam):
    resp = await upload(sam, filename="../../etc/report.pdf")
    assert resp.json()["file"]["original_name"] == "report.pdf"


async def test_create_missing_title(upload, sam):
    assert_error(await upload(sam, title=None), 400, "VALIDATION_ERROR", "title")


async def test_create_blank_title(upload, sam):
    assert_error(await upload(sam, title="   "), 400, "VALIDATION_ERROR", "title")


async def test_create_title_too_long(upload, sam):
    assert_error(await upload(sam, title="x" * 201), 400, "VALIDATION_ERROR", "title")


async def test_create_title_at_max_length(upload, sam):
    assert (await upload(sam, title="x" * 200)).status_code == 201


async def test_create_no_file(upload, sam):
    assert_error(await upload(sam, filename=None), 400, "VALIDATION_ERROR", "file")


async def test_create_empty_file(upload, sam):
    before = stored_files()
    assert_error(await upload(sam, content=b""), 400, "VALIDATION_ERROR", "file")
    assert stored_files() == before


async def test_create_file_too_large(upload, sam, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    before = stored_files()
    resp = await upload(sam, content=b"x" * (1024 * 1024 + 1))
    assert_error(resp, 413, "FILE_TOO_LARGE", "file")
    assert stored_files() == before


async def test_create_file_at_limit(upload, sam, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    assert (await upload(sam, content=b"x" * 1024 * 1024)).status_code == 201


@pytest.mark.parametrize("filename", ["malware.exe", "archive.zip", "noextension", "report.pdf.sh"])
async def test_create_wrong_type(upload, sam, filename):
    resp = await upload(sam, filename=filename)
    assert_error(resp, 415, "UNSUPPORTED_FILE_TYPE", "file")


async def test_create_db_failure_leaves_no_file(upload, sam, monkeypatch):
    async def boom(*_):
        raise RuntimeError("db down")

    before = stored_files()
    monkeypatch.setattr("sqlalchemy.ext.asyncio.AsyncSession.commit", boom)
    with pytest.raises(RuntimeError):
        await upload(sam)
    assert stored_files() == before
