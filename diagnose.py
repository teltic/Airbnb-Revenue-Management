"""One-off diagnostic: find the real PriceLabs overrides endpoint path.

Run with: python diagnose.py
Safe to delete afterward -- not part of the actual script.
"""

import os
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")
api_key = os.environ["PRICELABS_API_KEY"]
headers = {"X-API-Key": api_key}

listing_id = "dec5d2ed-4400-4350-8df3-af76b5d3d09c"
pms = "smartbnb"
base = "https://api.pricelabs.co/v1"

candidates = [
    ("GET", f"{base}/listing_data/{listing_id}/overrides", {"pms": pms}, None),
    ("GET", f"{base}/listing_data/overrides", {"listing_id": listing_id, "pms": pms}, None),
    ("GET", f"{base}/overrides", {"listing_id": listing_id, "pms": pms}, None),
    ("GET", f"{base}/listings/{listing_id}/overrides", {"pms": pms}, None),
    ("POST", f"{base}/overrides", None, {"listings": [{"id": listing_id, "pms": pms}]}),
    ("POST", f"{base}/listing_data/overrides", None, {"listings": [{"id": listing_id, "pms": pms}]}),
]

for method, url, params, json_body in candidates:
    try:
        resp = requests.request(method, url, headers=headers, params=params, json=json_body, timeout=15)
        print(f"{method} {url} params={params} json={json_body}")
        print(f"  -> HTTP {resp.status_code}")
        if resp.status_code != 404:
            print(f"  body (first 500 chars): {resp.text[:500]}")
        print()
    except requests.RequestException as exc:
        print(f"{method} {url} -> request failed: {exc}\n")
