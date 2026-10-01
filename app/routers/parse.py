import logging
from pathlib import Path
from typing import List, Tuple, Union
from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse

from app.gemini_client import parse_bill
from app.models import BillParseResponse, ErrorResponse

logger = logging.getLogger("parse_router")

router = APIRouter(prefix="/api/v1", tags=["bill-processing"])

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "pdf"}
MAX_PER_FILE_SIZE = 15 * 1024 * 1024  # 15 MB per file
MAX_TOTAL_REQUEST_SIZE = 50 * 1024 * 1024  # 50 MB total request cap

MIME_MAP = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "pdf": "application/pdf",
}


@router.post(
    "/parse-bill",
    response_model=BillParseResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Validation failure or file constraint violation"},
        500: {"model": ErrorResponse, "description": "Internal processing failure"},
    },
)
async def parse_bill_endpoint(
    files: List[UploadFile] = File(
        ...,
        description="One or more images or PDF files representing ALL PAGES OF ONE BILL.",
    ),
) -> Union[BillParseResponse, JSONResponse]:
    """
    Synchronously parse all pages of a single pharmacy bill using Google Gemini.
    All validation is performed upfront before initiating any model calls.
    """
    if not files:
        return JSONResponse(
            status_code=400,
            content={
                "error": "empty_request",
                "detail": "No files were uploaded. Please provide at least one bill page.",
            },
        )

    # 1. Pre-validate file extensions for ALL files before reading streams
    for upload in files:
        filename = upload.filename or "unknown"
        ext = Path(filename).suffix.lower().lstrip(".")
        if not ext or ext not in ALLOWED_EXTENSIONS:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "unsupported_file_type",
                    "detail": (
                        f"File '{filename}' has invalid type '{ext or 'unknown'}'. "
                        f"Allowed file types are: {', '.join(sorted(ALLOWED_EXTENSIONS))}."
                    ),
                },
            )

    # 2. Read each file stream, checking per-file and total size bounds
    total_request_size = 0
    pages: List[Tuple[bytes, str]] = []

    for upload in files:
        filename = upload.filename or "unknown"
        ext = Path(filename).suffix.lower().lstrip(".")
        chunks = []
        file_size = 0

        while chunk := await upload.read(65536):
            file_size += len(chunk)
            total_request_size += len(chunk)

            if file_size > MAX_PER_FILE_SIZE:
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": "file_too_large",
                        "detail": (
                            f"File '{filename}' exceeds maximum allowed limit of 15MB. "
                            f"Received {file_size} bytes."
                        ),
                    },
                )

            if total_request_size > MAX_TOTAL_REQUEST_SIZE:
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": "request_too_large",
                        "detail": (
                            f"Total request size ({total_request_size} bytes) exceeds maximum limit of 50MB across all pages."
                        ),
                    },
                )

            chunks.append(chunk)

        if file_size == 0:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "empty_file",
                    "detail": f"File '{filename}' is empty (0 bytes).",
                },
            )

        file_bytes = b"".join(chunks)
        mime_type = upload.content_type
        if not mime_type or mime_type == "application/octet-stream":
            mime_type = MIME_MAP.get(ext, "application/octet-stream")

        pages.append((file_bytes, mime_type))

    # 3. Synchronous extraction call with safe error boundary
    try:
        extraction_result = parse_bill(pages=pages)
        return extraction_result
    except Exception as exc:
        logger.exception("Internal error during pharmacy bill processing: %s", exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": "processing_failed",
                "detail": f"An internal error occurred while processing the bill: {str(exc)}",
            },
        )
