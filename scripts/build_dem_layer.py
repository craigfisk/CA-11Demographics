#!/usr/bin/env python3
"""
Build public/ca11-voters.geojson — no external dependencies required.

Downloads CA incorporated place/CDP boundaries from Census TIGERweb, clips
to CA-11 via centroid-in-polygon test, joins voter registration data, and
writes the output GeoJSON.

Usage:
    python3 scripts/build_dem_layer.py

Updating voter registration data:
    1. Go to https://www.sos.ca.gov/elections/voter-registration/voter-registration-statistics/
    2. Download the most recent "Report of Registration — Historical Highlights" (Excel/CSV).
    3. Find per-city counts for Contra Costa County (and any other counties in CA-11).
    4. Update VOTER_REG below with (dem, npp, total) triples.
       NPP = No Party Preference (California's term for unaffiliated/independent).
    5. Re-run this script to regenerate public/ca11-voters.geojson.
"""

import json, sys, urllib.request, urllib.parse
from pathlib import Path

DISTRICT_PATH = Path("public/ca11.geojson")
OUTPUT_PATH   = Path("public/ca11-voters.geojson")

# Census TIGERweb – Incorporated Places (layer 4) and CDPs (layer 5)
PLACES_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
    "Places_CouSub_ConCity_SubMCD/MapServer/4/query"
)
CDP_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
    "Places_CouSub_ConCity_SubMCD/MapServer/5/query"
)

# ---------------------------------------------------------------------------
# Voter registration data  (update with CA SOS report values)
# Key:   place_name_upper  (as returned by TIGERweb NAME field, uppercased)
# Value: (dem_registered, npp_registered, dem_plus_npp_plus_rep_total)
#
# Source: CA Secretary of State Report of Registration
#   https://www.sos.ca.gov/elections/voter-registration/voter-registration-statistics/
#
# CA-11 (119th Congress) = city and county of San Francisco.
# TIGERweb represents it as a single consolidated city-county place.
#
# Note: total = D + NPP + R only (minor parties excluded) so that
#   pct_rep = (total - dem - npp) / total represents Republicans specifically.
#
# Run the script once with an empty dict to see what keys are printed for
# unmatched places, then fill them in here.
# ---------------------------------------------------------------------------
VOTER_REG: dict[str, tuple[int, int, int]] = {
    # Values: (dem_registered, npp_registered, dem_plus_npp_plus_rep_total)
    # Approximate 2024 general-election pre-registration figures for SF:
    #   Democratic ~272k, NPP ~131k, Republican ~43k
    "SAN FRANCISCO CITY": (272000, 131000, 446000),
}


# ---------------------------------------------------------------------------
# Pure-Python spatial helpers
# ---------------------------------------------------------------------------

def _ring_contains(ring: list, px: float, py: float) -> bool:
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


def geometry_contains(geom: dict, px: float, py: float) -> bool:
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


def ring_centroid(ring: list) -> tuple[float, float]:
    xs = [c[0] for c in ring]
    ys = [c[1] for c in ring]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def geometry_centroid(geom: dict) -> tuple[float, float] | None:
    t = geom["type"]
    if t == "Polygon":
        return ring_centroid(geom["coordinates"][0])
    if t == "MultiPolygon":
        largest = max(geom["coordinates"], key=lambda p: len(p[0]))
        return ring_centroid(largest[0])
    return None


# ---------------------------------------------------------------------------

def load_district(path: Path) -> list[dict]:
    raw = json.loads(path.read_text())
    if raw.get("type") == "FeatureCollection":
        return [f["geometry"] for f in raw["features"]]
    if raw.get("type") == "Feature":
        return [raw["geometry"]]
    return [raw]


def fetch_places(url: str, label: str) -> list[dict]:
    params = {
        "where": "STATE='06'",
        "outFields": "NAME,STATE",
        "returnGeometry": "true",
        "f": "geojson",
        "outSR": "4326",
        "resultRecordCount": 2000,
    }
    full_url = url + "?" + urllib.parse.urlencode(params)
    print(f"Downloading CA {label} from Census TIGERweb…")
    try:
        req = urllib.request.Request(full_url, headers={"User-Agent": "build_dem_layer/1.0"})
        with urllib.request.urlopen(req, timeout=120) as r:
            fc = json.loads(r.read())
    except Exception as e:
        print(f"  Warning: could not download {label}: {e}")
        return []
    features = fc.get("features", [])
    print(f"  Downloaded {len(features)} {label}.")
    return features


def main() -> None:
    if not DISTRICT_PATH.exists():
        sys.exit(f"District file not found: {DISTRICT_PATH}\nRun scripts/fetch_district.py first.")

    district_geoms = load_district(DISTRICT_PATH)

    def in_district(px: float, py: float) -> bool:
        return any(geometry_contains(g, px, py) for g in district_geoms)

    features = fetch_places(PLACES_URL, "incorporated places")
    features += fetch_places(CDP_URL, "CDPs")
    print(f"Total CA places + CDPs: {len(features)}")

    if not features:
        sys.exit("No features downloaded.")

    output_features = []
    unmatched: list[str] = []

    for feat in features:
        geom = feat.get("geometry")
        if geom is None:
            continue
        centroid = geometry_centroid(geom)
        if centroid is None:
            continue
        cx, cy = centroid
        if not in_district(cx, cy):
            continue

        props    = feat["properties"]
        raw_name = str(props.get("NAME", "")).strip().upper()

        pair = VOTER_REG.get(raw_name)
        if pair is None:
            unmatched.append(f'"{raw_name}"')
            pct_dem = pct_npp = pct_rep = None
        else:
            dem, npp, total = pair
            pct_dem = round(dem / total * 100, 1) if total > 0 else None
            pct_npp = round(npp / total * 100, 1) if total > 0 else None
            pct_rep = round((total - dem - npp) / total * 100, 1) if total > 0 else None

        output_features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": {
                "place":    props.get("NAME", ""),
                "pct_dem":  pct_dem,
                "pct_npp":  pct_npp,
                "pct_rep":  pct_rep,
            },
        })

    out_fc = {"type": "FeatureCollection", "features": output_features}
    OUTPUT_PATH.write_text(json.dumps(out_fc))

    matched = sum(1 for f in output_features if f["properties"]["pct_dem"] is not None)
    print(f"\nPlaces in CA-11: {len(output_features)}")
    print(f"Matched to VOTER_REG: {matched}/{len(output_features)}")

    if unmatched:
        print("\nUnmatched — add these keys to VOTER_REG (with actual dem/npp/total counts):")
        for key in sorted(set(unmatched)):
            print(f"  {key}: (dem_count, npp_count, total_count),")

    print(f"\nOutput written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
