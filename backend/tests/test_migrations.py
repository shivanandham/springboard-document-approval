import asyncio

from alembic import command
from alembic.config import Config
from sqlalchemy import func, select

from app.config import settings
from app.db import engine
from app.models import Permission, Role, User
from app.services import reseed_users

ALEMBIC = Config("alembic.ini")
SEED_EMAILS = {"sam.submitter@docflow.dev", "riya.reviewer@docflow.dev"}


async def test_upgrade_downgrade_upgrade():
    for step, revision in [("downgrade", "base"), ("upgrade", "head"), ("downgrade", "0001")]:
        await asyncio.to_thread(getattr(command, step), ALEMBIC, revision)
    await asyncio.to_thread(command.upgrade, ALEMBIC, "head")
    # Recreated enum types get new OIDs, so drop pooled connections that cached the old ones.
    await engine.dispose()


async def test_seed_creates_roles_permissions_and_users(session):
    roles = {r.name: r for r in await session.scalars(select(Role))}
    assert set(roles) == {"submitter", "reviewer"}
    assert {p.code for p in roles["submitter"].permissions} == {
        "document:create",
        "document:read_own",
        "file:download_own",
    }
    assert {p.code for p in roles["reviewer"].permissions} == {
        "document:read_all",
        "document:review",
        "file:download_all",
    }
    assert await session.scalar(select(func.count()).select_from(Permission)) == 6

    users = {u.email: u for u in await session.scalars(select(User))}
    assert SEED_EMAILS <= set(users)
    assert [r.name for r in users["sam.submitter@docflow.dev"].roles] == ["submitter"]
    assert users["riya.reviewer@docflow.dev"].full_name == "Riya Menon"


async def test_reseed_is_idempotent(login):
    await reseed_users()
    await reseed_users()
    for email, password in [
        ("sam.submitter@docflow.dev", settings.seed_submitter_password),
        ("riya.reviewer@docflow.dev", settings.seed_reviewer_password),
    ]:
        assert (await login(email, password)).status_code == 200
