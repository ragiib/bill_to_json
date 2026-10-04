# Pharmacy Bill Intelligence API

A high-performance, stateless REST service built with FastAPI and Google Gemini, designed for automated extraction of structured data from Indian pharmacy and wholesale medical bills. Deployed as a containerized service on **Render**.

---

## Key Features

- **Stateless & Synchronous**: Accepts one or more pages of a single invoice, calls Google Gemini once with all pages, and immediately returns structured JSON in the HTTP response.
- **Multi-Page Continuity**: Reconstructs line-item tables spanning multiple pages into a single unified invoice list.
- **Strict No-Guessing Policy**: Unclear or obscured values are set to `null` with lowered confidence (< 0.6) and flagged in the `flags` array rather than invented.
- **Old vs. Current MRP Disambiguation**: Intelligently extracts the active/effective price for `mrp.value` while keeping verbatim visual text in `mrp.raw`.
- **High-Resolution Multimodal Extraction**: Operates Gemini with `media_resolution=MEDIA_RESOLUTION_HIGH` for deciphering fine print in batch numbers and expiry dates.
- **Per-Field Confidence**: Every extracted field carries `value`, `raw`, and `confidence`. Overall confidence averages all fields without omitting failed extractions.

---

## Project Structure

```text
.
├── app/
│   ├── __init__.py
│   ├── main.py             # FastAPI app, lifespan validation, and /healthz
│   ├── models.py           # Pydantic schemas (ExtractedField, BillParseResponse, etc.)
│   ├── gemini_client.py    # Google GenAI SDK integration, prompts, retries, and confidence
│   └── routers/
│       ├── __init__.py
│       └── parse.py        # POST /api/v1/parse-bill multi-file endpoint
├── test_fixtures/          # Local directory for test bill images
├── .env.example            # Sample configuration file
├── Dockerfile              # Cloud Run production container definition
├── requirements.txt        # fastapi, uvicorn, python-multipart, pydantic, google-genai
└── README.md
```

---

## Configuration

Set the following variables in your `.env` file or environment:

```ini
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.5-flash-lite
OUR_API_KEY=your_secure_api_key_here
```

- `GEMINI_API_KEY`: Required. Google Gemini API key, validated on startup.
- `GEMINI_MODEL`: Optional (defaults to `gemini-2.5-flash`). Allows overriding the Gemini Flash model string (e.g. `gemini-3.5-flash-lite`).
- `OUR_API_KEY`: Required. Secret API key used for authenticating incoming requests to `/api/v1/parse-bill`.

---

## Running Locally

### 1. Setup Environment
```bash
# Windows
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt

# Linux / macOS
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Start the API Server
```bash
uvicorn app.main:app --reload --port 8080
```

- **Swagger Documentation**: [http://localhost:8080/docs](http://localhost:8080/docs)
- **ReDoc UI**: [http://localhost:8080/redoc](http://localhost:8080/redoc)

---

## API Reference

### 1. Parse Bill
`POST /api/v1/parse-bill`

Uploads one or more images or PDF pages representing all pages of a single pharmacy bill.

- **Authentication**: **Required**. Every request to `/api/v1/parse-bill` must include the header:
  ```http
  X-API-Key: <OUR_API_KEY>
  ```
  Missing or invalid API key will immediately return `401 Unauthorized`:
  ```json
  {"error": "unauthorized", "detail": "Missing or invalid API key"}
  ```
  This check executes prior to reading payload bytes or calling Gemini, ensuring unauthorized requests do not consume bandwidth or quota.

- **Request Type**: `multipart/form-data`
- **Field Name**: `files` (supports multiple files)
- **Constraints**:
  - Allowed file types: `.jpg`, `.jpeg`, `.png`, `.pdf`
  - Per-file size limit: `15MB`
  - Total request size cap: `50MB` across all files combined

#### Example Request (Multi-Page Bill)
```bash
curl -X POST "http://localhost:8080/api/v1/parse-bill" \
  -H "X-API-Key: your_secure_api_key_here" \
  -F "files=@page1.png" \
  -F "files=@page2.png"
```

#### Response Structure (200 OK)
```json
{
  "status": "completed",
  "overall_confidence": 0.94,
  "page_count": 2,
  "pharmacy": {
    "name": {"value": "Apollo Pharmacy", "raw": "APOLLO PHARMACY", "confidence": 0.98},
    "address": {"value": "MG Road, Bengaluru", "raw": "MG Road, Bengaluru - 560001", "confidence": 0.95},
    "gstin": {"value": "29ABCDE1234F1Z5", "raw": "GSTIN: 29ABCDE1234F1Z5", "confidence": 0.99},
    "dl_no": {"value": "KA-B1-12345", "raw": "DL: KA-B1-12345", "confidence": 0.96}
  },
  "invoice": {
    "invoice_number": {"value": "INV-2026-001", "raw": "Inv No: INV-2026-001", "confidence": 0.99},
    "invoice_date": {"value": "2026-09-14", "raw": "14/09/2026", "confidence": 0.98},
    "order_no": {"value": "ORD-991", "raw": "PO: ORD-991", "confidence": 0.93}
  },
  "line_items": [
    {
      "description": {"value": "Augmentin 625 Duo Tablet", "raw": "AUGMENTIN 625 DUO", "confidence": 0.96},
      "hsn_code": {"value": "3004", "raw": "3004", "confidence": 0.95},
      "quantity": {"value": 10.0, "raw": "10 TAB", "confidence": 0.98},
      "unit": {"value": "TAB", "raw": "TAB", "confidence": 0.95},
      "batch": {"value": "AUG202", "raw": "B.No: AUG202", "confidence": 0.94},
      "expiry_date": {"value": "11/27", "raw": "EXP 11/27", "confidence": 0.93},
      "mrp": {"value": 204.50, "raw": "MRP 204.50", "confidence": 0.97},
      "rate": {"value": 163.60, "raw": "163.60", "confidence": 0.96},
      "discount_pct": {"value": 0.0, "raw": null, "confidence": 1.0},
      "taxable_value": {"value": 1636.00, "raw": "1636.00", "confidence": 0.97},
      "cgst_pct": {"value": 6.0, "raw": "6%", "confidence": 0.99},
      "sgst_pct": {"value": 6.0, "raw": "6%", "confidence": 0.99},
      "amount": {"value": 1832.32, "raw": "1832.32", "confidence": 0.97}
    }
  ],
  "totals": {
    "sub_total": {"value": 1636.00, "raw": "1636.00", "confidence": 0.97},
    "total_cgst": {"value": 98.16, "raw": "98.16", "confidence": 0.98},
    "total_sgst": {"value": 98.16, "raw": "98.16", "confidence": 0.98},
    "round_off": {"value": 0.0, "raw": "0.00", "confidence": 1.0},
    "grand_total": {"value": 1832.32, "raw": "1832.32", "confidence": 0.99}
  },
  "flags": [],
  "model_version": "gemini-2.5-flash"
}
```

#### Error Responses
- Missing or invalid API key (401 Unauthorized):
  ```json
  {"error": "unauthorized", "detail": "Missing or invalid API key"}
  ```
- Unsupported file type (400 Bad Request):
  ```json
  {"error": "unsupported_file_type", "detail": "File 'notes.txt' has invalid type 'txt'. Allowed file types are: jpeg, jpg, pdf, png."}
  ```
- File too large (400 Bad Request):
  ```json
  {"error": "file_too_large", "detail": "File 'big.pdf' exceeds maximum allowed limit of 15MB. Received 15794176 bytes."}
  ```
- Request too large (400 Bad Request):
  ```json
  {"error": "request_too_large", "detail": "Total request size (52428800 bytes) exceeds maximum limit of 50MB across all pages."}
  ```

---

### 2. Health Check
`GET /healthz`

Returns `200 OK` with `{"status": "ok"}`. Open and unauthenticated for container liveness and readiness probes.

---

## Deployment to Render

This service is containerized via Docker and can be deployed to [Render](https://render.com) (no credit card required on the free tier, with 750 free instance-hours/month).

### Option A: Using Render Blueprints (render.yaml)
1. Push your repository to GitHub.
2. In the [Render Dashboard](https://dashboard.render.com), click **New +** > **Blueprint**.
3. Connect your GitHub repository (`bill_to_json`). Render will automatically detect [`render.yaml`](file:///c:/bill_to_JSON/render.yaml).
4. Render will prompt you for the secret environment variables marked `sync: false`:
   - `GEMINI_API_KEY`: Your Google Gemini API key.
   - `OUR_API_KEY`: Your secure API key generated for `/api/v1/parse-bill`.
5. Click **Apply** to deploy.

### Option B: Manual Web Service Setup
1. In the [Render Dashboard](https://dashboard.render.com), click **New +** > **Web Service**.
2. Connect your GitHub repository or enter `https://github.com/ragiib/bill_to_json`.
3. Configure the service:
   - **Name**: `pharmacy-bill-api` (or preferred name)
   - **Region**: Oregon (or nearest region)
   - **Branch**: `main`
   - **Runtime**: `Docker`
   - **Instance Type**: `Free`
   - **Health Check Path**: `/healthz`
4. Add the following **Environment Variables** (encrypted secrets):
   - `GEMINI_API_KEY`: `<your_gemini_api_key>`
   - `GEMINI_MODEL`: `gemini-3.5-flash-lite`
   - `OUR_API_KEY`: `<your_generated_api_key>`
5. Click **Create Web Service**.

### Free-Tier Behavior & Client Timeouts (Important)
- **Automatic Inactivity Sleep**: Render's free tier spins down (sleeps) after **15 minutes of inactivity**.
- **Cold Start Delay**: The first request received after the service sleeps takes approximately **50–70 seconds** while Render provisions the container and boots the application. Subsequent requests while the container is warm respond in normal time (~3–6 seconds).
- **Client Timeout Recommendation**: Any client application, frontend, or backend consuming this API should configure an HTTP request timeout of **at least 90 seconds** (`timeout=90.0` or higher) to avoid prematurely dropping connections during cold starts.
