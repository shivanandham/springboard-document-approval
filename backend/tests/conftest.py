import shutil
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from app.config import settings

# Point the app at the test database and a throwaway storage dir before anything binds to them.
settings.database_url = settings.test_database_url
settings.storage_dir = Path(tempfile.mkdtemp(prefix="docflow-test-"))

from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app import security  # noqa: E402
from app.db import engine, get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Document, DocumentStatus, Role, User  # noqa: E402
from app.security import create_access_token, hash_password  # noqa: E402

PASSWORD = "correct-horse-battery"
PASSWORD_HASH = hash_password(PASSWORD)
ALEMBIC = Config("alembic.ini")


@pytest.fixture(scope="session", autouse=True)
def database():
    command.downgrade(ALEMBIC, "base")
    command.upgrade(ALEMBIC, "head")
    yield
    shutil.rmtree(settings.storage_dir, ignore_errors=True)


@pytest.fixture(autouse=True)
def reset_rate_limits():
    security.login_ip_limiter.reset()
    security.login_account_limiter.reset()


@pytest.fixture
async def connection():
    async with engine.connect() as conn:
        transaction = await conn.begin()
        yield conn
        await transaction.rollback()


def _session(conn) -> AsyncSession:
    return AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)


@pytest.fixture
async def session(connection):
    async with _session(connection) as s:
        yield s


@pytest.fixture
async def client(connection):
    async def override():
        async with _session(connection) as s:
            yield s

    app.dependency_overrides[get_session] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def make_user(session):
    async def factory(*roles: str, email: str | None = None, is_active: bool = True) -> User:
        user = User(
            email=email or f"user-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Test User",
            password_hash=PASSWORD_HASH,
            is_active=is_active,
            roles=list(await session.scalars(select(Role).where(Role.name.in_(roles)))),
        )
        session.add(user)
        await session.commit()
        return user

    return factory


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user)}"}


@pytest.fixture
def auth():
    return _auth


@pytest.fixture
def login(client):
    async def post(email: str, password: str = PASSWORD):
        return await client.post("/api/auth/login", data={"username": email, "password": password})

    return post


@pytest.fixture
def make_document(session):
    async def factory(
        submitter: User,
        *,
        title: str = "Quarterly report",
        status: DocumentStatus = DocumentStatus.pending,
        decided_by: User | None = None,
        created_at: datetime | None = None,
    ) -> Document:
        doc = Document(submitter_id=submitter.id, title=title, status=status)
        if status != DocumentStatus.pending:
            doc.decided_by_id = (decided_by or submitter).id
            doc.decided_at = datetime.now(UTC)
            doc.decision_comment = "Needs another pass" if status == "rejected" else None
        if created_at:
            doc.created_at = created_at
        session.add(doc)
        await session.commit()
        return doc

    return factory


@pytest.fixture
def upload(client):
    async def post(
        user: User,
        *,
        title: str | None = "Quarterly report",
        content: bytes = b"%PDF-1.7 quarterly numbers",
        filename: str | None = "report.pdf",
        description: str | None = None,
    ):
        data = {"title": title, "description": description}
        data = {k: v for k, v in data.items() if v is not None}
        files = {"file": (filename, content, "application/octet-stream")} if filename else None
        return await client.post("/api/documents", headers=_auth(user), data=data, files=files)

    return post
