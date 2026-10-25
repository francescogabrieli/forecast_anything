"""Application factory; authentication covers documentation and streaming too."""

import hmac

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ..contracts import DomainError, ErrorResponse
from ..runtime import Runtime
from ..store import Ledger
from .routes import router
from .service import Observatory


def create_app(ledger: Ledger, runtime: Runtime, workspace_token: str) -> FastAPI:
    if not isinstance(workspace_token, str) or not workspace_token.strip():
        raise DomainError("workspace_token_required", {})
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
            if not hmac.compare_digest(
                supplied.encode(), f"Bearer {workspace_token}".encode()
            ):
                return JSONResponse(
                    {"code": "unauthorized", "details": {}},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
        return await call_next(request)

    @app.exception_handler(DomainError)
    async def domain_error(request, error):
        status = (
            404
            if error.code in {"not_found", "source_not_found"}
            else 409
            if error.code in {"idempotency_conflict", "immutable_identity"}
            else 422
        )
        return JSONResponse(error.model_dump(mode="json"), status_code=status)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        # Inputs can include secret refs or authorization material; never echo them.
        errors = [{"loc": list(e["loc"]), "type": e["type"]} for e in error.errors()]
        return JSONResponse(
            {"code": "validation_error", "details": {"errors": errors}}, status_code=422
        )

    @app.get("/health")
    def health():
        return {"status": "ok"}

    app.include_router(router(app.state.observatory))
    return app
