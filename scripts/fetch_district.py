#!/usr/bin/env python3
"""
Fetch the CA-11 congressional district boundary and save as public/ca11.geojson.

Uses the Census TIGERweb REST API (118th Congress boundaries).

Usage:
    python3 scripts/fetch_district.py
"""

import json, sys, urllib.request, urllib.parse
from pathlib import Path

OUTPUT_PATH = Path("public/ca11.geojson")

# Census TIGERweb – 119th Congressional Districts (layer 0)
# STATE='06' (California), CD119='11' (District 11)
TIGER_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Legislative/MapServer/0/query"
)

PARAMS = {
    "where": "STATE='06' AND CD119='11'",
    "outFields": "GEOID,NAME,STATE,CD119",
    "returnGeometry": "true",
    "f": "geojson",
    "outSR": "4326",
}


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    url = TIGER_URL + "?" + urllib.parse.urlencode(PARAMS)
    print(f"Fetching CA-11 boundary from Census TIGERweb…")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "fetch_district/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            fc = json.loads(r.read())
    except Exception as e:
        sys.exit(
            f"Download failed: {e}\n\n"
            "Fallback: download manually from\n"
            "  https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Legislative/MapServer/0/query\n"
            "with where=STATE='06' AND CD119='11' and save as public/ca11.geojson"
        )

    features = fc.get("features", [])
    if not features:
        sys.exit("No features returned — check the query parameters.")

    print(f"Got {len(features)} feature(s). Writing {OUTPUT_PATH}…")
    OUTPUT_PATH.write_text(json.dumps(fc))
    print("Done.")


if __name__ == "__main__":
    main()
