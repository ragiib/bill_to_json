import os
import sys
import time
import httpx

def run_live_tests(base_url: str, api_key: str):
    base_url = base_url.rstrip("/")
    print(f"=== TESTING LIVE DEPLOYMENT AT: {base_url} ===")
    
    # 1. Unauthenticated /healthz
    print("\n[1] Testing GET /healthz (unauthenticated)...")
    t0 = time.time()
    try:
        r_health = httpx.get(f"{base_url}/healthz", timeout=120.0)
        t_health = time.time() - t0
        print(f"Health Status: {r_health.status_code}, Body: {r_health.json()}, Latency: {t_health:.2f}s")
        assert r_health.status_code == 200, f"Expected 200, got {r_health.status_code}"
        assert r_health.json() == {"status": "ok"}
        print("PASS: /healthz is open and returned 200 OK.")
    except Exception as e:
        print(f"FAIL on /healthz: {e}")
        return False

    # 2. Reject request without X-API-Key header (401)
    print("\n[2] Testing POST /api/v1/parse-bill WITHOUT X-API-Key header...")
    t0 = time.time()
    try:
        r_no_auth = httpx.post(
            f"{base_url}/api/v1/parse-bill",
            files=[("files", ("test.jpeg", b"dummy content", "image/jpeg"))],
            timeout=30.0,
        )
        t_no_auth = time.time() - t0
        print(f"Status: {r_no_auth.status_code}, Body: {r_no_auth.json()}, Latency: {t_no_auth:.2f}s")
        assert r_no_auth.status_code == 401, f"Expected 401, got {r_no_auth.status_code}"
        assert r_no_auth.json() == {"error": "unauthorized", "detail": "Missing or invalid API key"}
        print("PASS: Missing header rejected with 401 Unauthorized.")
    except Exception as e:
        print(f"FAIL on missing key check: {e}")
        return False

    # 3. Reject request with invalid X-API-Key header (401)
    print("\n[3] Testing POST /api/v1/parse-bill WITH WRONG X-API-Key header...")
    try:
        r_bad_auth = httpx.post(
            f"{base_url}/api/v1/parse-bill",
            headers={"X-API-Key": "invalid_wrong_key_12345"},
            files=[("files", ("test.jpeg", b"dummy content", "image/jpeg"))],
            timeout=30.0,
        )
        print(f"Status: {r_bad_auth.status_code}, Body: {r_bad_auth.json()}")
        assert r_bad_auth.status_code == 401, f"Expected 401, got {r_bad_auth.status_code}"
        print("PASS: Invalid key rejected with 401 Unauthorized.")
    except Exception as e:
        print(f"FAIL on invalid key check: {e}")
        return False

    # 4. First extraction call (measures cold/initial response time)
    page1_path = "test_fixtures/last_test.jpeg"
    page2_path = "test_fixtures/last_test_page2.jpeg"
    with open(page1_path, "rb") as f1, open(page2_path, "rb") as f2:
        b1, b2 = f1.read(), f2.read()

    print("\n[4] Testing POST /api/v1/parse-bill WITH VALID KEY (Request 1 - Cold/Initial)...")
    t0 = time.time()
    try:
        files = [
            ("files", ("last_test.jpeg", b1, "image/jpeg")),
            ("files", ("last_test_page2.jpeg", b2, "image/jpeg")),
        ]
        r1 = httpx.post(
            f"{base_url}/api/v1/parse-bill",
            headers={"X-API-Key": api_key},
            files=files,
            timeout=180.0,
        )
        cold_time = time.time() - t0
        print(f"Status: {r1.status_code}, Latency: {cold_time:.2f}s")
        assert r1.status_code == 200, f"Expected 200, got {r1.status_code}: {r1.text}"
        data1 = r1.json()
        print(f"Supplier: {data1.get('supplier_name')}")
        print(f"Items count: {len(data1.get('items', []))}")
        print(f"Taxable amount: {data1.get('taxable_amount')}")
        print(f"Total amount: {data1.get('total_amount')}")
        print(f"Status: {data1.get('status')}")
        print(f"Flags: {data1.get('flags')}")
    except Exception as e:
        print(f"FAIL on request 1: {e}")
        return False

    # 5. Second extraction call (measures warm response time)
    print("\n[5] Testing POST /api/v1/parse-bill WITH VALID KEY (Request 2 - Warm)...")
    t0 = time.time()
    try:
        files = [
            ("files", ("last_test.jpeg", b1, "image/jpeg")),
            ("files", ("last_test_page2.jpeg", b2, "image/jpeg")),
        ]
        r2 = httpx.post(
            f"{base_url}/api/v1/parse-bill",
            headers={"X-API-Key": api_key},
            files=files,
            timeout=120.0,
        )
        warm_time = time.time() - t0
        print(f"Status: {r2.status_code}, Latency: {warm_time:.2f}s")
        assert r2.status_code == 200, f"Expected 200, got {r2.status_code}"
    except Exception as e:
        print(f"FAIL on request 2: {e}")
        return False

    print("\n=== SUMMARY OF LIVE TESTS ===")
    print(f"Live URL: {base_url}")
    print(f"Health Check (/healthz): PASS (200 OK)")
    print(f"401 Auth Rejection: PASS (Rejected missing & invalid keys)")
    print(f"Request 1 Latency: {cold_time:.2f}s")
    print(f"Request 2 (Warm) Latency: {warm_time:.2f}s")
    print(f"Item Count: {len(data1.get('items', []))} items")
    print(f"Taxable Amount: {data1.get('taxable_amount')}")
    print(f"Total Amount: {data1.get('total_amount')}")
    print(f"Reconciliation Status: {data1.get('status')}")
    return True

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else input("Enter live Render base URL: ")
    key = os.getenv("OUR_API_KEY", "R8qIi4IJ_Z19pcLQAU-N-NPlkHabWWJ9Q01T6YCXM6M")
    success = run_live_tests(url, key)
    sys.exit(0 if success else 1)
