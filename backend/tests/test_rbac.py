import json
import logging
import re
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import JsonFormatter, app

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


async def server_error(monkeypatch, headers=None):
    async def boom(*_):
        raise RuntimeError("kaboom")

    monkeypatch.setattr("sqlalchemy.ext.asyncio.AsyncSession.execute", boom)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.get("/api/health", headers=headers)


async def test_unhandled_error_uses_error_shape(monkeypatch):
    resp = await server_error(monkeypatch, {"X-Request-ID": "req-123"})
    assert resp.status_code == 500
    assert resp.headers["x-request-id"] == "req-123"
    assert resp.json() == {
        "error": {
            "code": "INTERNAL_ERROR",
            "message": "Something went wrong. Reference: req-123",
            "fields": {},
        }
    }


async def test_unhandled_error_is_logged_with_traceback(monkeypatch, caplog):
    await server_error(monkeypatch, {"X-Request-ID": "req-500"})
    (record,) = [r for r in caplog.records if r.levelname == "ERROR"]
    assert record.request_id == "req-500"
    line = json.loads(JsonFormatter().format(record))
    assert "Traceback" in line["exc_info"] and "RuntimeError: kaboom" in line["exc_info"]


async def test_request_id_is_generated(client):
    resp = await client.get("/api/health")
    assert re.fullmatch(r"[0-9a-f]{32}", resp.headers["x-request-id"])


@pytest.mark.parametrize(
    ("incoming", "kept"),
    [("abc-123.DEF_4", True), ("has spaces", False), ("x" * 65, False), ("", False)],
)
async def test_incoming_request_id_is_honoured_if_sane(client, incoming, kept):
    resp = await client.get("/api/health", headers={"X-Request-ID": incoming})
    assert (resp.headers["x-request-id"] == incoming) is kept


async def test_request_log_line(client, auth, make_user, login, caplog):
    user = await make_user("submitter", email="sam@example.com")
    caplog.set_level(logging.INFO, logger="docflow")
    token = (await login("sam@example.com")).json()["access_token"]
    resp = await client.get("/api/auth/me", headers=auth(user))

    lines = [json.loads(JsonFormatter().format(r)) for r in caplog.records if r.name == "docflow"]
    assert lines[-1] | {"time": None, "duration_ms": None} == {
        "time": None,
        "level": "INFO",
        "logger": "docflow",
        "message": "request",
        "method": "GET",
        "path": "/api/auth/me",
        "status": 200,
        "duration_ms": None,
        "request_id": resp.headers["x-request-id"],
        "user_id": str(user.id),
    }
    assert lines[-2]["path"] == "/api/auth/login" and lines[-2]["user_id"] == str(user.id)
    logged = caplog.text + "".join(map(json.dumps, lines))
    for secret in (token, auth(user)["Authorization"], "correct-horse-battery", "refresh_token"):
        assert secret not in logged
