"""Application factory; authentication covers documentation and streaming too."""

import hashlib
import hmac
import secrets
import threading
import time

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ..contracts import DomainError, ErrorResponse
from ..diagnostics import runtime_version, sign_diagnostics, validated_nonce
from ..forecast_policy import model_readiness
from ..runtime import Runtime
from ..store import Ledger
from .errors import public_error_details
from .routes import router
from .service import Observatory

SESSION_LIFETIME = 8 * 60 * 60


def _session_now():
    return time.monotonic()


def create_app(
    ledger: Ledger,
    runtime: Runtime,
    workspace_token: str,
    agent_token: str | None = None,
    console_origins: tuple[str, ...] = (),
    expected_worker_id: str | None = None,
    supervisor_pid: int | None = None,
) -> FastAPI:
    if not isinstance(workspace_token, str) or not workspace_token.strip():
        raise DomainError("workspace_token_required", {})
    if agent_token is not None and (
        not isinstance(agent_token, str)
        or not agent_token.strip()
        or hmac.compare_digest(agent_token, workspace_token)
    ):
        raise DomainError("invalid_agent_token", {})
    app = FastAPI(
        title="Forecast Anything",
        version="1.0.0",
        responses={
            401: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
        },
    )
    app.state.observatory = Observatory(ledger, runtime)
    cookie_name = "fa_browser_" + ledger.workspace_id()
    sessions = {}
    session_lock = threading.Lock()

    def valid_session(request):
        origin = request.headers.get("origin")
        if origin not in console_origins:
            return False
        raw = request.cookies.get(cookie_name, "")
        if not raw or len(raw) > 128:
            return False
        digest = hashlib.sha256(raw.encode()).hexdigest()
        with session_lock:
            record = sessions.get(digest)
            if not record or record[1] <= _session_now():
                sessions.pop(digest, None)
                return False
            return hmac.compare_digest(record[0], origin)

    @app.middleware("http")
    async def authenticate(request, call_next):
        if request.url.path != "/health":
            supplied = request.headers.get("authorization", "")
            agent_route = request.url.path == "/v1/agent/operations"
            if agent_route and agent_token is None:
                return JSONResponse(
                    {"code": "unauthorized", "details": {}},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
            expected = agent_token if agent_route else workspace_token
            bearer_valid = hmac.compare_digest(
                supplied.encode(), f"Bearer {expected}".encode()
            )
            cookie_valid = not supplied and not agent_route and valid_session(request)
            if not bearer_valid and not cookie_valid:
                return JSONResponse(
                    {"code": "unauthorized", "details": {}},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
            if cookie_valid:
                request.state.browser_session_valid = lambda: valid_session(request)
        return await call_next(request)

    # Register after the auth middleware so CORS can answer browser preflight
    # requests before authentication and wrap authenticated responses.
    if console_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(console_origins),
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "Accept", "Last-Event-ID"],
        )

    @app.post("/v1/browser-session", status_code=201)
    def create_browser_session(request: Request):
        origin = request.headers.get("origin")
        if origin not in console_origins or (
            request.url.scheme != "https"
            and request.url.hostname not in {"localhost", "127.0.0.1", "::1"}
        ):
            return JSONResponse({"code": "forbidden", "details": {}}, status_code=403)
        if not hmac.compare_digest(
            request.headers.get("authorization", "").encode(),
            f"Bearer {workspace_token}".encode(),
        ):
            return JSONResponse(
                {"code": "unauthorized", "details": {}}, status_code=401
            )
        raw = secrets.token_urlsafe(32)
        digest = hashlib.sha256(raw.encode()).hexdigest()
        now = _session_now()
        with session_lock:
            for key in [key for key, value in sessions.items() if value[1] <= now]:
                sessions.pop(key, None)
            previous = request.cookies.get(cookie_name, "")
            if previous and len(previous) <= 128:
                sessions.pop(hashlib.sha256(previous.encode()).hexdigest(), None)
            sessions[digest] = (origin, now + SESSION_LIFETIME)
        response = JSONResponse(
            {"expires_in": SESSION_LIFETIME},
            status_code=201,
            headers={"Cache-Control": "no-store"},
        )
        response.set_cookie(
            cookie_name,
            raw,
            max_age=SESSION_LIFETIME,
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="strict",
            path="/",
        )
        return response

    @app.post("/v1/browser-session/revoke")
    def revoke_browser_session(request: Request):
        if not valid_session(request):
            return JSONResponse(
                {"code": "unauthorized", "details": {}}, status_code=401
            )
        digest = hashlib.sha256(request.cookies[cookie_name].encode()).hexdigest()
        with session_lock:
            sessions.pop(digest, None)
        response = JSONResponse(
            {"revoked": True}, headers={"Cache-Control": "no-store"}
        )
        response.delete_cookie(
            cookie_name,
            path="/",
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="strict",
        )
        return response

    @app.exception_handler(DomainError)
    async def domain_error(request, error):
        status = (
            404
            if error.code in {"not_found", "source_not_found"}
            else 409
            if error.code
            in {
                "source_content_changed",
                "idempotency_conflict",
                "immutable_identity",
                "stale_question_revision",
                "operation_version_conflict",
                "stale_operation_version",
                "operation_already_submitted",
                "operation_not_ready",
                "operation_job_mismatch",
            }
            else 422
        )
        payload = error.model_dump(mode="json")
        payload["details"] = public_error_details(payload["details"])
        return JSONResponse(payload, status_code=status)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        # Inputs can include secret refs or authorization material; never echo them.
        errors = public_error_details(error.errors())
        return JSONResponse(
            {"code": "validation_error", "details": {"errors": errors}}, status_code=422
        )

    @app.get("/health")
    def health(request: Request):
        worker, model = ledger.worker_diagnostics(
            ledger.clock(), expected_worker_id=expected_worker_id
        )
        payload = {
            "status": "ok",
            "worker": worker,
            "worker_model": model,
            "runtime_version": runtime_version(),
            "diagnostics_version": 1,
            "supervisor_pid": supervisor_pid,
        }
        if nonce := validated_nonce(request.headers, workspace_token):
            payload["required_provider"] = runtime.required_provider
            payload["model_cache"] = model_readiness(runtime)["status"]
            return sign_diagnostics(payload, nonce, workspace_token)
        return payload

    app.include_router(router(app.state.observatory))
    return app
