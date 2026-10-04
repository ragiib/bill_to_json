import os
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_healthz():
    print("Testing GET /healthz without any auth...")
    response = client.get("/healthz")
    print(f"Status: {response.status_code}, Body: {response.json()}")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    print("PASS: /healthz is unauthenticated and returns 200 OK.")

def test_missing_api_key():
    print("\nTesting POST /api/v1/parse-bill WITHOUT X-API-Key header...")
    response = client.post(
        "/api/v1/parse-bill",
        files=[("files", ("test.jpeg", b"dummy content", "image/jpeg"))],
    )
    print(f"Status: {response.status_code}, Body: {response.json()}")
    assert response.status_code == 401
    assert response.json() == {"error": "unauthorized", "detail": "Missing or invalid API key"}
    print("PASS: Request without header rejected with 401 Unauthorized.")

def test_invalid_api_key():
    print("\nTesting POST /api/v1/parse-bill WITH WRONG X-API-Key header...")
    response = client.post(
        "/api/v1/parse-bill",
        headers={"X-API-Key": "completely_wrong_key_12345"},
        files=[("files", ("test.jpeg", b"dummy content", "image/jpeg"))],
    )
    print(f"Status: {response.status_code}, Body: {response.json()}")
    assert response.status_code == 401
    assert response.json() == {"error": "unauthorized", "detail": "Missing or invalid API key"}
    print("PASS: Request with wrong key rejected with 401 Unauthorized.")

def test_valid_api_key_real_bill():
    api_key = os.getenv("OUR_API_KEY")
    print(f"\nTesting POST /api/v1/parse-bill WITH CORRECT X-API-Key header ({api_key[:8]}...)...")
    page1_path = "test_fixtures/last_test.jpeg"
    page2_path = "test_fixtures/last_test_page2.jpeg"
    
    with open(page1_path, "rb") as f1, open(page2_path, "rb") as f2:
        files = [
            ("files", ("last_test.jpeg", f1.read(), "image/jpeg")),
            ("files", ("last_test_page2.jpeg", f2.read(), "image/jpeg")),
        ]
        
    response = client.post(
        "/api/v1/parse-bill",
        headers={"X-API-Key": api_key},
        files=files,
    )
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Supplier: {data.get('supplier_name')}")
    print(f"Items count: {len(data.get('items', []))}")
    print(f"Taxable amount: {data.get('taxable_amount')}")
    print(f"Total amount: {data.get('total_amount')}")
    print(f"Status: {data.get('status')}")
    print(f"Flags: {data.get('flags')}")
    assert response.status_code == 200
    assert len(data.get('items', [])) == 26
    print("PASS: Request with correct API key succeeded and parsed bill properly.")

if __name__ == "__main__":
    test_healthz()
    test_missing_api_key()
    test_invalid_api_key()
    test_valid_api_key_real_bill()
    print("\nALL LOCAL AUTH TESTS PASSED SUCCESSFULLY!")
