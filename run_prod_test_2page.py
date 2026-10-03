"""
Two-page production simulation test.
Sends a real multipart POST to the running FastAPI server with BOTH pages
of Invoice 443TB2035938 attached under the same files[] field.
"""
import json
import time
from pathlib import Path

import requests

SERVER = "http://127.0.0.1:8000"
PAGE1 = Path("test_fixtures/last_test.jpeg")
PAGE2 = Path("test_fixtures/last_test_page2.jpeg")
OUT_PATH = Path("test_fixtures/results/final_prod_test_2page.json")
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

print("=" * 60)
print("GET /healthz")
health = requests.get(f"{SERVER}/healthz", timeout=10)
print(f"  HTTP {health.status_code}: {health.text}")
assert health.status_code == 200
print()

print("=" * 60)
print("POST /api/v1/parse-bill  [2-page multipart]")
print(f"  Page 1 : {PAGE1}  ({PAGE1.stat().st_size:,} bytes)")
print(f"  Page 2 : {PAGE2}  ({PAGE2.stat().st_size:,} bytes)")
print()

p1_bytes = PAGE1.read_bytes()
p2_bytes = PAGE2.read_bytes()

t_start = time.perf_counter()
resp = requests.post(
    f"{SERVER}/api/v1/parse-bill",
    files=[
        ("files", (PAGE1.name, p1_bytes, "image/jpeg")),
        ("files", (PAGE2.name, p2_bytes, "image/jpeg")),
    ],
    timeout=300,
)
elapsed = time.perf_counter() - t_start

print(f"HTTP Status Code : {resp.status_code}")
print(f"Response Time    : {elapsed:.2f}s ({elapsed*1000:.0f}ms)")
print()

body = resp.json()
OUT_PATH.write_text(json.dumps(body, indent=2), encoding="utf-8")
print(f"Saved to: {OUT_PATH}")
print()
print("=" * 60)
print("FULL JSON RESPONSE BODY:")
print(json.dumps(body, indent=2))
