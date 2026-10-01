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
logger = logging.getLogger("flash_check")

IMAGE_PATH = Path("test_fixtures/new_bill.jpg")

def check_rotation(image_bytes: bytes, mime_type: str):
    img = Image.open(IMAGE_PATH)
    exif = img.getexif()
    exif_tag = exif.get(274) if exif else None
    
    engine = get_orientation_engine()
    rgb_img = img.convert("RGB")
    img_np = np.array(rgb_img)
    angle_str, elapse = engine(img_np)
    angle = int(angle_str)
    
    norm_bytes, norm_mime, applied_deg = normalize_image_orientation(image_bytes, mime_type)
    return norm_bytes, norm_mime, applied_deg, exif_tag, angle, elapse

def process_guardrails_and_reconciliation(raw_dict: dict, model_name: str, page_count: int = 1):
    parsed = BillParseResponse.model_validate(raw_dict)
    
    # 5. Apply Confidence Guardrails:
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

    # 6. Gather all ExtractedField instances to compute overall_confidence
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

    # 8. Reconciliation
    parsed = reconcile(parsed)
    return parsed

def main():
    api_key = validate_gemini_config()
    model_name = get_gemini_model()
    print("Exact GEMINI_MODEL value being used:", model_name)
    assert model_name == "gemini-2.5-flash", f"Model must be gemini-2.5-flash, got {model_name}"

    with open(IMAGE_PATH, "rb") as f:
        file_bytes = f.read()
    mime_type = "image/jpeg"

    # Rotation check
    norm_bytes, norm_mime, applied_deg, exif_tag, detected_angle, elapse = check_rotation(file_bytes, mime_type)
    print(f"EXIF tag: {exif_tag}")
    print(f"RapidOrientation detected angle: {detected_angle} deg (time: {elapse:.4f}s)")
    print(f"Rotation applied: {applied_deg} deg")
    print(f"Rotation triggered: {applied_deg != 0}")

    client = genai.Client(api_key=api_key)

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

    for run_idx in range(1, 4):
        print(f"\n=================== RUN {run_idx} STARTING ===================")
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

        # Post-process through guardrails & reconciliation
        final_response = process_guardrails_and_reconciliation(raw_dict, model_name)
        final_dict = final_response.model_dump()

        runs_data.append({
            "run": run_idx,
            "duration": duration,
            "raw_text": raw_text,
            "raw_dict": raw_dict,
            "final_dict": final_dict,
        })

    # Save Run 1 final output to test_fixtures/[bill_name]_flash_result.json
    # Here bill_name is new_bill
    out_file = Path("test_fixtures/new_bill_flash_result.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(runs_data[0]["final_dict"], f, indent=2)
    print(f"\nSaved Run 1 final output to {out_file}")

    # Also save raw outputs and full runs summary for complete tracking
    for r in runs_data:
        idx = r["run"]
        with open(f"test_fixtures/new_bill_raw_run_{idx}.json", "w", encoding="utf-8") as f:
            json.dump(r["raw_dict"], f, indent=2)
        with open(f"test_fixtures/new_bill_final_run_{idx}.json", "w", encoding="utf-8") as f:
            json.dump(r["final_dict"], f, indent=2)

    # Save summary json
    summary_data = {
        "model": model_name,
        "exif_tag": exif_tag,
        "detected_angle": detected_angle,
        "applied_rotation": applied_deg,
        "rotation_triggered": applied_deg != 0,
        "runs": [
            {
                "run": r["run"],
                "duration": r["duration"],
                "status": r["final_dict"]["status"],
                "overall_confidence": r["final_dict"]["overall_confidence"],
                "flags": r["final_dict"]["flags"],
                "totals": {
                    k: r["final_dict"]["totals"][k]["value"]
                    for k in r["final_dict"]["totals"]
                },
                "line_items_count": len(r["final_dict"]["line_items"]),
                "line_items": [
                    {
                        "desc": item["description"]["value"],
                        "batch": item["batch"]["value"],
                        "qty": item["quantity"]["value"],
                        "mrp": item["mrp"]["value"],
                        "rate": item["rate"]["value"],
                        "taxable_value": item["taxable_value"]["value"],
                        "cgst_pct": item["cgst_pct"]["value"],
                        "sgst_pct": item["sgst_pct"]["value"],
                        "amount": item["amount"]["value"],
                    }
                    for item in r["final_dict"]["line_items"]
                ]
            }
            for r in runs_data
        ]
    }
    with open("test_fixtures/new_bill_runs_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2)
    print("Saved runs summary to test_fixtures/new_bill_runs_summary.json")

if __name__ == "__main__":
    main()
