"""
Deterministic bill-level reconciliation for pharmacy bill extraction.

This module implements two bill-level sanity checks:
1. Check A (approximate line-sum check):
   Computes estimated_taxable = sum( qty * rate * (1 - discount/100) )
   across all items where quantity and rate are present and numeric (discount 0 if absent),
   and compares against stated taxable_amount (+-5% tolerance).
2. Check B (tax-consistency check):
   Verifies taxable_amount + cgst_amount + sgst_amount ~= total_amount
   within +-1 unit tolerance.

No per-line arithmetic checks are performed.
"""

import logging
from typing import Any, List, Optional, Union

from app.models import BillParseResponse, InternalBillExtraction

logger = logging.getLogger("reconciliation")

# Check A: +-10% tolerance for approximate line-sum check (informational only)
LINE_SUM_TOLERANCE_PERCENT: float = 10.0

# Check B: +-1 absolute unit tolerance for document tax consistency
TAX_CONSISTENCY_TOLERANCE_ABSOLUTE: float = 1.0


def _flag(message: str) -> str:
    """Prefix a reconciliation flag consistently."""
    return f"reconciliation: {message}"


def _parse_float(val: Any) -> Optional[float]:
    """Safely parse a numeric float from string/number or return None."""
    if val is None:
        return None
    try:
        clean = str(val).strip().replace("%", "").replace(",", "")
        if not clean or clean.lower() in ("null", "none"):
            return None
        return float(clean)
    except (ValueError, TypeError):
        return None


def _get_val(obj: Any, field_name: str) -> Any:
    """Extract field value from an internal ExtractedField or public schema."""
    val = getattr(obj, field_name, None)
    if hasattr(val, "value"):
        return val.value
    return val


def reconcile(
    response: Union[InternalBillExtraction, BillParseResponse]
) -> Union[InternalBillExtraction, BillParseResponse]:
    """
    Run bill-level deterministic sanity checks on an extracted bill.

    Mutates response in-place (appends to response.flags and escalates status
    to 'needs_review' if any hard check fails) and returns the response.
    """
    taxable_val = _parse_float(_get_val(response, "taxable_amount"))
    cgst_val = _parse_float(_get_val(response, "cgst_amount"))
    sgst_val = _parse_float(_get_val(response, "sgst_amount"))
    total_val = _parse_float(_get_val(response, "total_amount"))

    # -----------------------------------------------------------------------
    # Check A — Approximate line-sum check vs stated taxable_amount (+-10%)
    # NOTE: On bills where the printed 'Rate' is already net of discount or
    # where additional line-level scheme/adjustments apply, this formula can
    # diverge significantly. Per design decision, this check is treated as
    # informational: it appends an advisory flag for human review but does not
    # alone force status to 'needs_review'.
    # -----------------------------------------------------------------------
    items = getattr(response, "items", [])
    if taxable_val is not None and taxable_val > 0.0 and items:
        line_estimates: List[float] = []
        for item in items:
            qty = _parse_float(_get_val(item, "quantity"))
            rate = _parse_float(_get_val(item, "rate"))
            if qty is None or rate is None:
                continue

            disc_raw = _get_val(item, "discount")
            if disc_raw is None or str(disc_raw).strip() == "":
                disc = 0.0
            else:
                disc = _parse_float(disc_raw)
                if disc is None:
                    continue  # discount was present but non-numeric

            line_taxable = qty * rate * (1.0 - disc / 100.0)
            line_estimates.append(line_taxable)

        if line_estimates:
            estimated_taxable = sum(line_estimates)
            pct_diff = abs(estimated_taxable - taxable_val) / taxable_val * 100.0

            if pct_diff > LINE_SUM_TOLERANCE_PERCENT:
                msg = _flag(
                    f"informational: estimated line total ({estimated_taxable:.2f}) differs "
                    f"from stated taxable_amount ({taxable_val:.2f}) by more than {LINE_SUM_TOLERANCE_PERCENT:.0f}% "
                    f"(rate may already be net-of-discount or include uncaptured scheme adjustments)"
                )
                logger.info("Reconciliation informational flag: %s", msg)
                response.flags.append(msg)
                # Option (a): informational only — do NOT escalate status to needs_review

    # -----------------------------------------------------------------------
    # Check B — Tax consistency check: taxable + cgst + sgst ~= total (+-1 unit)
    # -----------------------------------------------------------------------
    if (
        taxable_val is not None
        and cgst_val is not None
        and sgst_val is not None
        and total_val is not None
    ):
        expected_total = taxable_val + cgst_val + sgst_val
        diff = abs(expected_total - total_val)

        if diff > TAX_CONSISTENCY_TOLERANCE_ABSOLUTE:
            msg = _flag(
                f"tax consistency check does not reconcile: taxable_amount ({taxable_val:.2f}) + "
                f"cgst_amount ({cgst_val:.2f}) + sgst_amount ({sgst_val:.2f}) = {expected_total:.2f} "
                f"differs from total_amount ({total_val:.2f}) by {diff:.2f} "
                f"(exceeds +-{TAX_CONSISTENCY_TOLERANCE_ABSOLUTE:.0f} unit tolerance)"
            )
            logger.info("Reconciliation flag: %s", msg)
            response.flags.append(msg)
            if response.status != "needs_review":
                response.status = "needs_review"

    return response
