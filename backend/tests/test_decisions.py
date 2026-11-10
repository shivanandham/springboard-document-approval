import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import Document, DocumentEvent


@pytest.fixture
async def sam(make_user):
    return await make_user("submitter")


@pytest.fixture
async def riya(make_user):
    return await make_user("reviewer")


@pytest.fixture
async def doc(sam, make_document):
    return await make_document(sam)


@pytest.fixture
def decide(client, auth):
    async def post(user, document_id, decision="approve", comment=None, version=1):
        return await client.post(
            f"/api/documents/{document_id}/decision",
            headers=auth(user),
            json={"decision": decision, "comment": comment, "version": version},
        )

    return post


def assert_error(resp, status, code):
    assert resp.status_code == status, resp.text
    assert resp.json()["error"]["code"] == code
    return resp.json()["error"]


async def test_approve(decide, riya, doc):
    resp = await decide(riya, doc.id)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "approved"
    assert body["version"] == 2
    assert body["decision_comment"] is None


async def test_approve_with_comment(decide, riya, doc):
    resp = await decide(riya, doc.id, comment="  Looks good  ")
    assert resp.json()["decision_comment"] == "Looks good"


async def test_reject_with_comment(decide, riya, doc):
    resp = await decide(riya, doc.id, "reject", "Missing signatures")
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"
    assert resp.json()["decision_comment"] == "Missing signatures"


@pytest.mark.parametrize("comment", [None, "", "   "])
async def test_reject_without_comment(decide, riya, doc, comment):
    error = assert_error(await decide(riya, doc.id, "reject", comment), 400, "VALIDATION_ERROR")
    assert "comment" in error["fields"]


async def test_decide_already_decided(decide, riya, make_user, doc):
    assert (await decide(riya, doc.id)).status_code == 200
    raj = await make_user("reviewer")
    error = assert_error(
        await decide(raj, doc.id, "reject", "No", version=2), 409, "INVALID_TRANSITION"
    )
    assert error["message"] == "This document has already been approved"


async def test_stale_version(decide, riya, doc, session):
    doc.version = 3  # someone else's edit bumped the version
    await session.commit()
    assert_error(await decide(riya, doc.id, version=2), 409, "CONFLICT")


async def test_decide_own_document(decide, make_user, make_document):
    both = await make_user("submitter", "reviewer")
    own = await make_document(both)
    assert_error(await decide(both, own.id), 403, "FORBIDDEN")


async def test_submitter_cannot_decide(decide, make_user, doc):
    other = await make_user("submitter")
    assert_error(await decide(other, doc.id), 403, "FORBIDDEN")


@pytest.mark.parametrize("document_id", [uuid.uuid4(), "not-a-uuid"])
async def test_unknown_document(decide, riya, document_id):
    assert_error(await decide(riya, document_id), 404, "NOT_FOUND")


@pytest.mark.parametrize(
    "body",
    [
        {"decision": "maybe", "version": 1},
        {"decision": "approve"},
        {"decision": "approve", "version": 0},
        {"version": 1},
    ],
)
async def test_invalid_body(client, auth, riya, doc, body):
    resp = await client.post(f"/api/documents/{doc.id}/decision", headers=auth(riya), json=body)
    assert_error(resp, 400, "VALIDATION_ERROR")


async def test_event_trail_records_transition(client, auth, decide, riya, sam, upload):
    created = (await upload(sam)).json()
    await decide(riya, created["id"], "reject", "Wrong quarter")
    resp = await client.get(f"/api/documents/{created['id']}", headers=auth(sam))
    events = sorted(resp.json()["events"], key=lambda e: e["event"] != "submitted")
    assert [(e["event"], e["from_status"], e["to_status"], e["comment"]) for e in events] == [
        ("submitted", None, "pending", None),
        ("rejected", "pending", "rejected", "Wrong quarter"),
    ]
    assert events[1]["actor"]["id"] == str(riya.id)


async def test_decided_by_and_decided_at_are_set(decide, riya, doc, session):
    before = datetime.now(UTC)
    body = (await decide(riya, doc.id)).json()
    assert body["decided_by"] == {
        "id": str(riya.id),
        "full_name": riya.full_name,
        "email": riya.email,
    }
    assert before - timedelta(seconds=5) <= datetime.fromisoformat(body["decided_at"])
    row = await session.scalar(
        select(Document).where(Document.id == doc.id).execution_options(populate_existing=True)
    )
    assert row.decided_by_id == riya.id and row.decided_at is not None


async def test_failed_decision_writes_no_event(decide, riya, doc, session):
    await decide(riya, doc.id, version=9)
    events = await session.scalars(select(DocumentEvent).where(DocumentEvent.document_id == doc.id))
    assert list(events) == []
