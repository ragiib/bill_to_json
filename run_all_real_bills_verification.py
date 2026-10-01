import json
import logging
import sys
from pathlib import Path

# Silence verbose logging
logging.basicConfig(level=logging.WARNING)

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.gemini_client import parse_bill, validate_gemini_config

BILLS = [
    ("test_fixtures/bill_1.jpeg", "bill_1.jpeg (Jyotsna Medical Agency)"),
    ("test_fixtures/batch_2/test_bill.jpeg", "batch_2/test_bill.jpeg (Sastasundar Healthbuddy - TB2037025)"),
    ("test_fixtures/page1.jpeg", "page1.jpeg (Sastasundar Healthbuddy - 443TB1904436)"),
    ("test_fixtures/new_bill.jpg", "new_bill.jpg (Sastasundar Healthbuddy - 443TB2028895)"),
]

def main():
    validate_gemini_config()
    results = {}

    for rel_path, label in BILLS:
        full_path = PROJECT_ROOT / rel_path
        if not full_path.is_file():
            print(f"File not found: {full_path}")
            continue

        ext = full_path.suffix.lower().lstrip(".")
        mime_type = "image/jpeg" if ext in ["jpg", "jpeg"] else "image/png"

        print(f"\n=======================================================")
        print(f"RUNNING: {label}")
        print(f"=======================================================")

        with open(full_path, "rb") as f:
            file_bytes = f.read()

        res = parse_bill([(file_bytes, mime_type)])
        results[rel_path] = res

        out_file = PROJECT_ROOT / "test_fixtures" / f"{full_path.stem}_new_shape.json"
        with open(out_file, "w", encoding="utf-8") as out_f:
            json.dump(res, out_f, indent=2)

        print(f"Status: {res.get('status')}")
        print(f"Overall Confidence: {res.get('overall_confidence')}")
        print(f"Flags: {res.get('flags')}")
        print(f"Saved: {out_file.name}")

    print("\nALL RUNS COMPLETE.")

if __name__ == "__main__":
    main()
