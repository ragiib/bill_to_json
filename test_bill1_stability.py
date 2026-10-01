import json
import os
import sys
import time
from pathlib import Path

from app.gemini_client import parse_bill, get_gemini_model

def run_3_extractions(image_path: str):
    print(f"\n=======================================================")
    print(f"RUNNING 3 CONSECUTIVE EXTRACTIONS VIA parse_bill ON: {image_path}")
    print(f"MODEL: {get_gemini_model()}")
    print(f"=======================================================")

    p = Path(image_path)
    with open(p, "rb") as f:
        file_bytes = f.read()

    ext = p.suffix.lower().lstrip(".")
    mime_type = "image/jpeg" if ext in ["jpg", "jpeg"] else "image/png"

    results = []
    sums = []

    for i in range(1, 4):
        print(f"\n--- RUN {i} of 3 ---")
        try:
            res = parse_bill([(file_bytes, mime_type)])
            items = res.get("line_items", [])
            amounts = [it["amount"]["value"] for it in items if it.get("amount") and it["amount"].get("value") is not None]
            total_sum = round(sum(amounts), 2)
            sums.append(total_sum)

            print(f"Run {i}: extracted {len(items)} items.")
            for idx, it in enumerate(items):
                desc = it.get("description", {}).get("value", "")
                qty = it.get("quantity", {}).get("value", "")
                rate = it.get("rate", {}).get("value", "")
                amt = it.get("amount", {}).get("value", "")
                print(f"  Item {idx+1}: {str(desc)[:25]:25} | Qty: {str(qty):5} | Rate: {str(rate):8} | Amt: {amt}")

            totals = res.get("totals", {})
            gt = totals.get("grand_total", {}).get("value")
            sub = totals.get("sub_total", {}).get("value")
            print(f"Run {i} Line Amounts Sum: {total_sum}")
            print(f"Run {i} Totals: SubTotal={sub}, GrandTotal={gt}")

            with open(f"bill_1_parsebill_run_{i}.json", "w", encoding="utf-8") as out_f:
                json.dump(res, out_f, indent=2)

        except Exception as e:
            print(f"Run {i} FAILED with exception: {e}")
            sums.append(None)

        if i < 3:
            time.sleep(3)  # Brief pause between calls

    print("\n================== SUMMARY ACROSS 3 RUNS ==================")
    for i, s in enumerate(sums, 1):
        print(f"Run {i} sum(line amounts): {s}")
    return sums

if __name__ == "__main__":
    run_3_extractions("test_fixtures/bill_1.jpeg")
