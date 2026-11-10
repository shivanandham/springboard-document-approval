import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

ANON, SUBMITTER, REVIEWER, OTHER = "anonymous", "submitter", "reviewer", "other_submitter"

# (method, path, body kind) -> expected status per caller. {doc} is the submitter's document.
MATRIX = [
    ("GET", "/api/health", None, {ANON: 200, SUBMITTER: 200, REVIEWER: 200, OTHER: 200}),
    ("GET", "/api/auth/me", None, {ANON: 401, SUBMITTER: 200, REVIEWER: 200, OTHER: 200}),
    ("POST", "/api/documents", "upload", {ANON: 401, SUBMITTER: 201, REVIEWER: 403, OTHER: 201}),
    ("GET", "/api/documents", None, {ANON: 401, SUBMITTER: 200, REVIEWER: 200, OTHER: 200}),
    ("GET", "/api/documents/{doc}", None, {ANON: 401, SUBMITTER: 200, REVIEWER: 200, OTHER: 404}),
    (
        "GET",
        "/api/documents/{doc}/file",
        None,
        {ANON: 401, SUBMITTER: 200, REVIEWER: 200, OTHER: 404},
    ),
    (
        "POST",
        "/api/documents/{doc}/decision",
        "decision",
        {ANON: 401, SUBMITTER: 403, REVIEWER: 200, OTHER: 403},
    ),
]
CASES = [
    pytest.param(method, path, body, caller, status, id=f"{method} {path} as {caller}")
    for method, path, body, expected in MATRIX
    for caller, status in expected.items()
]
ERROR_CODES = {401: "UNAUTHENTICATED", 403: "FORBIDDEN", 404: "NOT_FOUND"}


@pytest.mark.parametrize(("method", "path", "body", "caller", "status"), CASES)
async def test_rbac_matrix(client, auth, make_user, upload, method, path, body, caller, status):
    users = {
        SUBMITTER: await make_user("submitter"),
        REVIEWER: await make_user("reviewer"),
        OTHER: await make_user("submitter"),
    }
    doc = (await upload(users[SUBMITTER])).json()
    headers = auth(users[caller]) if caller in users else {}
    kwargs = {}
    if body == "upload":
        kwargs = {"data": {"title": "Mine"}, "files": {"file": ("a.txt", b"hi", "text/plain")}}
    elif body == "decision":
        kwargs = {"json": {"decision": "approve", "version": 1}}

    resp = await client.request(method, path.format(doc=doc["id"]), headers=headers, **kwargs)

    assert resp.status_code == status, resp.text
    if status >= 400:
        assert resp.json()["error"]["code"] == ERROR_CODES[status]


async def test_unknown_route_uses_error_shape(client):
    resp = await client.get("/api/nope")
    assert resp.status_code == 404
    assert resp.json() == {"error": {"code": "NOT_FOUND", "message": "Not Found", "fields": {}}}


async def test_wrong_method_uses_error_shape(client):
    resp = await client.delete("/api/health")
    assert resp.status_code == 405
    assert set(resp.json()["error"]) == {"code", "message", "fields"}


async def test_malformed_json_uses_error_shape(client, auth, make_user):
    riya = await make_user("reviewer")
    resp = await client.post(
        f"/api/documents/{uuid.uuid4()}/decision",
        headers={**auth(riya), "Content-Type": "application/json"},
        content=b"{not json",
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_unhandled_error_uses_error_shape(monkeypatch):
    async def boom(*_):
        raise RuntimeError("kaboom")

    monkeypatch.setattr("sqlalchemy.ext.asyncio.AsyncSession.execute", boom)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/health")
    assert resp.status_code == 500
    assert resp.json() == {
        "error": {"code": "INTERNAL_ERROR", "message": "Something went wrong", "fields": {}}
    }
