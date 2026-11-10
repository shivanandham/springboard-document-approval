import shutil
import tempfile
import uuid
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

from app.db import engine, get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Role, User  # noqa: E402
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


def auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user)}"}
