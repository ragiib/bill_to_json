import json
import os
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.gemini_client import parse_bill, validate_gemini_config


def test_bill(image_path: str, bill_label: str):
    print(f"\n=======================================================")
    print(f"TESTING: {bill_label} ({image_path})")
    print(f"=======================================================")

    p = Path(image_path)
    if not p.is_file():
        print(f"ERROR: File not found: {image_path}")
        return None

    with open(p, "rb") as f:
        file_bytes = f.read()

    ext = p.suffix.lower().lstrip(".")
    mime_type = "image/jpeg" if ext in ["jpg", "jpeg"] else "image/png"

    try:
        result = parse_bill([(file_bytes, mime_type)])
        print("\n--- FULL EXTRACTED JSON RESPONSE ---")
        print(json.dumps(result, indent=2))

        # Save result to file for permanent record
        out_path = p.with_suffix(".extracted.json")
        with open(out_path, "w", encoding="utf-8") as out_f:
            json.dump(result, out_f, indent=2)
        print(f"\nSaved JSON result to: {out_path}")
        return result
    except Exception as exc:
        print(f"ERROR during parse_bill: {exc}")
        import traceback
        traceback.print_exc()
        return None


def main():
    try:
        validate_gemini_config()
    except RuntimeError as err:
        print(f"\n[CONFIGURATION REQUIRED] {err}")
        print("Please set your GEMINI_API_KEY in .env or run with GEMINI_API_KEY=... python run_real_bills_test.py")
        sys.exit(2)

    bill1_path = "test_fixtures/bill_1.jpeg"
    page1_path = "test_fixtures/page1.jpeg"

    res_bill1 = test_bill(bill1_path, "bill_1.jpeg (Jyotsna Medical Agency)")
    res_page1 = test_bill(page1_path, "page1.jpeg (Sastasundar Healthbuddy)")


if __name__ == "__main__":
    main()
