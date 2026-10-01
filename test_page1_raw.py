import json
import os
import sys
from pathlib import Path
from google import genai
from google.genai import types

from app.gemini_client import EXTRACTION_SYSTEM_PROMPT, validate_gemini_config, get_gemini_model
from app.models import BillParseResponse

def run_page1_raw_test():
    api_key = validate_gemini_config()
    model_name = get_gemini_model()
    client = genai.Client(api_key=api_key)

    p = Path("test_fixtures/page1.jpeg")
    with open(p, "rb") as f:
        file_bytes = f.read()

    contents = [
        types.Part.from_bytes(data=file_bytes, mime_type="image/jpeg"),
        "Extract all pharmacy bill data across all provided page(s) according to the schema instructions."
    ]

    # Current config as defined in app/gemini_client.py
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=BillParseResponse,
        media_resolution=types.MediaResolution.MEDIA_RESOLUTION_HIGH,
        system_instruction=EXTRACTION_SYSTEM_PROMPT,
        temperature=0.1,
    )

    print("Calling Gemini API for page1.jpeg...")
    response = client.models.generate_content(
        model=model_name,
        contents=contents,
        config=config,
    )

    print("\n================== RAW GEMINI RESPONSE TEXT (TOTALS SECTION ONLY) ==================")
    raw_json_str = response.text
    raw_dict = json.loads(raw_json_str)

    raw_totals = raw_dict.get("totals", {})
    print(json.dumps(raw_totals, indent=2))

    print("\n================== RAW GEMINI FULL RESPONSE KEYS ==================")
    print("Keys in raw response:", list(raw_dict.keys()))
    print("Number of line items in raw response:", len(raw_dict.get("line_items", [])))
    print("Flags in raw response:", raw_dict.get("flags", []))

    # Save raw response to scratch file
    with open("page1_raw_response.json", "w", encoding="utf-8") as f:
        f.write(raw_json_str)
    print("\nSaved full raw response to page1_raw_response.json")

if __name__ == "__main__":
    run_page1_raw_test()
