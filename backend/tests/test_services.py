import pytest

from app import services
from app.models import DocumentStatus
from app.schemas import AppError


@pytest.mark.parametrize(
    ("decision", "expected"),
    [("approve", DocumentStatus.approved), ("reject", DocumentStatus.rejected)],
)
def test_pending_can_be_decided(decision, expected):
    assert services.transition(DocumentStatus.pending, decision) == expected


@pytest.mark.parametrize("status", [DocumentStatus.approved, DocumentStatus.rejected])
@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_decided_documents_are_final(status, decision):
    with pytest.raises(AppError) as exc:
        services.transition(status, decision)
    assert (exc.value.status, exc.value.code) == (409, "INVALID_TRANSITION")


def test_every_target_state_is_terminal():
    targets = {t for moves in services.TRANSITIONS.values() for t in moves.values()}
    assert targets == {DocumentStatus.approved, DocumentStatus.rejected}
    assert targets.isdisjoint(services.TRANSITIONS)


async def test_decide_validates_comment_before_touching_the_row(session, make_user):
    riya = await make_user("reviewer")
    with pytest.raises(AppError) as exc:
        # The id doesn't exist: the comment check must fire first, without a DB lookup.
        await services.decide(session, riya, riya.id, "reject", "  ", 1)
    assert exc.value.code == "VALIDATION_ERROR"


async def test_decide_checks_ownership_before_state(session, make_user, make_document):
    both = await make_user("submitter", "reviewer")
    doc = await make_document(both, status=DocumentStatus.approved)
    with pytest.raises(AppError) as exc:
        await services.decide(session, both, doc.id, "approve", None, doc.version)
    assert exc.value.code == "FORBIDDEN"


async def test_decide_checks_state_before_version(session, make_user, make_document):
    sam, riya = await make_user("submitter"), await make_user("reviewer")
    doc = await make_document(sam, status=DocumentStatus.approved, decided_by=riya)
    with pytest.raises(AppError) as exc:
        await services.decide(session, riya, doc.id, "reject", "late", doc.version + 5)
    assert exc.value.code == "INVALID_TRANSITION"


async def test_decide_updates_document(session, make_user, make_document):
    sam, riya = await make_user("submitter"), await make_user("reviewer")
    doc = await make_document(sam)
    decided = await services.decide(session, riya, doc.id, "reject", " Blurry scan ", 1)
    assert decided.status == DocumentStatus.rejected
    assert decided.decision_comment == "Blurry scan"
    assert decided.decided_by.id == riya.id
    assert decided.version == 2


async def test_list_scopes_to_owner_without_read_all(session, make_user, make_document):
    sam, other = await make_user("submitter"), await make_user("submitter")
    await make_document(sam)
    await make_document(other)
    items, total = await services.list_documents(session, sam, None, 10, 0, "-created_at")
    assert total == 1 and items[0].submitter_id == sam.id
