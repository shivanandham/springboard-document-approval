from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlalchemy import select

from app import security
from app.config import settings
from app.models import RefreshToken


def assert_unauthenticated(resp, message=None):
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"
    if message:
        assert resp.json()["error"]["message"] == message


async def test_login_success(client, make_user, login):
    user = await make_user("submitter", email="sam@example.com")
    resp = await login("  SAM@example.com ")
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    claims = jwt.decode(body["access_token"], settings.jwt_secret, algorithms=["HS256"])
    assert claims["sub"] == str(user.id)
    assert claims["roles"] == ["submitter"]
    assert "document:create" in claims["perms"]
    cookie = resp.headers["set-cookie"]
    assert "refresh_token=" in cookie
    assert "HttpOnly" in cookie
    assert "Path=/api/auth" in cookie
    assert "SameSite=lax" in cookie
    assert "Secure" not in cookie


async def test_cookie_secure_setting(client, make_user, login, monkeypatch):
    monkeypatch.setattr(settings, "cookie_secure", True)
    await make_user("submitter", email="sam@example.com")
    assert "Secure" in (await login("sam@example.com")).headers["set-cookie"]
    assert "Secure" in (await client.post("/api/auth/logout")).headers["set-cookie"]


async def test_login_wrong_password(client, make_user, login):
    await make_user("submitter", email="sam@example.com")
    assert_unauthenticated(await login("sam@example.com", "nope"), "Invalid email or password")


async def test_login_unknown_email(client, login):
    assert_unauthenticated(await login("ghost@example.com"), "Invalid email or password")


async def test_login_inactive_user(client, make_user, login):
    await make_user("submitter", email="gone@example.com", is_active=False)
    assert_unauthenticated(await login("gone@example.com"), "Invalid email or password")


async def test_login_missing_fields(client):
    resp = await client.post("/api/auth/login", data={"username": "x@example.com"})
    assert resp.status_code == 400
    assert "password" in resp.json()["error"]["fields"]


async def test_inactive_user_with_valid_token(client, make_user, session, auth):
    user = await make_user("submitter")
    headers = auth(user)
    user.is_active = False
    await session.commit()
    assert_unauthenticated(await client.get("/api/auth/me", headers=headers))


async def test_expired_access_token(client, make_user):
    user = await make_user("submitter")
    token = jwt.encode(
        {"sub": str(user.id), "exp": datetime.now(UTC) - timedelta(seconds=1)},
        settings.jwt_secret,
        algorithm="HS256",
    )
    resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert_unauthenticated(resp, "Invalid or expired token")


async def test_tampered_token(client, make_user, auth):
    user = await make_user("submitter")
    header, payload, signature = auth(user)["Authorization"].split(".")
    tampered = f"{header}.{payload}.{signature[::-1]}"
    assert_unauthenticated(await client.get("/api/auth/me", headers={"Authorization": tampered}))


async def test_token_signed_with_other_secret(client, make_user):
    user = await make_user("submitter")
    token = jwt.encode(
        {"sub": str(user.id), "exp": datetime.now(UTC) + timedelta(minutes=5)},
        "x" * 64,
        algorithm="HS256",
    )
    resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert_unauthenticated(resp)


async def test_token_for_deleted_user(client, make_user, session, auth):
    user = await make_user("submitter")
    headers = auth(user)
    await session.delete(user)
    await session.commit()
    assert_unauthenticated(await client.get("/api/auth/me", headers=headers))


async def test_missing_token(client):
    assert_unauthenticated(await client.get("/api/auth/me"), "Not authenticated")


async def test_refresh_rotation(client, make_user, session, login):
    user = await make_user("submitter", email="sam@example.com")
    first = (await login("sam@example.com")).cookies["refresh_token"]

    resp = await client.post("/api/auth/refresh")
    assert resp.status_code == 200
    assert jwt.decode(resp.json()["access_token"], settings.jwt_secret, algorithms=["HS256"])
    second = client.cookies["refresh_token"]
    assert second != first

    tokens = list(
        await session.scalars(select(RefreshToken).where(RefreshToken.user_id == user.id))
    )
    assert len(tokens) == 2
    old, new = sorted(tokens, key=lambda t: t.revoked_at is None)
    assert old.revoked_at is not None and old.replaced_by_id == new.id
    assert new.revoked_at is None and new.family_id == old.family_id
    assert first not in {t.token_hash for t in tokens}  # only hashes are stored


async def test_reusing_old_refresh_token_revokes_family(client, make_user, session, login):
    user = await make_user("submitter", email="sam@example.com")
    first = (await login("sam@example.com")).cookies["refresh_token"]
    assert (await client.post("/api/auth/refresh")).status_code == 200
    current = client.cookies["refresh_token"]

    client.cookies.set("refresh_token", first, path="/api/auth")
    assert_unauthenticated(await client.post("/api/auth/refresh"), "Refresh token reuse detected")

    tokens = await session.scalars(select(RefreshToken).where(RefreshToken.user_id == user.id))
    assert all(t.revoked_at is not None for t in tokens)
    client.cookies.set("refresh_token", current, path="/api/auth")
    assert_unauthenticated(await client.post("/api/auth/refresh"))


async def test_refresh_without_cookie(client):
    assert_unauthenticated(await client.post("/api/auth/refresh"), "Missing refresh token")


async def test_refresh_with_unknown_token(client):
    client.cookies.set("refresh_token", "made-up", path="/api/auth")
    assert_unauthenticated(await client.post("/api/auth/refresh"), "Invalid refresh token")


async def test_refresh_with_expired_token(client, make_user, session, login):
    user = await make_user("submitter", email="sam@example.com")
    await login("sam@example.com")
    token = await session.scalar(select(RefreshToken).where(RefreshToken.user_id == user.id))
    token.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await session.commit()
    assert_unauthenticated(await client.post("/api/auth/refresh"), "Refresh token expired")


async def test_refresh_for_inactive_user(client, make_user, session, login):
    user = await make_user("submitter", email="sam@example.com")
    await login("sam@example.com")
    user.is_active = False
    await session.commit()
    assert_unauthenticated(await client.post("/api/auth/refresh"), "Invalid refresh token")


async def test_logout_revokes_token(client, make_user, session, login):
    user = await make_user("submitter", email="sam@example.com")
    token = (await login("sam@example.com")).cookies["refresh_token"]

    resp = await client.post("/api/auth/logout")
    assert resp.status_code == 204
    assert 'refresh_token=""' in resp.headers["set-cookie"]
    assert "refresh_token" not in client.cookies

    row = await session.scalar(select(RefreshToken).where(RefreshToken.user_id == user.id))
    assert row.revoked_at is not None
    client.cookies.set("refresh_token", token, path="/api/auth")
    assert_unauthenticated(await client.post("/api/auth/refresh"))


async def test_logout_without_cookie(client):
    assert (await client.post("/api/auth/logout")).status_code == 204


async def test_me_returns_permissions(client, make_user, auth):
    user = await make_user("reviewer", email="riya@example.com")
    resp = await client.get("/api/auth/me", headers=auth(user))
    assert resp.status_code == 200
    assert resp.json() == {
        "id": str(user.id),
        "email": "riya@example.com",
        "full_name": "Test User",
        "roles": ["reviewer"],
        "permissions": ["document:read_all", "document:review", "file:download_all"],
    }


async def test_me_merges_permissions_of_several_roles(client, make_user, auth):
    user = await make_user("submitter", "reviewer")
    resp = await client.get("/api/auth/me", headers=auth(user))
    assert resp.json()["roles"] == ["reviewer", "submitter"]
    assert len(resp.json()["permissions"]) == 6


@pytest.fixture
def clock(monkeypatch):
    # Skip argon2 so dozens of attempts stay fast; "wrong" is the only bad password here.
    monkeypatch.setattr(security, "verify_password", lambda password, _: password != "wrong")
    now = [1000.0]
    for limiter in (security.login_ip_limiter, security.login_account_limiter):
        monkeypatch.setattr(limiter, "clock", lambda: now[0])
    return now


def assert_rate_limited(resp, retry_after):
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "RATE_LIMITED"
    assert resp.json()["error"]["message"] == (
        f"Too many login attempts. Try again in {retry_after} seconds."
    )
    assert resp.headers["retry-after"] == str(retry_after)


async def test_login_rate_limit_per_account(login, make_user, clock):
    await make_user("submitter", email="sam@example.com")
    for _ in range(4):
        assert (await login("sam@example.com", "wrong")).status_code == 401
    assert (await login("SAM@example.com")).status_code == 200  # successes count too
    clock[0] += 15
    assert_rate_limited(await login("sam@example.com"), 45)
    assert (await login("someone-else@example.com")).status_code == 401


async def test_login_rate_limit_per_ip_across_emails(login, clock):
    for i in range(20):
        assert (await login(f"user{i}@example.com")).status_code == 401
    assert_rate_limited(await login("fresh@example.com"), 60)


async def test_login_rate_limit_window_expires(login, make_user, clock):
    await make_user("submitter", email="sam@example.com")
    for _ in range(5):
        await login("sam@example.com", "wrong")
    assert_rate_limited(await login("sam@example.com"), 60)
    clock[0] += 60
    assert (await login("sam@example.com")).status_code == 200


async def test_rate_limit_only_applies_to_login(client, login, make_user, auth, clock):
    user = await make_user("submitter")
    for _ in range(25):
        await login("sam@example.com", "wrong")
    assert (await client.get("/api/auth/me", headers=auth(user))).status_code == 200
    assert (await client.post("/api/auth/refresh")).status_code == 401
