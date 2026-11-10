from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response
from fastapi.security import OAuth2PasswordRequestForm

from app import security
from app.config import settings
from app.db import SessionDep
from app.models import User
from app.schemas import ErrorOut, MeOut, TokenOut

COOKIE = "refresh_token"
COOKIE_PATH = "/api/auth"

router = APIRouter(prefix="/api/auth", tags=["auth"], responses={401: {"model": ErrorOut}})
RefreshCookie = Annotated[str | None, Cookie(alias=COOKIE)]


def _tokens(response: Response, user: User, refresh_token: str) -> TokenOut:
    response.set_cookie(
        COOKIE,
        refresh_token,
        max_age=settings.refresh_token_ttl_days * 86400,
        path=COOKIE_PATH,
        httponly=True,
        samesite="lax",
    )
    return TokenOut(access_token=security.create_access_token(user))


@router.post("/login", summary="Log in with email and password")
async def login(
    response: Response,
    session: SessionDep,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> TokenOut:
    """Returns an access token and sets a rotating refresh token as an httpOnly cookie."""
    user = await security.authenticate(session, form.username, form.password)
    refresh_token, _ = await security.issue_refresh_token(session, user.id)
    await session.commit()
    return _tokens(response, user, refresh_token)


@router.post("/refresh", summary="Exchange the refresh cookie for a new access token")
async def refresh(response: Response, session: SessionDep, token: RefreshCookie = None) -> TokenOut:
    """Rotates the refresh token. Reusing a spent token revokes every token in its family."""
    if not token:
        raise security.unauthenticated("Missing refresh token")
    user, refresh_token = await security.rotate_refresh_token(session, token)
    return _tokens(response, user, refresh_token)


@router.post("/logout", status_code=204, summary="Revoke the refresh token and clear the cookie")
async def logout(response: Response, session: SessionDep, token: RefreshCookie = None) -> None:
    if token:
        await security.revoke_refresh_token(session, token)
    response.delete_cookie(COOKIE, path=COOKIE_PATH, httponly=True, samesite="lax")


@router.get("/me", summary="The current user with their roles and permissions")
async def me(user: security.CurrentUser) -> MeOut:
    return MeOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        roles=sorted(r.name for r in user.roles),
        permissions=sorted(user.permissions),
    )
