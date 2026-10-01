from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.gemini_client import validate_gemini_config
from app.models import HealthResponse
from app.routers.parse import router as parse_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Verify environment configuration at startup
    validate_gemini_config()
    yield


app = FastAPI(
    title="Pharmacy Bill Intelligence API",
    version="1.0.0",
    description="Stateless, synchronous API for automated pharmacy bill extraction via Google Gemini.",
    lifespan=lifespan,
)

# Register routes
app.include_router(parse_router)


@app.get("/healthz", response_model=HealthResponse, tags=["health"])
def health_check():
    """Liveness/readiness probe for Google Cloud Run container checks."""
    return HealthResponse(status="ok")
