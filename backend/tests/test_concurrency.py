import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal
from app.main import app
from app.models import Document, DocumentEvent, Role, User


@pytest.fixture
async def committed():
    """Real committed rows: the race needs separate connections, so no wrapping transaction."""
    async with SessionLocal() as session:
        roles = {r.name: r for r in await session.scalars(select(Role))}
        sam, riya, raj = (
            User(email=f"{name}@race.test", full_name=name, password_hash="x", roles=[roles[role]])
            for name, role in [("sam", "submitter"), ("riya", "reviewer"), ("raj", "reviewer")]
        )
        doc = Document(submitter=sam, title="Contested")
        session.add_all([sam, riya, raj, doc])
        await session.commit()
        yield session, doc, riya, raj
        await session.execute(delete(Document).where(Document.id == doc.id))
        await session.execute(delete(User).where(User.id.in_([sam.id, riya.id, raj.id])))
        await session.commit()


async def test_two_reviewers_decide_at_once(committed, auth, monkeypatch):
    session, doc, riya, raj = committed
    commit = AsyncSession.commit

    async def slow_commit(self):
        # Widen the read-to-write window so an unlocked read would let both reviewers through.
        await asyncio.sleep(0.05)
        await commit(self)

    monkeypatch.setattr(AsyncSession, "commit", slow_commit)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:

        async def decide(user, decision):
            body = {"decision": decision, "comment": "Not this time", "version": 1}
            url = f"/api/documents/{doc.id}/decision"
            return await client.post(url, headers=auth(user), json=body)

        responses = await asyncio.gather(decide(riya, "approve"), decide(raj, "reject"))
    monkeypatch.undo()

    assert sorted(r.status_code for r in responses) == [200, 409]
    winner = next(r for r in responses if r.status_code == 200).json()
    loser = next(r for r in responses if r.status_code == 409).json()
    assert loser["error"]["code"] in {"INVALID_TRANSITION", "CONFLICT"}

    await session.refresh(doc)
    assert doc.status == winner["status"] and doc.version == 2
    events = await session.scalars(select(DocumentEvent).where(DocumentEvent.document_id == doc.id))
    assert len(list(events)) == 1
