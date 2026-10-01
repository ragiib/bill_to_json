import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.WARNING)
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.gemini_client import parse_bill, validate_gemini_config

BILLS = [
    ("bill_1.jpeg", "image/jpeg"),
    ("page1.jpeg", "image/jpeg"),
]
RESULTS_DIR = PROJECT_ROOT / "test_fixtures" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def fv(v):
    if v is None:
        return "None"
    if isinstance(v, (int, float)):
        return f"{v:.2f}"
    return str(v)


validate_gemini_config()

for fn, mime in BILLS:
    bill_path = PROJECT_ROOT / "test_fixtures" / fn
    with open(bill_path, "rb") as f:
        file_bytes = f.read()

    result = parse_bill([(file_bytes, mime)])

    out = RESULTS_DIR / f"{bill_path.stem}_latest.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")

    flags = result.get("flags", [])
    items = result.get("line_items", [])
    status = result["status"]
    conf = result["overall_confidence"]

    print()
    print("=" * 80)
    print(f"BILL: {fn}")
    print(f"STATUS: {status} | OVERALL_CONFIDENCE: {conf:.4f} | FLAGS_COUNT: {len(flags)}")
    print(f"SAVED: {out.relative_to(PROJECT_ROOT)}")
    if flags:
        print("FLAGS:")
        for flag in flags:
            print(f"  * {flag}")

    hdr = (
        f"{'#':<3} | {'Description':<34} | {'MRP':<9} | {'Rate':<9} | "
        f"{'Net Rate':<9} | {'Taxable':<9} | {'Amount':<9} | {'Qty':<5} | {'Disc%':<7} | {'Disc src'}"
    )
    print()
    print("LINE ITEMS:")
    print(hdr)
    print("-" * len(hdr))

    for i, item in enumerate(items, 1):
        desc = (item.get("description", {}).get("value") or "")[:34]
        mrp = fv(item.get("mrp", {}).get("value"))
        rate = fv(item.get("rate", {}).get("value"))
        net_rate = fv(item.get("net_rate", {}).get("value"))
        taxable = fv(item.get("taxable_value", {}).get("value"))
        amount = fv(item.get("amount", {}).get("value"))
        qty = fv(item.get("quantity", {}).get("value"))
        disc = fv(item.get("discount_pct", {}).get("value"))
        disc_src = item.get("discount_pct", {}).get("source_column") or ""
        print(
            f"{i:<3} | {desc:<34} | {mrp:<9} | {rate:<9} | "
            f"{net_rate:<9} | {taxable:<9} | {amount:<9} | {qty:<5} | {disc:<7} | {disc_src}"
        )

print()
print("Done.")
