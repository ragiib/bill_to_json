import json
import logging
import os
import sys
import time
from pathlib import Path

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.gemini_client import parse_bill, validate_gemini_config, get_gemini_model

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("task4_verification")

BILLS = [
    ("new_bill", "test_fixtures/new_bill.jpg"),
    ("bill_1", "test_fixtures/bill_1.jpeg"),
    ("page1", "test_fixtures/page1.jpeg"),
]

OUT_DIR = Path("test_fixtures/verification_results")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def run_bill_runs(bill_key: str, bill_path_str: str, num_runs: int = 3):
    bill_path = Path(bill_path_str)
    if not bill_path.is_file():
        raise FileNotFoundError(f"Bill file not found: {bill_path}")

    with open(bill_path, "rb") as f:
        file_bytes = f.read()

    ext = bill_path.suffix.lower().lstrip(".")
    mime_type = "image/jpeg" if ext in ["jpg", "jpeg"] else "image/png"

    results = []

    print(f"\n{'='*70}")
    print(f"RUNNING VERIFICATION FOR: {bill_key} ({bill_path_str}) - {num_runs} RUNS")
    print(f"{'='*70}")

    for r in range(1, num_runs + 1):
        print(f"\n--- {bill_key} RUN {r}/{num_runs} ---")
        t0 = time.time()
        parsed_dict = parse_bill([(file_bytes, mime_type)])
        elapsed = time.time() - t0
        print(f"Completed run {r} in {elapsed:.2f}s | Status: {parsed_dict['status']} | Confidence: {parsed_dict['overall_confidence']}")

        out_file = OUT_DIR / f"{bill_key}_run_{r}.json"
        with open(out_file, "w", encoding="utf-8") as out_f:
            json.dump(parsed_dict, out_f, indent=2)

        results.append({
            "run": r,
            "elapsed": elapsed,
            "parsed": parsed_dict
        })

    return results


def analyze_new_bill(runs):
    print(f"\n{'='*70}")
    print(f"ANALYSIS: new_bill.jpg (5-column bill)")
    print(f"{'='*70}")
    for res in runs:
        r = res["run"]
        parsed = res["parsed"]
        line_items = parsed.get("line_items", [])
        flags = parsed.get("flags", [])
        status = parsed.get("status")

        print(f"\n[Run {r}] Status: {status} | Total Line Items: {len(line_items)}")
        if line_items:
            row1 = line_items[0]
            mrp = row1.get("mrp", {})
            rate = row1.get("rate", {})
            net_rate = row1.get("net_rate", {})
            taxable = row1.get("taxable_value", {})
            disc = row1.get("discount_pct", {})
            desc = row1.get("description", {}).get("value", "")

            print(f"  Row 1 Description: {desc}")
            print(f"  Row 1 mrp:        value={mrp.get('value')} | raw={mrp.get('raw')} | source_column={mrp.get('source_column')}")
            print(f"  Row 1 rate:       value={rate.get('value')} | raw={rate.get('raw')} | source_column={rate.get('source_column')}")
            print(f"  Row 1 net_rate:   value={net_rate.get('value')} | raw={net_rate.get('raw')} | source_column={net_rate.get('source_column')}")
            print(f"  Row 1 disc_pct:   value={disc.get('value')} | raw={disc.get('raw')} | source_column={disc.get('source_column')}")
            print(f"  Row 1 taxable:    value={taxable.get('value')} | raw={taxable.get('raw')} | source_column={taxable.get('source_column')}")

            reconciliation_flags = [f for f in flags if "reconciliation:" in f or "does not reconcile" in f]
            print(f"  Reconciliation Flags Count: {len(reconciliation_flags)}")

        print(f"  Full Flags ({len(flags)} total):")
        for f in flags:
            print(f"    - {f}")


def analyze_null_net_rate_bill(bill_name: str, runs):
    print(f"\n{'='*70}")
    print(f"ANALYSIS: {bill_name}")
    print(f"{'='*70}")
    for res in runs:
        r = res["run"]
        parsed = res["parsed"]
        line_items = parsed.get("line_items", [])
        flags = parsed.get("flags", [])
        status = parsed.get("status")

        net_rate_non_null = [
            (idx, item.get("net_rate", {}).get("value"))
            for idx, item in enumerate(line_items)
            if item.get("net_rate", {}).get("value") is not None
        ]

        print(f"\n[Run {r}] Status: {status} | Total Line Items: {len(line_items)}")
        print(f"  Non-null net_rate count across all items: {len(net_rate_non_null)}")
        if net_rate_non_null:
            print(f"  WARNING: Non-null net_rate items found: {net_rate_non_null}")
        else:
            print(f"  CONFIRMED: net_rate is null throughout all {len(line_items)} line items.")

        reconciliation_flags = [f for f in flags if "reconciliation:" in f or "does not reconcile" in f]
        print(f"  Reconciliation Flags Count: {len(reconciliation_flags)}")
        print(f"  Full Flags ({len(flags)} total):")
        for f in flags:
            print(f"    - {f}")


def main():
    validate_gemini_config()
    model = get_gemini_model()
    print(f"Gemini Model: {model}")

    all_data = {}

    for bill_key, bill_path in BILLS:
        runs = run_bill_runs(bill_key, bill_path, num_runs=3)
        all_data[bill_key] = runs

    analyze_new_bill(all_data["new_bill"])
    analyze_null_net_rate_bill("bill_1.jpeg", all_data["bill_1"])
    analyze_null_net_rate_bill("page1.jpeg", all_data["page1"])

    summary_file = OUT_DIR / "task4_summary.json"
    serializable = {}
    for k, runs in all_data.items():
        serializable[k] = [
            {
                "run": r["run"],
                "elapsed": r["elapsed"],
                "status": r["parsed"]["status"],
                "overall_confidence": r["parsed"]["overall_confidence"],
                "flags": r["parsed"]["flags"],
                "line_items_count": len(r["parsed"]["line_items"]),
                "row_1": r["parsed"]["line_items"][0] if r["parsed"]["line_items"] else None,
            }
            for r in runs
        ]
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(serializable, f, indent=2)
    print(f"\nSaved summary to: {summary_file}")


if __name__ == "__main__":
    main()
