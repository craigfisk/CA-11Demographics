#!/usr/bin/env python3
"""
Build public/ca11-demo.geojson — Census tract demographic data for CA-11.

Uses:
  - Census TIGERweb for tract geometries (no key required)
  - Census Reporter API for ACS 2023 5-year estimates (no key required)
    See: https://api.censusreporter.org

CA-11 (119th Congress) spans western Contra Costa, Marin, and potentially
parts of Alameda County. This script queries all four counties and filters
tracts by centroid-in-polygon against the district boundary.

Requires: public/ca11.geojson (run fetch_district.py first)

Usage:
    python3 scripts/build_demo_data.py
"""

import json, sys, urllib.request, urllib.parse, time
from pathlib import Path

DISTRICT_PATH = Path("public/ca11.geojson")
OUTPUT_PATH   = Path("public/ca11-demo.geojson")

# Counties to query (FIPS codes for counties intersecting CA-11 bbox)
# Contra Costa=06013, Marin=06041, Alameda=06001, San Francisco=06075
COUNTY_FIPS = ["06013", "06041", "06001", "06075"]

# Census TIGERweb – Census Tracts layer (layer 7) for California
TRACTS_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/"
    "TIGERweb/Tracts_Blocks/MapServer/7/query"
)

# Census Reporter API — returns ACS estimates without requiring a key
CENSUSREPORTER_URL = "https://api.censusreporter.org/1.0/data/show/latest"

# ACS tables needed:
#   B03003 — Hispanic or Latino Origin
#   B16004 — Age by Language Spoken at Home (for Spanish-speaking %)
#   B01001 — Sex by Age (for 18-34 population)
ACS_TABLES = "B03003,B16004,B01001"


# ---------------------------------------------------------------------------
# Pure-Python spatial helpers
# ---------------------------------------------------------------------------

def _ring_contains(ring, px, py):
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > py) != (yj > py):
            if px < (xj - xi) * (py - yi) / (yj - yi) + xi:
                inside = not inside
        j = i
    return inside


def geometry_contains(geom, px, py):
    t = geom["type"]
    if t == "Polygon":
        rings = geom["coordinates"]
        if not _ring_contains(rings[0], px, py):
            return False
        return not any(_ring_contains(h, px, py) for h in rings[1:])
    if t == "MultiPolygon":
        return any(
            geometry_contains({"type": "Polygon", "coordinates": poly}, px, py)
            for poly in geom["coordinates"]
        )
    return False


def ring_centroid(ring):
    xs = [c[0] for c in ring]
    ys = [c[1] for c in ring]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def geometry_centroid(geom):
    t = geom["type"]
    if t == "Polygon":
        return ring_centroid(geom["coordinates"][0])
    if t == "MultiPolygon":
        largest = max(geom["coordinates"], key=lambda p: len(p[0]))
        return ring_centroid(largest[0])
    return None


# ---------------------------------------------------------------------------

def load_district(path):
    raw = json.loads(path.read_text())
    if raw.get("type") == "FeatureCollection":
        return [f["geometry"] for f in raw["features"]]
    if raw.get("type") == "Feature":
        return [raw["geometry"]]
    return [raw]


def fetch_tract_geometries(county_fips):
    """Fetch tract geometries for a given county FIPS (e.g. '06013')."""
    state = county_fips[:2]
    county = county_fips[2:]
    params = {
        "where": f"STATE='{state}' AND COUNTY='{county}'",
        "outFields": "STATE,COUNTY,TRACT,GEOID",
        "returnGeometry": "true",
        "f": "geojson",
        "outSR": "4326",
        "resultRecordCount": 1000,
    }
    url = TRACTS_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "build_demo_data/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        fc = json.loads(r.read())
    return fc.get("features", [])


def fetch_acs_for_county(county_fips):
    """
    Fetch ACS demographics for all tracts in a county via Census Reporter API.
    Returns dict of {geoid: {B03003001: val, ...}} where geoid is '14000US06013XXXXXX'.
    """
    geo_ids = f"140|05000US{county_fips}"
    params = {
        "table_ids": ACS_TABLES,
        "geo_ids": geo_ids,
    }
    url = CENSUSREPORTER_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "build_demo_data/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.loads(r.read())

    result = {}
    for geoid, tables in d.get("data", {}).items():
        if not geoid.startswith("14000US"):
            continue
        estimates = {}
        for table_id, table_data in tables.items():
            for var, val in table_data.get("estimate", {}).items():
                estimates[var] = val
        result[geoid] = estimates
    return result


def safe_int(v):
    try:
        return max(0, int(v or 0))
    except (TypeError, ValueError):
        return 0


def main():
    if not DISTRICT_PATH.exists():
        sys.exit(f"District file not found: {DISTRICT_PATH}\nRun scripts/fetch_district.py first.")

    district_geoms = load_district(DISTRICT_PATH)

    def in_district(px, py):
        return any(geometry_contains(g, px, py) for g in district_geoms)

    all_tract_features = []
    all_acs = {}

    for fips in COUNTY_FIPS:
        county_name = {
            "06013": "Contra Costa",
            "06041": "Marin",
            "06001": "Alameda",
            "06075": "San Francisco",
        }.get(fips, fips)

        print(f"Fetching tracts for {county_name} County ({fips})…")
        try:
            feats = fetch_tract_geometries(fips)
            print(f"  {len(feats)} tracts")
            all_tract_features.extend(feats)
        except Exception as e:
            print(f"  Warning: geometry fetch failed: {e}")

        print(f"Fetching ACS data for {county_name} County via Census Reporter…")
        try:
            acs = fetch_acs_for_county(fips)
            print(f"  {len(acs)} tracts with ACS data")
            all_acs.update(acs)
        except Exception as e:
            print(f"  Warning: ACS fetch failed: {e}")
        time.sleep(0.5)  # be polite to Census Reporter

    print(f"\nTotal tracts fetched: {len(all_tract_features)}")
    print("Filtering by CA-11 boundary…")

    output_features = []
    for feat in all_tract_features:
        geom = feat.get("geometry")
        if geom is None:
            continue
        centroid = geometry_centroid(geom)
        if centroid is None:
            continue
        cx, cy = centroid
        if not in_district(cx, cy):
            continue

        props  = feat["properties"]
        state  = str(props.get("STATE", "")).zfill(2)
        county = str(props.get("COUNTY", "")).zfill(3)
        tract  = str(props.get("TRACT", "")).zfill(6)
        geoid  = f"14000US{state}{county}{tract}"

        acs = all_acs.get(geoid, {})

        total_pop     = safe_int(acs.get("B01001001"))
        hisp_universe = safe_int(acs.get("B03003001"))
        hisp_pop      = safe_int(acs.get("B03003003"))

        # Spanish speakers across age groups (B16004)
        spanish_pop = (safe_int(acs.get("B16004003")) +   # 5-17
                       safe_int(acs.get("B16004025")) +   # 18-64
                       safe_int(acs.get("B16004047")))    # 65+
        lang_universe = safe_int(acs.get("B16004001"))

        # Young voters (18-34): male B01001007-B01001012, female B01001031-B01001036
        young_male   = sum(safe_int(acs.get(f"B01001{str(i).zfill(3)}")) for i in range(7, 13))
        young_female = sum(safe_int(acs.get(f"B01001{str(i).zfill(3)}")) for i in range(31, 37))
        young_pop    = young_male + young_female

        pct_hispanic = round(hisp_pop / hisp_universe * 100, 1) if hisp_universe > 0 else 0
        pct_spanish  = round(spanish_pop / lang_universe * 100, 1) if lang_universe > 0 else 0
        pct_young    = round(young_pop / total_pop * 100, 1) if total_pop > 0 else 0

        output_features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": {
                "TRACT":        tract,
                "GEOID":        geoid,
                "total_pop":    total_pop,
                "pct_hispanic": pct_hispanic,
                "pct_spanish":  pct_spanish,
                "pct_young":    pct_young,
            },
        })

    out_fc = {"type": "FeatureCollection", "features": output_features}
    OUTPUT_PATH.write_text(json.dumps(out_fc))
    print(f"\nTracts in CA-11: {len(output_features)}")
    print(f"Output written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
