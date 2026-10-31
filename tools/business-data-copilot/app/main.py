"""Authenticated FastAPI surface for the Business Data Copilot."""

from __future__ import annotations

import asyncio
import importlib
import logging
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from alpha_core.agent import AgentIdentity
from alpha_core.auth import InvalidCsrfToken
from alpha_app.agent_hub import RATE_LIMITER
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .demo import build_demo_frame, demo_csv_bytes
from .ingest import MAX_UPLOAD_BYTES, UploadRejected, parse_upload
from .models import ConfirmSchema, QueryRequest, QueryResponse
from .planner import CopilotClarification, CopilotUnsupported
from .service import CopilotService, QueryTimedOut, VerificationFailed
from .storage import CopilotStore, DatasetAccessDenied, DatasetExpired, DatasetUnavailable

ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = Path(os.getenv("COPILOT_DATA_ROOT", str(ROOT / "instance" / "workspaces")))
STORE = CopilotStore(DATA_ROOT)
SERVICE = CopilotService(STORE)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    STORE.purge_expired()
    yield


app = FastAPI(title="Business Data Copilot", version="1.0.0", lifespan=lifespan)


class _UploadBodyTooLarge(Exception):
    pass


class UploadBodyLimit:
    """Stop oversized multipart bodies before Starlette spools them to temporary files."""

    def __init__(self, application: ASGIApp, *, max_bytes: int) -> None:
        self.application = application
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http" or scope.get("path") != "/api/upload" or scope.get("method") != "POST":
            await self.application(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")
        if content_length:
            try:
                if int(content_length) > self.max_bytes:
                    response = JSONResponse(status_code=413, content={"detail": "Upload request is too large."})
                    await response(scope, receive, send)
                    return
            except ValueError:
                response = JSONResponse(status_code=400, content={"detail": "Invalid upload size header."})
                await response(scope, receive, send)
                return

        received = 0

        async def bounded_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _UploadBodyTooLarge
            return message

        try:
            await self.application(scope, bounded_receive, send)
        except _UploadBodyTooLarge:
            response = JSONResponse(status_code=413, content={"detail": "Upload request is too large."})
            await response(scope, receive, send)


app.add_middleware(UploadBodyLimit, max_bytes=MAX_UPLOAD_BYTES + 262_144)


def _knowledge_module() -> Any:
    return importlib.import_module("tools.enterprise-knowledge-assistant.app.main")


def authenticated_user(request: Request) -> dict[str, Any]:
    return _knowledge_module().current_user(request)


def identity_for(user: dict[str, Any]) -> AgentIdentity:
    return AgentIdentity(
        user_id=str(user["id"]),
        roles=frozenset({str(user["role"])}),
        workspace_id=str(user.get("workspace_id") or user["id"]),
        groups=frozenset(str(group) for group in user.get("groups", [])),
        active=True,
    )


def csrf_user(
    request: Request,
    user: dict[str, Any] = Depends(authenticated_user),
) -> dict[str, Any]:
    token = request.headers.get("X-CSRF-Token", "")
    if not token:
        raise HTTPException(403, "A session CSRF token is required.")
    try:
        _knowledge_module()._session_codec().verify_csrf(token, str(user["id"]))
    except (InvalidCsrfToken, ValueError) as exc:
        raise HTTPException(403, "The session CSRF token is invalid or expired.") from exc
    RATE_LIMITER.check(str(user["id"]))
    return user


def _dataset_identity(user: dict[str, Any]) -> AgentIdentity:
    identity = identity_for(user)
    if not identity.active or not identity.roles.intersection({"employee", "admin"}):
        raise HTTPException(403, "This account cannot use the Business Data Copilot.")
    return identity


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "data": "SYNTHETIC demo and user-owned uploads"}


@app.get("/")
def home() -> RedirectResponse:
    return RedirectResponse("/", status_code=303)


@app.get("/api/csrf")
def csrf_token(user: dict[str, Any] = Depends(authenticated_user)) -> dict[str, str]:
    return {"csrf_token": _knowledge_module()._session_codec().issue_csrf(str(user["id"]))}


@app.post("/api/upload")
async def upload(
    file: UploadFile = File(...),
    user: dict[str, Any] = Depends(csrf_user),
) -> dict[str, Any]:
    try:
        content = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(content) > MAX_UPLOAD_BYTES:
            raise UploadRejected("Uploads are limited to 10 MB.")
        filename = file.filename or ""
        frame = await asyncio.to_thread(parse_upload, filename, content)
        profile = await asyncio.to_thread(
            STORE.stage_frame, _dataset_identity(user), frame, content=content,
            filename_label=filename or "uploaded file", data_label="USER_UPLOADED",
        )
        return profile.model_dump(mode="json")
    except UploadRejected as exc:
        raise HTTPException(400, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    finally:
        await file.close()


@app.post("/api/demo")
def stage_demo(user: dict[str, Any] = Depends(csrf_user)) -> dict[str, Any]:
    frame = build_demo_frame()
    profile = STORE.stage_frame(
        _dataset_identity(user), frame, content=demo_csv_bytes(frame),
        filename_label="synthetic_demo_orders.csv", data_label="SYNTHETIC",
    )
    return profile.model_dump(mode="json")


@app.post("/api/confirm")
def confirm_schema(
    request: ConfirmSchema,
    user: dict[str, Any] = Depends(csrf_user),
) -> dict[str, Any]:
    try:
        return STORE.confirm(_dataset_identity(user), request)
    except DatasetAccessDenied as exc:
        raise HTTPException(403, str(exc)) from exc
    except DatasetUnavailable as exc:
        raise HTTPException(410, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/profile")
def profile(user: dict[str, Any] = Depends(authenticated_user)) -> dict[str, Any]:
    try:
        return STORE.profile(_dataset_identity(user), include_preview=True)
    except DatasetUnavailable as exc:
        raise HTTPException(404, str(exc)) from exc
    except DatasetExpired as exc:
        raise HTTPException(410, str(exc)) from exc


@app.post("/api/query", response_model=QueryResponse)
async def query(
    request: QueryRequest,
    user: dict[str, Any] = Depends(csrf_user),
) -> dict[str, Any]:
    identity = _dataset_identity(user)
    try:
        return await asyncio.to_thread(SERVICE.query, identity, request.question)
    except CopilotClarification as exc:
        raise HTTPException(422, str(exc)) from exc
    except CopilotUnsupported as exc:
        raise HTTPException(400, str(exc)) from exc
    except DatasetUnavailable as exc:
        raise HTTPException(404, str(exc)) from exc
    except DatasetExpired as exc:
        raise HTTPException(410, str(exc)) from exc
    except DatasetAccessDenied as exc:
        raise HTTPException(403, str(exc)) from exc
    except QueryTimedOut as exc:
        raise HTTPException(408, str(exc)) from exc
    except VerificationFailed as exc:
        raise HTTPException(502, str(exc)) from exc
    except Exception as exc:
        logger.warning("Copilot query failed with %s", type(exc).__name__)
        raise HTTPException(500, "The Copilot could not complete this question safely.") from exc


@app.get("/api/export/{query_id}.csv")
def export_csv(
    query_id: str,
    user: dict[str, Any] = Depends(authenticated_user),
) -> Response:
    if not re.fullmatch(r"[0-9a-f-]{36}", query_id):
        raise HTTPException(404, "The verified result was not found.")
    try:
        content = SERVICE.export_csv(_dataset_identity(user), query_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="copilot-query-{query_id}.csv"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )
