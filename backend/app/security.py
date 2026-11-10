import hashlib
import math
import secrets
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import SessionDep
from app.models import RefreshToken, User
from app.schemas import AppError

ALGORITHM = "HS256"
_hasher = PasswordHasher()
_dummy_hash = _hasher.hash("timing-equaliser")
_bearer = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def unauthenticated(message: str = "Not authenticated") -> AppError:
    return AppError(401, "UNAUTHENTICATED", message)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


async def authenticate(session: AsyncSession, email: str, password: str) -> User:
    user = await session.scalar(select(User).where(User.email == email.strip().lower()))
    # Verify against a dummy hash for unknown emails so response timing doesn't leak them.
    valid = verify_password(password, user.password_hash if user else _dummy_hash)
    if not (user and valid and user.is_active):
        raise unauthenticated("Invalid email or password")
    return user


class RateLimiter:
    """In-memory sliding window. Per process, which is fine for the single uvicorn worker."""

    def __init__(self, limit: int, window: float = 60, clock: Callable[[], float] = time.monotonic):
        self.limit, self.window, self.clock = limit, window, clock
        self.hits: defaultdict[str, deque[float]] = defaultdict(deque)

    def hit(self, key: str) -> int:
        """Record an attempt. Returns 0 if allowed, else the seconds until the next slot."""
        now, hits = self.clock(), self.hits[key]
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            return max(1, math.ceil(hits[0] + self.window - now))
        hits.append(now)
        return 0

    def reset(self) -> None:
        self.hits.clear()


login_ip_limiter = RateLimiter(20)
login_account_limiter = RateLimiter(5)


def check_login_rate(client_ip: str, email: str) -> None:
    for limiter, key in (
        (login_ip_limiter, client_ip),
        (login_account_limiter, f"{client_ip}|{email.strip().lower()}"),
    ):
        if wait := limiter.hit(key):
            raise AppError(
                429,
                "RATE_LIMITED",
                f"Too many login attempts. Try again in {wait} seconds.",
                headers={"Retry-After": str(wait)},
            )


def create_access_token(user: User) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": str(user.id),
        "roles": sorted(r.name for r in user.roles),
        "perms": sorted(user.permissions),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_ttl_minutes),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=ALGORITHM)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def issue_refresh_token(
    session: AsyncSession, user_id: uuid.UUID, family_id: uuid.UUID | None = None
) -> tuple[str, RefreshToken]:
    token = secrets.token_urlsafe(32)
    row = RefreshToken(
        user_id=user_id,
        token_hash=_hash_token(token),
        family_id=family_id or uuid.uuid4(),
        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_ttl_days),
    )
    session.add(row)
    await session.flush()
    return token, row


async def rotate_refresh_token(session: AsyncSession, token: str) -> tuple[User, str]:
    """Swap a valid refresh token for a new one; reuse of a spent token revokes its family."""
    row = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == _hash_token(token)).with_for_update()
    )
    if row is None:
        raise unauthenticated("Invalid refresh token")
    if row.revoked_at is not None:
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == row.family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=func.now())
        )
        await session.commit()
        raise unauthenticated("Refresh token reuse detected")
    if row.expires_at <= datetime.now(UTC):
        raise unauthenticated("Refresh token expired")
    user = await session.get(User, row.user_id)
    if user is None or not user.is_active:
        raise unauthenticated("Invalid refresh token")

    new_token, new_row = await issue_refresh_token(session, user.id, row.family_id)
    row.revoked_at = datetime.now(UTC)
    row.replaced_by_id = new_row.id
    await session.commit()
    return user, new_token


async def revoke_refresh_token(session: AsyncSession, token: str) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == _hash_token(token), RefreshToken.revoked_at.is_(None))
        .values(revoked_at=func.now())
    )
    await session.commit()


async def get_current_user(
    request: Request, session: SessionDep, token: Annotated[str | None, Depends(_bearer)]
) -> User:
    if not token:
        raise unauthenticated()
    try:
        claims = jwt.decode(
            token, settings.jwt_secret, algorithms=[ALGORITHM], options={"require": ["exp", "sub"]}
        )
        user_id = uuid.UUID(claims["sub"])
    except (jwt.InvalidTokenError, ValueError) as exc:
        raise unauthenticated("Invalid or expired token") from exc
    # Roles and permissions are reloaded from the DB on every request; token claims are hints only.
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthenticated()
    request.state.user_id = str(user.id)  # for the request log line
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_permission(*codes: str):
    """Dependency that passes if the user holds any of the given permissions."""

    async def dependency(user: CurrentUser) -> User:
        if user.permissions.isdisjoint(codes):
            raise AppError(403, "FORBIDDEN", "You do not have permission to do this")
        return user

    return Depends(dependency)
