from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.config import settings
from app.db import SessionLocal
from app.models import Role, User, user_roles
from app.security import hash_password


async def reseed_users() -> None:
    """Idempotently restore the seed users, their roles and their passwords from env."""
    seeds = [
        ("sam.submitter@docflow.dev", "Sam Carter", "submitter", settings.seed_submitter_password),
        ("riya.reviewer@docflow.dev", "Riya Menon", "reviewer", settings.seed_reviewer_password),
    ]
    async with SessionLocal() as session:
        for email, full_name, role, password in seeds:
            values = {
                "full_name": full_name,
                "password_hash": hash_password(password),
                "is_active": True,
            }
            user_id = await session.scalar(
                insert(User)
                .values(email=email, **values)
                .on_conflict_do_update(
                    index_elements=[User.email], set_={**values, "updated_at": func.now()}
                )
                .returning(User.id)
            )
            role_id = select(Role.id).where(Role.name == role).scalar_subquery()
            await session.execute(
                insert(user_roles).values(user_id=user_id, role_id=role_id).on_conflict_do_nothing()
            )
        await session.commit()
