import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
from google import genai
from google.genai import errors, types

from app.image_preprocessor import normalize_image_orientation
from app.models import (
    BillItem,
    BillParseResponse,
    ExtractedField,
    InternalBillExtraction,
    InternalLineItem,
)
from app.reconciliation import reconcile

logger = logging.getLogger("gemini_client")


# System instruction prompt for Gemini multimodal bill parsing
EXTRACTION_SYSTEM_PROMPT = """You are an expert, highly accurate AI system specialized in extracting structured inventory and invoice data from Indian pharmacy and wholesale medical bills.
Your primary purpose is to allow pharmacy owners to load purchased medicines into inventory from a dealer bill.

CRITICAL INSTRUCTIONS:
1. MULTI-PAGE CONTINUITY:
   - The provided images represent ALL PAGES OF ONE SINGLE BILL.
   - Treat them as a single continuous document. If a line-item table spans across page breaks, seamlessly reconstruct the items into one unified `items` array in document order.
   - Do not duplicate header information (supplier/invoice details) or repeat items during page transitions.

2. ABSOLUTE NO-GUESSING RULE (HARD CONSTRAINT):
   - You must NEVER silently guess, extrapolate, or invent plausible numbers, medicine names, or tax percentages that you cannot clearly decipher.
   - If any character, digit, or decimal point is obscured, folded, torn, blurry, or ambiguous, you MUST set `value` to null and lower its `confidence` (< 0.6).
   - If confidence is below 0.6 for any critical inventory field (medicine_name, quantity, mrp, rate), set `value` to null and record a descriptive alert in the top-level `flags` array.
   - For optional fields that are legitimately absent from the bill (e.g. batch_number, expiry_date, discount, hsn_code, notes), set `value` to null, `raw` to null, and `confidence` to 1.0 without penalty.

3. HEADER-GROUNDED COLUMN MAPPING & PRICING EXTRACTION:
   Before extracting line items, first identify and examine every column header actually printed on this document's item table, exactly as printed (e.g. 'Item Description', 'Batch', 'Exp', 'Old Mrp / Mrp', 'MRP', 'Qty', 'Rate', 'Disc %', 'GST %' — or whatever this specific bill uses; do not assume any fixed set or order).

   Then, for each line item, map each printed value to the field it corresponds to based on the ACTUAL header text and label meaning — never by position or by assuming a standard layout, since different distributors print completely different column sets and orders. Record which header label you used for each price field in that field's source_column.

   Field definitions & disambiguation rules:
   - medicine_name: The brand/generic description of the medicine (including strength and pack size if printed, e.g. "CYTOGARD OD 60 MG CAPSULE (10 CAP)").
   - mrp: The CURRENT / active Maximum Retail Price, as a STRING (e.g. "233.79", "354.37").
     * CRITICAL - Old Mrp vs Mrp disambiguation:
       Some bills (e.g. Sastasundar Healthbuddy invoices) print a column header literally as "Old Mrp / Mrp" with TWO stacked numbers in each cell — the upper number is the OLD (previous/outdated) MRP, and the lower number is the CURRENT MRP.
       ALWAYS extract the CURRENT (lower) number for the `mrp` field — NEVER the old/upper one.
       Verified example from a real bill: a cell shows "377.99" (Old Mrp) stacked above "354.37" (Mrp) for item "CYTOGARD OD 60 MG CAPSULE (10 CAP)". The correct `mrp` value is "354.37", not "377.99".
       Similarly, row with cell "188.43" stacked above "176.65" (MONTEK) -> extract "176.65".
       Row with cell "277.59" stacked above "260.24" (STATOR CV) -> extract "260.24".
       If a bill shows only ONE number for MRP (no Old Mrp), extract that number as-is — this disambiguation only applies when two stacked values are present under an Old Mrp/Mrp combined header.
   - quantity: The billed quantity as a STRING (e.g. "1", "3").
   - batch_number: The manufacturer batch/lot number (e.g. "AKM0044", "LXC2014"). Null if absent.
   - expiry_date: The product expiry date, normalized to YYYY-MM format as a STRING (e.g. "2025-08", "2027-10"). If printed as MM/YY (e.g. "10/27"), convert to YYYY-MM ("2027-10"). Null if absent or unreadable.
   - hsn_code: The HSN/SAC code as a STRING (e.g. "30049079"). Null if absent.
   - rate: The wholesale/trade unit price before any per-line discount, as a STRING (e.g. "175.03", "270.00").
   - discount: The per-line discount % as a STRING (e.g. "4.00", "6.00"), distinguished explicitly from any unrelated "Scheme %" / "Sch %" column if both are present on the bill.
     * CRITICAL ADJACENT-COLUMN WARNING:
       Some bills print a 'Sch %' (scheme discount) column immediately next to a 'Disc %' (trade discount) column — these are visually close together and easy to confuse. The `discount` field must come from 'Disc %' specifically, never from 'Sch %'. If unsure which column is which, state both values you see before choosing.
       Maintain strict vertical column alignment across ALL rows in the table: on bills with both columns, 'Sch %' is often 0.00 down the entire column, whereas 'Disc %' contains the trade discount (e.g. 4.00, 2.00). Do NOT drift into the 'Sch %' column on any row. Verify via printed math: rate x (1 - discount/100) matches the line's pre-tax value (e.g. 175.03 x 0.96 = 168.03 -> discount is 4.00, not 0.00; 58.55 x 0.96 = 56.21 -> discount is 4.00).
     Null if no discount is printed.

4. CONFIDENCE & LEGIBILITY:
   Confidence must reflect ONLY how clearly and legibly you can read the printed text for THAT specific field.
   A clearly printed value should have confidence=1.0. Only lower confidence when the digit, decimal, or text is visually ambiguous, obscured, blurry, or genuinely hard to read.

5. EXTRACTION TARGETS:
   - Invoice Level:
     * supplier_name: Name of the selling dealer / distributor / agency (e.g. "SASTASUNDAR HEALTHBUDDY LIMITED", "JYOTSNA MEDICAL AGENCY").
     * supplier_gstin: 15-character Indian GSTIN of the supplier (e.g. "19AAHCM0651P1ZO").
     * bill_no: Invoice / Bill / Memo number (e.g. "TB2037025", "2600007700984592").
     * bill_date: Invoice date, normalized to YYYY-MM-DD (e.g. "2026-09-23", "2023-09-02").
     * notes: Any printed terms, notes, or remarks, or null if none.
     * taxable_amount: Pre-tax taxable subtotal of the invoice as a numeric float (usually printed in a summary box, e.g. 958.40 or 3638.00).
     * cgst_amount: Total CGST amount on the invoice as a numeric float (e.g. 23.97 or 91.66).
     * sgst_amount: Total SGST amount on the invoice as a numeric float (e.g. 23.97 or 91.66).
     * total_amount: Net payable invoice grand total as a numeric float (e.g. 1006.00 or 3821.00).
   - Items: Array of all line items with fields specified above.

6. OUTPUT FORMAT:
   - Output strictly valid JSON conforming precisely to the provided schema. Do not enclose output in markdown blocks, backticks, or preamble.
"""


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


def validate_gemini_config() -> str:
    """
    Validate that GEMINI_API_KEY is configured.
    Raises RuntimeError at startup if missing.
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "Configuration Error: GEMINI_API_KEY environment variable is not set or is empty. "
            "Please configure GEMINI_API_KEY in your environment or .env file before starting the application."
        )
    return api_key


def get_gemini_model() -> str:
    """
    Get the configured Gemini model string.
    Defaults to 'gemini-2.5-flash'.
    """
    return os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()


def to_str_or_none(val: Any) -> Optional[str]:
    """Convert a value to stripped string or None if empty/null."""
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in ("none", "null"):
        return None
    return s


def normalize_quantity_str(val: Any) -> Optional[str]:
    """Normalize quantity string (e.g. 1.0 -> '1', 3 -> '3')."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        if float(val).is_integer():
            return str(int(val))
        return str(val)
    s = str(val).strip()
    if not s or s.lower() in ("none", "null"):
        return None
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
        return str(f)
    except ValueError:
        return s


def normalize_gst_str(val: Any) -> Optional[str]:
    """Normalize GST string (e.g. '5%' -> '5', '5.00' -> '5', '12' -> '12')."""
    if val is None:
        return None
    s = str(val).strip().rstrip("%").strip()
    if not s or s.lower() in ("none", "null"):
        return None
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
        return f"{f:g}"
    except ValueError:
        return s


def normalize_expiry_date(val: Optional[str]) -> Optional[str]:
    """Normalize expiry date to YYYY-MM if recognizable."""
    if not val:
        return None
    val = val.strip()
    # YYYY-MM or YYYY/MM
    m = re.match(r"^(\d{4})[-/.](\d{1,2})$", val)
    if m:
        year, month = m.groups()
        return f"{year}-{int(month):02d}"
    # MM/YYYY or MM-YYYY
    m = re.match(r"^(\d{1,2})[-/.](\d{4})$", val)
    if m:
        month, year = m.groups()
        return f"{year}-{int(month):02d}"
    # MM/YY or MM-YY
    m = re.match(r"^(\d{1,2})[-/.](\d{2})$", val)
    if m:
        month, yy = m.groups()
        year = 2000 + int(yy) if int(yy) < 100 else int(yy)
        return f"{year}-{int(month):02d}"
    return val


def normalize_bill_date(val: Optional[str]) -> Optional[str]:
    """Normalize bill date to YYYY-MM-DD if recognizable."""
    if not val:
        return None
    val = val.strip()
    # YYYY-MM-DD
    m = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", val)
    if m:
        year, month, day = m.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"
    # DD-MM-YYYY
    m = re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", val)
    if m:
        day, month, year = m.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"
    # DD-MM-YY
    m = re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2})", val)
    if m:
        day, month, yy = m.groups()
        year = 2000 + int(yy)
        return f"{year}-{int(month):02d}-{int(day):02d}"
    return val


def convert_to_public_response(
    internal: InternalBillExtraction,
    status: str,
    overall_confidence: float,
    model_version: str,
) -> BillParseResponse:
    """Convert internal extraction result to the public response shape."""
    public_items: List[BillItem] = []
    for item in internal.items:
        public_items.append(
            BillItem(
                medicine_name=to_str_or_none(item.medicine_name.value),
                mrp=to_str_or_none(item.mrp.value),
                quantity=normalize_quantity_str(item.quantity.value),
                batch_number=to_str_or_none(item.batch_number.value),
                expiry_date=normalize_expiry_date(item.expiry_date.value),
                hsn_code=to_str_or_none(item.hsn_code.value),
                gst=normalize_gst_str(item.gst.value),
                rate=to_str_or_none(item.rate.value),
                discount=to_str_or_none(item.discount.value),
            )
        )

    return BillParseResponse(
        supplier_name=to_str_or_none(internal.supplier_name.value),
        supplier_gstin=to_str_or_none(internal.supplier_gstin.value),
        bill_no=to_str_or_none(internal.bill_no.value),
        bill_date=normalize_bill_date(internal.bill_date.value),
        notes=to_str_or_none(internal.notes.value),
        taxable_amount=internal.taxable_amount.value,
        cgst_amount=internal.cgst_amount.value,
        sgst_amount=internal.sgst_amount.value,
        total_amount=internal.total_amount.value,
        items=public_items,
        status=status,
        overall_confidence=overall_confidence,
        flags=internal.flags,
        model_version=model_version,
    )


def parse_bill(pages: List[Tuple[bytes, str]]) -> Dict[str, Any]:
    """
    Synchronously parse one or more pages of a single pharmacy bill using Google Gemini.

    Args:
        pages: List of (file_bytes, mime_type) tuples representing all pages of ONE bill.

    Returns:
        Dictionary matching the public BillParseResponse schema.
    """
    api_key = validate_gemini_config()
    model_name = get_gemini_model()

    client = genai.Client(api_key=api_key)

    # 1. Preprocess: detect and correct orientation for every image page
    processed_pages: List[Tuple[bytes, str]] = []
    for file_bytes, mime_type in pages:
        norm_bytes, norm_mime, deg = normalize_image_orientation(file_bytes, mime_type)
        if deg:
            logger.info("Auto-corrected image orientation (%d degrees)", deg)
        processed_pages.append((norm_bytes, norm_mime))

    # 2. Construct multimodal contents
    contents: List[Any] = []
    for file_bytes, mime_type in processed_pages:
        contents.append(
            types.Part.from_bytes(
                data=file_bytes,
                mime_type=mime_type,
            )
        )

    contents.append(
        "Extract all pharmacy bill data across all provided page(s) according to the schema instructions.\n"
        "REMINDER: When extracting line items, if you see adjacent columns for 'Sch %' (scheme discount) and 'Disc %' (trade discount), "
        "always extract the `discount` field from 'Disc %' (e.g. 4.00), NEVER from 'Sch %' (which is often 0.00)."
    )

    # 3. Configure generation with internal schema enforcement
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=InternalBillExtraction,
        media_resolution=types.MediaResolution.MEDIA_RESOLUTION_HIGH,
        system_instruction=EXTRACTION_SYSTEM_PROMPT,
        temperature=0.0,
    )

    # 4. Execute call with retries on transient errors
    max_retries = 5
    response = None
    for attempt in range(max_retries + 1):
        try:
            logger.info(
                "Calling Gemini API (model: %s, pages: %d, attempt: %d)...",
                model_name,
                len(pages),
                attempt + 1,
            )
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=config,
            )
            break
        except errors.ClientError:
            logger.error("Non-retryable 4xx client error from Gemini API.")
            raise
        except (errors.ServerError, httpx.TimeoutException, httpx.NetworkError, TimeoutError) as exc:
            if attempt < max_retries:
                backoff_delay = 3.0 * (2 ** attempt)
                logger.warning(
                    "Transient error calling Gemini API (attempt %d/%d): %s. Retrying in %.1fs...",
                    attempt + 1,
                    max_retries + 1,
                    exc,
                    backoff_delay,
                )
                time.sleep(backoff_delay)
                continue
            logger.error("Transient error persisted after retry: %s", exc)
            raise

    if not response or not response.text:
        raise ValueError("Gemini API returned an empty response.")

    # 5. Parse into InternalBillExtraction
    try:
        raw_dict = json.loads(response.text)
        internal = InternalBillExtraction.model_validate(raw_dict)
    except Exception as exc:
        logger.error("Failed to parse Gemini response text as InternalBillExtraction: %s", exc)
        raise

    # 6. Apply Confidence Guardrails:
    # If confidence < 0.6 on critical fields (medicine_name, quantity, mrp, rate),
    # set value to null and append descriptive flag
    critical_item_fields = ["medicine_name", "quantity", "mrp", "rate"]
    for idx, item in enumerate(internal.items):
        for field_name in critical_item_fields:
            field: ExtractedField = getattr(item, field_name)
            if field.confidence < 0.6 and field.value is not None:
                field.value = None
                internal.flags.append(
                    f"Line item #{idx + 1} '{field_name}' confidence is low ({field.confidence:.2f}); value set to null."
                )

    critical_total_fields = ["taxable_amount", "total_amount"]
    for field_name in critical_total_fields:
        field: ExtractedField = getattr(internal, field_name)
        if field.confidence < 0.6 and field.value is not None:
            field.value = None
            internal.flags.append(
                f"Totals '{field_name}' confidence is low ({field.confidence:.2f}); value set to null."
            )

    # 7. Compute overall_confidence across all ExtractedField instances
    all_fields: List[ExtractedField] = [
        internal.supplier_name,
        internal.supplier_gstin,
        internal.bill_no,
        internal.bill_date,
        internal.notes,
        internal.taxable_amount,
        internal.cgst_amount,
        internal.sgst_amount,
        internal.total_amount,
    ]
    for item in internal.items:
        all_fields.extend([
            item.medicine_name,
            item.mrp,
            item.quantity,
            item.batch_number,
            item.expiry_date,
            item.hsn_code,
            item.gst,
            item.rate,
            item.discount,
        ])

    field_confidences = [f.confidence for f in all_fields]
    if field_confidences:
        computed_confidence = round(sum(field_confidences) / len(field_confidences), 4)
    else:
        computed_confidence = 0.0

    # 8. Preliminary status determination:
    # "needs_review" if overall_confidence < 0.75; otherwise "completed".
    if computed_confidence < 0.75:
        status = "needs_review"
    else:
        status = "completed"

    # 9. Apply deterministic reconciliation (bill-level arithmetic sanity checks)
    internal.status = status
    internal = reconcile(internal)
    status = internal.status

    # 10. Final status gate: any actionable (non-informational) flags force status >= needs_review
    actionable_flags = [
        f for f in internal.flags
        if not f.startswith("reconciliation: informational:")
    ]
    if actionable_flags and status != "needs_review":
        status = "needs_review"

    # 11. Convert to public response schema
    public_response = convert_to_public_response(
        internal=internal,
        status=status,
        overall_confidence=computed_confidence,
        model_version=model_name,
    )

    return public_response.model_dump()
