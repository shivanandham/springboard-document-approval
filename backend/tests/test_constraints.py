import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError


@pytest.fixture
async def doc(make_user, make_document):
    return await make_document(await make_user("submitter"))


@pytest.fixture
async def reviewer(make_user):
    return await make_user("reviewer")


async def violates(connection, sql: str, error=IntegrityError, **params):
    with pytest.raises(error):
        async with connection.begin_nested():
            await connection.execute(text(sql), params)


async def test_pending_cannot_have_decision(connection, doc, reviewer):
    await violates(
        connection,
        "UPDATE documents SET decided_by_id = :r, decided_at = now() WHERE id = :id",
        r=reviewer.id,
        id=doc.id,
    )


@pytest.mark.parametrize("status", ["approved", "rejected"])
async def test_decided_requires_decider_and_time(connection, doc, status):
    await violates(
        connection,
        f"UPDATE documents SET status = '{status}', decision_comment = 'x' WHERE id = :id",
        id=doc.id,
    )


async def test_decided_requires_both_decider_and_time(connection, doc, reviewer):
    await violates(
        connection,
        "UPDATE documents SET status = 'approved', decided_by_id = :r WHERE id = :id",
        r=reviewer.id,
        id=doc.id,
    )


async def test_rejected_requires_comment(connection, doc, reviewer):
    await violates(
        connection,
        "UPDATE documents SET status = 'rejected', decided_by_id = :r, decided_at = now()"
        " WHERE id = :id",
        r=reviewer.id,
        id=doc.id,
    )


async def test_valid_decision_passes(connection, doc, reviewer):
    await connection.execute(
        text(
            "UPDATE documents SET status = 'rejected', decided_by_id = :r, decided_at = now(),"
            " decision_comment = 'Unsigned' WHERE id = :id"
        ),
        {"r": reviewer.id, "id": doc.id},
    )


async def test_unknown_status_rejected(connection, doc):
    await violates(
        connection, "UPDATE documents SET status = 'archived' WHERE id = :id", DBAPIError, id=doc.id
    )


async def test_title_cannot_be_empty(connection, doc):
    await violates(connection, "UPDATE documents SET title = '' WHERE id = :id", id=doc.id)


async def test_version_must_be_positive(connection, doc):
    await violates(connection, "UPDATE documents SET version = 0 WHERE id = :id", id=doc.id)


async def test_file_cannot_be_empty(connection, doc):
    await violates(
        connection,
        "INSERT INTO document_files (document_id, storage_key, original_name, content_type,"
        " size_bytes, sha256) VALUES (:id, 'k', 'a.txt', 'text/plain', 0, 'x')",
        id=doc.id,
    )


async def test_email_is_unique(connection, reviewer):
    await violates(
        connection,
        "INSERT INTO users (email, full_name, password_hash) VALUES (:email, 'Dup', 'x')",
        email=reviewer.email,
    )


async def test_email_is_lowercase(connection):
    await violates(
        connection,
        "INSERT INTO users (email, full_name, password_hash) VALUES ('Sam@X.com', 'Sam', 'x')",
    )


async def test_submitter_must_exist(connection):
    await violates(
        connection,
        "INSERT INTO documents (submitter_id, title) VALUES (gen_random_uuid(), 'Orphan')",
    )
