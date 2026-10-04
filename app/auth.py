import os
import secrets
from pathlib import Path
from typing import Optional
from fastapi import Header, HTTPException, Request, status
from fastapi.responses import JSONResponse


def load_env(env_path: str = ".env") -> None:
    """Load key-value pairs from .env into os.environ if present."""
    path = Path(env_path)
    if not path.is_file():
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k and k not in os.environ:
                    os.environ[k] = v
    except Exception:
        pass


load_env()


class UnauthorizedException(HTTPException):
    def __init__(self, detail: str = "Missing or invalid API key"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
        )


def validate_our_api_key_config() -> str:
    """
    Validate that OUR_API_KEY is configured in the environment.
    Raises RuntimeError if missing or empty.
    """
    api_key = os.getenv("OUR_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "Configuration Error: OUR_API_KEY environment variable is not set or is empty. "
            "Please configure OUR_API_KEY in your environment or .env file."
        )
    return api_key


def get_our_api_key() -> str:
    return os.getenv("OUR_API_KEY", "").strip()


async def verify_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
) -> str:
    """
    FastAPI dependency to verify the client's X-API-Key header.
    Missing or incorrect key triggers 401 Unauthorized before any file
    validation or Gemini call (protecting quotas and computing resources).
    """
    expected_key = get_our_api_key()
    if not expected_key or not x_api_key or not secrets.compare_digest(x_api_key, expected_key):
        raise UnauthorizedException("Missing or invalid API key")
    return x_api_key
