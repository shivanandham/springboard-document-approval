import json
import logging
import re
import sys
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.datastructures import Headers, MutableHeaders
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
REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")
LOG_FIELDS = ("method", "path", "status", "duration_ms", "request_id", "user_id")

logger = logging.getLogger("docflow")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        entry |= {f: getattr(record, f) for f in LOG_FIELDS if hasattr(record, f)}
        if record.exc_info:
            entry["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=settings.log_level.upper(), handlers=[handler], force=True)


class RequestContext:
    """Assigns a request id (echoed as X-Request-ID) and logs one line per request.
    Only method, path, status, timing and ids are logged: never headers, bodies or tokens."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        incoming = Headers(scope=scope).get("x-request-id", "")
        request_id = incoming if REQUEST_ID.fullmatch(incoming) else uuid.uuid4().hex
        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        status, start = 500, time.perf_counter()

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message).append("X-Request-ID", request_id)
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            logger.info(
                "request",
                extra={
                    "method": scope["method"],
                    "path": scope["path"],
                    "status": status,
                    "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                    "request_id": request_id,
                    "user_id": state.get("user_id"),
                },
            )


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
    configure_logging()
    app = FastAPI(title="DocFlow API", lifespan=lifespan)
    app.add_middleware(UploadSizeLimit)
    app.add_middleware(  # wraps the upload check so early 413s get CORS headers
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition", "X-Request-ID"],
    )
    app.add_middleware(RequestContext)

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
    async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
        # Runs outside the middleware stack, so it sets X-Request-ID itself.
        request_id = request.state.request_id
        logger.error("unhandled error", exc_info=exc, extra={"request_id": request_id})
        message = f"Something went wrong. Reference: {request_id}"
        return _error(500, "INTERNAL_ERROR", message, headers={"X-Request-ID": request_id})

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
