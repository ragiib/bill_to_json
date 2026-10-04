import json
import os
import time
import httpx

LIVE_URL = "https://bill-to-json.onrender.com"
API_KEY = os.getenv("OUR_API_KEY", "R8qIi4IJ_Z19pcLQAU-N-NPlkHabWWJ9Q01T6YCXM6M")
PAGE1_PATH = "test_fixtures/last_test.jpeg"
PAGE2_PATH = "test_fixtures/last_test_page2.jpeg"

print(f"Target Live URL: {LIVE_URL}")
print(f"Using OUR_API_KEY: {API_KEY[:8]}...{API_KEY[-6:]}")

# Read the two bill images
with open(PAGE1_PATH, "rb") as f1, open(PAGE2_PATH, "rb") as f2:
    bytes_page1 = f1.read()
    bytes_page2 = f2.read()

print(f"Loaded Page 1 ({len(bytes_page1)} bytes) and Page 2 ({len(bytes_page2)} bytes).")

results = {}

# STEP 1: GET /healthz
print("\n" + "="*60)
print("STEP 1: Checking GET /healthz...")
print("="*60)
t0 = time.time()
r_health = httpx.get(f"{LIVE_URL}/healthz", timeout=120.0)
t_health = time.time() - t0
print(f"Status Code: {r_health.status_code}")
print(f"Response Body: {r_health.text}")
print(f"Elapsed Time: {t_health:.2f}s")
assert r_health.status_code == 200
results["healthz"] = {
    "status_code": r_health.status_code,
    "body": r_health.json(),
    "latency_seconds": round(t_health, 2)
}

# STEP 2 & 3: Cold Request with X-API-Key and both bill pages
print("\n" + "="*60)
print("STEP 2: Sending Cold Request (1st real extraction call) with X-API-Key...")
print("="*60)
files_payload = [
    ("files", ("last_test.jpeg", bytes_page1, "image/jpeg")),
    ("files", ("last_test_page2.jpeg", bytes_page2, "image/jpeg")),
]
t0 = time.time()
r_cold = httpx.post(
    f"{LIVE_URL}/api/v1/parse-bill",
    headers={"X-API-Key": API_KEY},
    files=files_payload,
    timeout=240.0,
)
t_cold = time.time() - t0
print(f"Status Code: {r_cold.status_code}")
print(f"Cold Request Latency: {t_cold:.2f}s")
try:
    cold_json = r_cold.json()
except Exception:
    cold_json = r_cold.text

results["cold_request"] = {
    "status_code": r_cold.status_code,
    "latency_seconds": round(t_cold, 2),
    "body": cold_json,
}

# STEP 4: Warm Request (2nd identical extraction call) right after
print("\n" + "="*60)
print("STEP 4: Sending Warm Request (2nd identical extraction call)...")
print("="*60)
files_payload_warm = [
    ("files", ("last_test.jpeg", bytes_page1, "image/jpeg")),
    ("files", ("last_test_page2.jpeg", bytes_page2, "image/jpeg")),
]
t0 = time.time()
r_warm = httpx.post(
    f"{LIVE_URL}/api/v1/parse-bill",
    headers={"X-API-Key": API_KEY},
    files=files_payload_warm,
    timeout=180.0,
)
t_warm = time.time() - t0
print(f"Status Code: {r_warm.status_code}")
print(f"Warm Request Latency: {t_warm:.2f}s")
try:
    warm_json = r_warm.json()
except Exception:
    warm_json = r_warm.text

results["warm_request"] = {
    "status_code": r_warm.status_code,
    "latency_seconds": round(t_warm, 2),
    "body": warm_json,
}

# STEP 5: Request WITHOUT X-API-Key header
print("\n" + "="*60)
print("STEP 5: Sending Request WITHOUT X-API-Key header...")
print("="*60)
files_payload_noauth = [
    ("files", ("last_test.jpeg", bytes_page1, "image/jpeg")),
    ("files", ("last_test_page2.jpeg", bytes_page2, "image/jpeg")),
]
t0 = time.time()
r_noauth = httpx.post(
    f"{LIVE_URL}/api/v1/parse-bill",
    files=files_payload_noauth,
    timeout=60.0,
)
t_noauth = time.time() - t0
print(f"Status Code: {r_noauth.status_code}")
print(f"Response Body: {r_noauth.text}")
print(f"Elapsed Time: {t_noauth:.2f}s")
results["no_key_request"] = {
    "status_code": r_noauth.status_code,
    "body": r_noauth.json() if r_noauth.headers.get("content-type") == "application/json" else r_noauth.text,
    "latency_seconds": round(t_noauth, 2),
}

# Save complete results
output_path = "test_fixtures/results/live_render_final_test.json"
os.makedirs(os.path.dirname(output_path), exist_ok=True)
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)

print("\n" + "="*60)
print("SUMMARY OF LIVE RENDER TESTS")
print("="*60)
print(f"1. GET /healthz: Status {r_health.status_code} ({t_health:.2f}s)")
print(f"2. Cold Request (Request 1): Status {r_cold.status_code} in {t_cold:.2f}s")
print(f"3. Warm Request (Request 2): Status {r_warm.status_code} in {t_warm:.2f}s")
print(f"4. Missing Key Request: Status {r_noauth.status_code} ({t_noauth:.2f}s)")
print(f"Results written to {output_path}")
