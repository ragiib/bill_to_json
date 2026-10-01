import re
from typing import Generic, List, Literal, Optional, TypeVar
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Internal extraction models (capturing value + confidence + raw for guardrails)
# ---------------------------------------------------------------------------

class ExtractedField(BaseModel, Generic[T]):
    model_config = ConfigDict(coerce_numbers_to_str=True)
    value: Optional[T] = Field(
        default=None,
        description="Normalized value. Null if uncertain, illegible, or absent.",
    )
    raw: Optional[str] = Field(
        default=None,
        description="Verbatim text as visually seen on the bill, prior to normalization.",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0.",
    )
    source_column: Optional[str] = Field(
        default=None,
        description="Printed column header text from which this field was extracted.",
    )


class InternalLineItem(BaseModel):
    medicine_name: ExtractedField[str] = Field(default_factory=ExtractedField[str])
    mrp: ExtractedField[str] = Field(default_factory=ExtractedField[str])
    quantity: ExtractedField[str] = Field(default_factory=ExtractedField[str])
    batch_number: ExtractedField[str] = Field(default_factory=ExtractedField[str])
    expiry_date: ExtractedField[str] = Field(default_factory=ExtractedField[str])
    hsn_code: ExtractedField[str] = Field(default_factory=ExtractedField[str])
    gst: ExtractedField[str] = Field(default_factory=ExtractedField[str])
    rate: ExtractedField[str] = Field(default_factory=ExtractedField[str])
    discount: ExtractedField[str] = Field(default_factory=ExtractedField[str])


class InternalBillExtraction(BaseModel):
    supplier_name: ExtractedField[str] = Field(default_factory=ExtractedField[str])
    supplier_gstin: ExtractedField[str] = Field(default_factory=ExtractedField[str])
    bill_no: ExtractedField[str] = Field(default_factory=ExtractedField[str])
    bill_date: ExtractedField[str] = Field(default_factory=ExtractedField[str])
    notes: ExtractedField[str] = Field(default_factory=ExtractedField[str])
    taxable_amount: ExtractedField[float] = Field(default_factory=ExtractedField[float])
    cgst_amount: ExtractedField[float] = Field(default_factory=ExtractedField[float])
    sgst_amount: ExtractedField[float] = Field(default_factory=ExtractedField[float])
    total_amount: ExtractedField[float] = Field(default_factory=ExtractedField[float])
    items: List[InternalLineItem] = Field(default_factory=list)
    flags: List[str] = Field(default_factory=list)
    status: Literal["completed", "needs_review", "failed"] = "completed"


# ---------------------------------------------------------------------------
# Public response models (flatter, exact target output shape)
# ---------------------------------------------------------------------------

class BillItem(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)
    medicine_name: Optional[str] = None
    mrp: Optional[str] = None
    quantity: Optional[str] = None
    batch_number: Optional[str] = None
    expiry_date: Optional[str] = None
    hsn_code: Optional[str] = None
    gst: Optional[str] = None
    rate: Optional[str] = None
    discount: Optional[str] = None


class BillParseResponse(BaseModel):
    supplier_name: Optional[str] = None
    supplier_gstin: Optional[str] = None
    bill_no: Optional[str] = None
    bill_date: Optional[str] = None
    notes: Optional[str] = None
    taxable_amount: Optional[float] = None
    cgst_amount: Optional[float] = None
    sgst_amount: Optional[float] = None
    total_amount: Optional[float] = None
    items: List[BillItem] = Field(default_factory=list)
    status: Literal["completed", "needs_review", "failed"] = "completed"
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    flags: List[str] = Field(default_factory=list)
    model_version: str = "gemini-2.5-flash"


class ErrorResponse(BaseModel):
    error: str
    detail: str


class HealthResponse(BaseModel):
    status: str = "ok"
