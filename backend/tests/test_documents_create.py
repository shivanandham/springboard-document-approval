import hashlib

import pytest
from sqlalchemy import select

from app import services
from app.config import settings
from app.main import app
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


async def test_create_description_length(upload, sam):
    assert (await upload(sam, description="x" * 5000)).status_code == 201
    resp = await upload(sam, description="x" * 5001)
    assert_error(resp, 400, "VALIDATION_ERROR", "description")


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


async def test_declared_oversize_upload_rejected_before_body_is_read(monkeypatch):
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    sent = []

    async def receive():
        raise AssertionError("the body must not be read")

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/documents",
        "raw_path": b"/api/documents",
        "root_path": "",
        "query_string": b"",
        "headers": [(b"content-length", b"999999999")],
        "client": ("127.0.0.1", 1),
        "server": ("test", 80),
    }
    await app(scope, receive, send)
    assert sent[0]["status"] == 413
    assert b'"FILE_TOO_LARGE"' in sent[1]["body"]


def chunked_multipart(file_size: int, sent: list[int] | None = None, chunk: int = 256 * 1024):
    boundary = "docflow-boundary"
    sent = sent if sent is not None else []

    async def body():
        yield (
            f'--{boundary}\r\nContent-Disposition: form-data; name="title"\r\n\r\nBig\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="big.txt"'
            "\r\nContent-Type: text/plain\r\n\r\n"
        ).encode()
        for start in range(0, file_size, chunk):
            sent.append(min(chunk, file_size - start))
            yield b"x" * sent[-1]
        yield f"\r\n--{boundary}--\r\n".encode()

    return {"content-type": f"multipart/form-data; boundary={boundary}"}, body()


async def test_chunked_upload_under_limit(client, auth, sam):
    headers, body = chunked_multipart(1000)
    resp = await client.post("/api/documents", headers={**auth(sam), **headers}, content=body)
    assert resp.status_code == 201, resp.text
    assert resp.json()["file"]["size_bytes"] == 1000


async def test_chunked_upload_over_cap_is_cut_off(client, auth, sam, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    before = stored_files()
    sent: list[int] = []
    headers, body = chunked_multipart(8 * 1024 * 1024, sent)
    resp = await client.post("/api/documents", headers={**auth(sam), **headers}, content=body)
    assert "content-length" not in resp.request.headers
    assert_error(resp, 413, "FILE_TOO_LARGE", "file")
    assert sum(sent) < 3 * 1024 * 1024  # reading stopped just past the 2 MB cap
    assert stored_files() == before


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
