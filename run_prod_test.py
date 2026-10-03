"""
Final production simulation test.
Sends a real multipart POST to the running FastAPI server and records:
  - GET /healthz result
  - POST /api/v1/parse-bill response (status code, body, elapsed time)
"""
import json
import time
from pathlib import Path

import requests

SERVER = "http://127.0.0.1:8000"
IMAGE_PATH = Path("test_fixtures/last_test.jpeg")
OUT_PATH = Path("test_fixtures/results/final_prod_test.json")
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

# Step 1: GET /healthz
print("=" * 60)
print("STEP 1: GET /healthz")
health_resp = requests.get(f"{SERVER}/healthz", timeout=10)
print(f"  HTTP {health_resp.status_code}: {health_resp.text}")
assert health_resp.status_code == 200, f"/healthz returned {health_resp.status_code}"
print("  /healthz: PASS — server is up and healthy")
print()

# Step 2: POST /api/v1/parse-bill
print("=" * 60)
print("STEP 2: POST /api/v1/parse-bill")
print(f"  File : {IMAGE_PATH}")
print(f"  Size : {IMAGE_PATH.stat().st_size:,} bytes")
print()

with open(IMAGE_PATH, "rb") as f:
    file_bytes = f.read()

t_start = time.perf_counter()
parse_resp = requests.post(
    f"{SERVER}/api/v1/parse-bill",
    files={"files": (IMAGE_PATH.name, file_bytes, "image/jpeg")},
    timeout=300,
)
elapsed_ms = (time.perf_counter() - t_start) * 1000

print(f"  HTTP Status Code : {parse_resp.status_code}")
print(f"  Response Time    : {elapsed_ms / 1000:.2f}s ({elapsed_ms:.0f}ms)")
print()

body = parse_resp.json()

# Save to file
with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(body, f, indent=2)
print(f"  Saved to: {OUT_PATH}")
print()

# Print full raw JSON body
print("=" * 60)
print("FULL JSON RESPONSE BODY:")
print(json.dumps(body, indent=2))
print()

# Step 3: Analyse missing-totals and status
print("=" * 60)
print("ANALYSIS:")
model_used = body.get("model_version", "unknown")
print(f"  model_version     : {model_used}")
print(f"  status            : {body.get('status')}")
print(f"  overall_confidence: {body.get('overall_confidence')}")
flags = body.get("flags", [])
print(f"  flags_count       : {len(flags)}")

for fld in ["taxable_amount", "cgst_amount", "sgst_amount", "total_amount"]:
    print(f"  {fld:20s}: {body.get(fld)}")

missing_totals_flag = any("total" in f.lower() or "taxable" in f.lower() for f in flags)
print()
print(f"  Missing-totals flag present : {'YES' if missing_totals_flag else 'NO'}")
print(f"  Status is needs_review      : {'YES' if body.get('status') == 'needs_review' else 'NO'}")

if missing_totals_flag and body.get("status") == "needs_review":
    print("  => PASS: Missing-totals triggers needs_review correctly.")
elif missing_totals_flag:
    print("  => PARTIAL: Missing-totals flag present but status is NOT needs_review.")
else:
    totals_all_none = all(body.get(f) is None for f in ["taxable_amount", "cgst_amount", "sgst_amount", "total_amount"])
    if totals_all_none:
        print("  => WARN: Totals are null but no missing-totals flag was emitted.")
    else:
        print("  => INFO: Totals present — single-page bill with totals on this page.")

print()
print(f"  Items extracted: {len(body.get('items', []))}")
for idx, item in enumerate(body.get("items", []), 1):
    name = (item.get("medicine_name") or "")[:36]
    mrp  = item.get("mrp") or "None"
    rate = item.get("rate") or "None"
    disc = item.get("discount") or "None"
    batch= item.get("batch_number") or "None"
    exp  = item.get("expiry_date") or "None"
    print(f"  {idx:>2}. {name:<36} mrp={mrp:<8} rate={rate:<8} disc={disc:<6} batch={batch:<14} exp={exp}")
