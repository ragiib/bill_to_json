import json
import logging
import os
import sys
import time
from pathlib import Path
from PIL import Image
import numpy as np

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from google import genai
from google.genai import types

from app.image_preprocessor import normalize_image_orientation, get_orientation_engine
from app.models import BillParseResponse, ExtractedField
from app.reconciliation import reconcile
from app.gemini_client import (
    EXTRACTION_SYSTEM_PROMPT,
    validate_gemini_config,
    get_gemini_model,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("batch_2_check")

IMAGE_PATH = Path("test_fixtures/batch_2/test_bill.jpeg")

def check_rotation(image_bytes: bytes, mime_type: str):
    print("==================================================")
    print("ROTATION & ORIENTATION CHECK")
    print("==================================================")
    
    # 1. EXIF check
    img = Image.open(IMAGE_PATH)
    exif = img.getexif()
    exif_tag = exif.get(274) if exif else None
    print(f"EXIF metadata present: {bool(exif)}")
    print(f"EXIF orientation tag (274): {exif_tag}")
    
    # 2. Text-angle detection via RapidOrientation
    engine = get_orientation_engine()
    rgb_img = img.convert("RGB")
    img_np = np.array(rgb_img)
    angle_str, elapse = engine(img_np)
    angle = int(angle_str)
    print(f"RapidOrientation engine: angle={angle}°, elapse={elapse:.4f}s")
    
    # 3. Overall preprocessor output
    norm_bytes, norm_mime, applied_deg = normalize_image_orientation(image_bytes, mime_type)
    print(f"normalize_image_orientation result: applied_degrees={applied_deg}")
    print(f"Rotation triggered: {applied_deg != 0}")
    return norm_bytes, norm_mime, applied_deg, exif_tag, angle

def process_guardrails_and_reconciliation(raw_dict: dict, model_name: str, page_count: int = 1):
    parsed = BillParseResponse.model_validate(raw_dict)
    
    # Confidence Guardrails
    critical_item_fields = [
        "description",
        "quantity",
        "mrp",
        "rate",
        "taxable_value",
        "amount",
    ]
    for idx, item in enumerate(parsed.line_items):
        for field_name in critical_item_fields:
            field: ExtractedField = getattr(item, field_name)
            if field.confidence < 0.6 and field.value is not None:
                field.value = None
                parsed.flags.append(
                    f"Line item #{idx + 1} '{field_name}' confidence is low ({field.confidence:.2f}); value set to null."
                )

    critical_total_fields = ["grand_total", "sub_total", "total_cgst", "total_sgst"]
    for field_name in critical_total_fields:
        field: ExtractedField = getattr(parsed.totals, field_name)
        if field.confidence < 0.6 and field.value is not None:
            field.value = None
            parsed.flags.append(
                f"Totals '{field_name}' confidence is low ({field.confidence:.2f}); value set to null."
            )

    # Compute overall_confidence
    all_fields = [
        parsed.pharmacy.name,
        parsed.pharmacy.address,
        parsed.pharmacy.gstin,
        parsed.pharmacy.dl_no,
        parsed.invoice.invoice_number,
        parsed.invoice.invoice_date,
        parsed.invoice.order_no,
        parsed.totals.sub_total,
        parsed.totals.total_discount,
        parsed.totals.total_cgst,
        parsed.totals.total_sgst,
        parsed.totals.round_off,
        parsed.totals.grand_total,
    ]
    for item in parsed.line_items:
        all_fields.extend([
            item.description,
            item.hsn_code,
            item.quantity,
            item.unit,
            item.batch,
            item.expiry_date,
            item.mrp,
            item.rate,
            item.discount_pct,
            item.taxable_value,
            item.cgst_pct,
            item.sgst_pct,
            item.amount,
        ])

    field_confidences = [f.confidence for f in all_fields]
    if field_confidences:
        computed_confidence = round(sum(field_confidences) / len(field_confidences), 4)
    else:
        computed_confidence = 0.0

    parsed.overall_confidence = computed_confidence
    parsed.page_count = page_count
    parsed.model_version = model_name

    has_null_critical_field = any(
        item.mrp.value is None or item.amount.value is None or item.taxable_value.value is None
        for item in parsed.line_items
    )

    if computed_confidence < 0.75 or has_null_critical_field:
        parsed.status = "needs_review"
    else:
        parsed.status = "completed"

    # Reconciliation
    parsed = reconcile(parsed)
    return parsed

def main():
    api_key = validate_gemini_config()
    model_name = get_gemini_model()
    client = genai.Client(api_key=api_key)

    with open(IMAGE_PATH, "rb") as f:
        file_bytes = f.read()
    mime_type = "image/jpeg"

    # Step 1: Rotation check
    norm_bytes, norm_mime, applied_deg, exif_tag, detected_angle = check_rotation(file_bytes, mime_type)

    contents = [
        types.Part.from_bytes(data=norm_bytes, mime_type=norm_mime),
        "Extract all pharmacy bill data across all provided page(s) according to the schema instructions."
    ]

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=BillParseResponse,
        media_resolution=types.MediaResolution.MEDIA_RESOLUTION_HIGH,
        system_instruction=EXTRACTION_SYSTEM_PROMPT,
        temperature=0.0,
    )

    runs_data = []

    print("\n==================================================")
    print("EXECUTING 3 CONSECUTIVE RUNS (temperature=0.0)")
    print("==================================================")

    for run_idx in range(1, 4):
        print(f"\n--- RUN {run_idx} STARTING ---")
        t0 = time.time()
        response = client.models.generate_content(
            model=model_name,
            contents=contents,
            config=config,
        )
        duration = time.time() - t0
        print(f"Run {run_idx} completed in {duration:.2f}s")

        raw_text = response.text
        raw_dict = json.loads(raw_text)

        # Save raw output
        raw_file = Path(f"test_fixtures/batch_2/raw_gemini_run_{run_idx}.json")
        with open(raw_file, "w", encoding="utf-8") as f:
            json.dump(raw_dict, f, indent=2)

        # Post-process through guardrails & reconciliation
        final_response = process_guardrails_and_reconciliation(raw_dict, model_name)
        final_dict = final_response.model_dump()

        # Save final output
        final_file = Path(f"test_fixtures/batch_2/final_reconciled_run_{run_idx}.json")
        with open(final_file, "w", encoding="utf-8") as f:
            json.dump(final_dict, f, indent=2)

        runs_data.append({
            "run": run_idx,
            "raw": raw_dict,
            "final": final_dict,
        })

        if run_idx < 3:
            time.sleep(2)

    # Save summary of runs
    summary_file = Path("test_fixtures/batch_2/runs_summary.json")
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump({
            "exif_tag": exif_tag,
            "detected_angle": detected_angle,
            "applied_rotation": applied_deg,
            "runs": [
                {
                    "run": r["run"],
                    "status": r["final"]["status"],
                    "overall_confidence": r["final"]["overall_confidence"],
                    "flags": r["final"]["flags"],
                    "totals": {
                        k: r["final"]["totals"][k]["value"]
                        for k in ["sub_total", "total_discount", "total_cgst", "total_sgst", "round_off", "grand_total"]
                    },
                    "line_items": [
                        {
                            "desc": it["description"]["value"],
                            "batch": it["batch"]["value"],
                            "qty": it["quantity"]["value"],
                            "mrp": it["mrp"]["value"],
                            "amount": it["amount"]["value"],
                        }
                        for it in r["final"]["line_items"]
                    ]
                }
                for r in runs_data
            ]
        }, f, indent=2)

    print("\nAll 3 runs completed successfully and artifacts saved to test_fixtures/batch_2/")

if __name__ == "__main__":
    main()
