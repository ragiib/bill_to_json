from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.auth import UnauthorizedException, validate_our_api_key_config
from app.gemini_client import validate_gemini_config
from app.models import HealthResponse
from app.routers.parse import router as parse_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Verify environment configuration at startup
    validate_gemini_config()
    validate_our_api_key_config()
    yield


app = FastAPI(
    title="Pharmacy Bill Intelligence API",
    version="1.0.0",
    description="Stateless, synchronous API for automated pharmacy bill extraction via Google Gemini.",
    lifespan=lifespan,
)


@app.exception_handler(UnauthorizedException)
async def unauthorized_exception_handler(request: Request, exc: UnauthorizedException):
    return JSONResponse(
        status_code=401,
        content={"error": "unauthorized", "detail": exc.detail},
    )


# Register routes
app.include_router(parse_router)


@app.get("/healthz", response_model=HealthResponse, tags=["health"])
def health_check():
    """Liveness/readiness probe for Google Cloud Run container checks."""
    return HealthResponse(status="ok")
