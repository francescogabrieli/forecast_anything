"""Application factory; authentication covers documentation and streaming too."""

import hmac

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
            if not hmac.compare_digest(
                supplied.encode(), f"Bearer {expected}".encode()
            ):
                return JSONResponse(
                    {"code": "unauthorized", "details": {}},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
        return await call_next(request)

    # Register after the auth middleware so CORS can answer browser preflight
    # requests before authentication and wrap authenticated responses.
    if console_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(console_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "Accept", "Last-Event-ID"],
        )

    @app.exception_handler(DomainError)
    async def domain_error(request, error):
        status = (
            404
            if error.code in {"not_found", "source_not_found"}
            else 409
            if error.code in {"idempotency_conflict", "immutable_identity"}
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
