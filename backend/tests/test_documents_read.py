import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models import DocumentStatus


@pytest.fixture
async def users(make_user):
    return {
        "sam": await make_user("submitter"),
        "other": await make_user("submitter"),
        "riya": await make_user("reviewer"),
    }


@pytest.fixture
async def docs(users, make_document):
    base = datetime(2026, 1, 1, tzinfo=UTC)
    sam, other, riya = users["sam"], users["other"], users["riya"]
    statuses = [DocumentStatus.pending, DocumentStatus.approved, DocumentStatus.rejected]
    created = []
    for i in range(6):
        owner = sam if i % 2 == 0 else other
        created.append(
            await make_document(
                owner,
                title=f"Doc {i}",
                status=statuses[i % 3],
                decided_by=riya,
                created_at=base + timedelta(days=i),
            )
        )
    return created


async def list_titles(client, auth, user, **params):
    resp = await client.get("/api/documents", headers=auth(user), params=params)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return [d["title"] for d in body["items"]], body["total"]


async def test_submitter_sees_only_own(client, auth, users, docs):
    assert await list_titles(client, auth, users["sam"]) == (["Doc 4", "Doc 2", "Doc 0"], 3)
    assert await list_titles(client, auth, users["other"]) == (["Doc 5", "Doc 3", "Doc 1"], 3)


async def test_reviewer_sees_all(client, auth, users, docs):
    titles, total = await list_titles(client, auth, users["riya"])
    assert total == 6
    assert titles == [f"Doc {i}" for i in reversed(range(6))]


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("pending", ["Doc 3", "Doc 0"]),
        ("approved", ["Doc 4", "Doc 1"]),
        ("rejected", ["Doc 5", "Doc 2"]),
    ],
)
async def test_status_filter(client, auth, users, docs, status, expected):
    assert await list_titles(client, auth, users["riya"], status=status) == (expected, 2)


async def test_status_filter_combines_with_ownership(client, auth, users, docs):
    assert await list_titles(client, auth, users["sam"], status="pending") == (["Doc 0"], 1)


async def test_pagination_and_total(client, auth, users, docs):
    riya = users["riya"]
    assert await list_titles(client, auth, riya, limit=4) == (
        ["Doc 5", "Doc 4", "Doc 3", "Doc 2"],
        6,
    )
    assert await list_titles(client, auth, riya, limit=4, offset=4) == (["Doc 1", "Doc 0"], 6)
    assert await list_titles(client, auth, riya, offset=10) == ([], 6)


async def test_sort_order(client, auth, users, docs):
    titles, _ = await list_titles(client, auth, users["riya"], sort="created_at")
    assert titles == [f"Doc {i}" for i in range(6)]


async def test_empty_list(client, auth, users):
    assert await list_titles(client, auth, users["sam"]) == ([], 0)


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"limit": 101}, "limit"),
        ({"limit": 0}, "limit"),
        ({"offset": -1}, "offset"),
        ({"sort": "title"}, "sort"),
        ({"status": "archived"}, "status"),
    ],
)
async def test_invalid_query_params(client, auth, users, params, field):
    resp = await client.get("/api/documents", headers=auth(users["riya"]), params=params)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    assert field in resp.json()["error"]["fields"]


async def test_get_own_document_with_events(client, auth, users, upload):
    doc = (await upload(users["sam"])).json()
    resp = await client.get(f"/api/documents/{doc['id']}", headers=auth(users["sam"]))
    assert resp.status_code == 200
    body = resp.json()
    assert body["file"] == doc["file"]
    assert [(e["event"], e["from_status"], e["to_status"]) for e in body["events"]] == [
        ("submitted", None, "pending")
    ]
    assert body["events"][0]["actor"]["id"] == str(users["sam"].id)


async def test_reviewer_gets_any_document(client, auth, users, docs):
    resp = await client.get(f"/api/documents/{docs[1].id}", headers=auth(users["riya"]))
    assert resp.status_code == 200
    assert resp.json()["decided_by"]["id"] == str(users["riya"].id)


async def test_submitter_gets_404_for_others_document(client, auth, users, docs):
    resp = await client.get(f"/api/documents/{docs[1].id}", headers=auth(users["sam"]))
    assert resp.status_code == 404
    assert resp.json()["error"] == {
        "code": "NOT_FOUND",
        "message": "Document not found",
        "fields": {},
    }


async def test_unknown_document_is_404(client, auth, users):
    resp = await client.get(f"/api/documents/{uuid.uuid4()}", headers=auth(users["riya"]))
    assert resp.status_code == 404


@pytest.mark.parametrize("suffix", ["", "/file"])
async def test_malformed_id_is_404(client, auth, users, suffix):
    resp = await client.get(f"/api/documents/not-a-uuid{suffix}", headers=auth(users["riya"]))
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


async def test_download_follows_ownership(client, auth, users, upload):
    content = b"%PDF-1.7 the real thing"
    doc = (await upload(users["sam"], content=content)).json()
    url = f"/api/documents/{doc['id']}/file"

    for name in ("sam", "riya"):
        resp = await client.get(url, headers=auth(users[name]))
        assert resp.status_code == 200
        assert resp.content == content
        assert hashlib.sha256(resp.content).hexdigest() == doc["file"]["sha256"]
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.headers["content-disposition"] == 'attachment; filename="report.pdf"'

    resp = await client.get(url, headers=auth(users["other"]))
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


async def test_download_non_ascii_filename(client, auth, users, upload):
    doc = (await upload(users["sam"], filename="résumé final.pdf")).json()
    resp = await client.get(f"/api/documents/{doc['id']}/file", headers=auth(users["sam"]))
    assert resp.headers["content-disposition"] == (
        "attachment; filename*=UTF-8''r%C3%A9sum%C3%A9%20final.pdf"
    )


async def test_download_document_without_file(client, auth, users, docs):
    resp = await client.get(f"/api/documents/{docs[0].id}/file", headers=auth(users["sam"]))
    assert resp.status_code == 404
    assert resp.json()["error"]["message"] == "File not found"
