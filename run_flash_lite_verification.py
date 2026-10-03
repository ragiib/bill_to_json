import json
import logging
import os
import sys
from pathlib import Path

# Override GEMINI_MODEL in-memory before loading client
os.environ["GEMINI_MODEL"] = "gemini-3.5-flash-lite"

# Silence verbose informational logs during script execution
logging.basicConfig(level=logging.WARNING)

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.gemini_client import parse_bill, validate_gemini_config

BILLS = [
    "bill_1.jpeg",
    "page1.jpeg",
    "test_bill.jpeg",
    "new_bill.jpg",
]

RESULTS_DIR = PROJECT_ROOT / "test_fixtures" / "results"


def format_val(val):
    if val is None:
        return "None"
    return str(val)


def main():
    validate_gemini_config()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    for bill_rel in BILLS:
        bill_path = PROJECT_ROOT / "test_fixtures" / bill_rel
        if not bill_path.is_file():
            alt_path = PROJECT_ROOT / "test_fixtures" / "batch_2" / bill_rel
            if alt_path.is_file():
                bill_path = alt_path
            else:
                print(f"Error: {bill_path} not found.")
                continue

        ext = bill_path.suffix.lower().lstrip(".")
        mime_type = "image/jpeg" if ext in ["jpg", "jpeg"] else "image/png"

        with open(bill_path, "rb") as f:
            file_bytes = f.read()

        result = parse_bill([(file_bytes, mime_type)])

        stem = bill_path.stem
        out_path = RESULTS_DIR / f"{stem}_flashlite.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)

        status = result.get("status")
        confidence = result.get("overall_confidence", 0.0)
        flags = result.get("flags", [])
        items = result.get("items", [])

        print(f"\n================================================================================")
        print(f"BILL: {bill_rel}")
        print(f"SUPPLIER: {result.get('supplier_name')} | BILL NO: {result.get('bill_no')} | DATE: {result.get('bill_date')}")
        print(f"TAXABLE: {result.get('taxable_amount')} | CGST: {result.get('cgst_amount')} | SGST: {result.get('sgst_amount')} | TOTAL: {result.get('total_amount')}")
        print(f"STATUS: {status} | OVERALL_CONFIDENCE: {confidence:.4f} | FLAGS_COUNT: {len(flags)}")
        print(f"SAVED: {out_path.relative_to(PROJECT_ROOT)}")
        if flags:
            print("FLAGS:")
            for flag in flags:
                print(f"  * {flag}")

        print("\nITEMS:")
        header = f"{'#':<3} | {'Medicine Name':<34} | {'MRP':<8} | {'Qty':<5} | {'Rate':<8} | {'Disc':<6} | {'GST':<5} | {'Expiry':<7} | {'Batch':<10}"
        print(header)
        print("-" * len(header))

        for idx, item in enumerate(items, start=1):
            name = (item.get("medicine_name") or "")[:34]
            mrp = format_val(item.get("mrp"))
            qty = format_val(item.get("quantity"))
            rate = format_val(item.get("rate"))
            disc = format_val(item.get("discount"))
            gst = format_val(item.get("gst"))
            exp = format_val(item.get("expiry_date"))
            batch = format_val(item.get("batch_number"))

            print(f"{idx:<3} | {name:<34} | {mrp:<8} | {qty:<5} | {rate:<8} | {disc:<6} | {gst:<5} | {exp:<7} | {batch:<10}")

    print("\nVerification run complete.")


if __name__ == "__main__":
    main()
