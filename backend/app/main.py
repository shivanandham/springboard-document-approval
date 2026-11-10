from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app import services
from app.config import settings
from app.db import SessionDep, engine
from app.routers import auth, documents
from app.schemas import AppError

HTTP_CODES = {401: "UNAUTHENTICATED", 403: "FORBIDDEN", 404: "NOT_FOUND", 409: "CONFLICT"}
MULTIPART_OVERHEAD = 1024 * 1024
UPLOAD_ROUTE = "POST /api/documents"


class UploadSizeLimit:
    """Rejects oversized uploads before the multipart body is spooled. The exact limit is
    still enforced while streaming in services.create_document."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or f"{scope['method']} {scope['path']}" != UPLOAD_ROUTE:
            return await self.app(scope, receive, send)

        cap = settings.max_upload_mb * 1024 * 1024 + MULTIPART_OVERHEAD
        length = dict(scope["headers"]).get(b"content-length", b"")
        if length.isdigit() and int(length) > cap:
            error = services.file_too_large()
            return await _error(413, error.code, error.message, error.fields)(scope, receive, send)

        received = 0

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if received > cap:
                raise services.file_too_large()
            return message

        await self.app(scope, counting_receive, send)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="DocFlow API", lifespan=lifespan)
    app.add_middleware(UploadSizeLimit)
    app.add_middleware(  # added last so it wraps everything, including early 413s
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],
    )

    app.include_router(auth.router)
    app.include_router(documents.router)

    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError) -> JSONResponse:
        return _error(exc.status, exc.code, exc.message, exc.fields, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # A malformed path id can't match anything, so treat it like an unknown one.
        if any(e["loc"][:1] == ("path",) for e in exc.errors()):
            return _error(404, "NOT_FOUND", "Not found")
        fields = {str(e["loc"][-1]): e["msg"] for e in exc.errors() if e["loc"]}
        return _error(400, "VALIDATION_ERROR", "Invalid request", fields)

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        return _error(exc.status_code, HTTP_CODES.get(exc.status_code, "HTTP_ERROR"), exc.detail)

    @app.exception_handler(Exception)
    async def unhandled_error(_: Request, __: Exception) -> JSONResponse:
        return _error(500, "INTERNAL_ERROR", "Something went wrong")

    @app.get("/api/health", summary="Health check (includes the database)", tags=["health"])
    async def health(session: SessionDep) -> dict[str, str]:
        await session.execute(text("SELECT 1"))
        return {"status": "ok"}

    return app


def _error(
    status: int,
    code: str,
    message: str,
    fields: dict | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = {"error": {"code": code, "message": message, "fields": fields or {}}}
    return JSONResponse(body, status_code=status, headers=headers)


app = create_app()
