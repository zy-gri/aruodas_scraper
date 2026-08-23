from __future__ import annotations

import argparse
import math
import re
from typing import Any


# ---------------------------------------------------------------------------
# Kaunas STR micro-location classifier
#
# These are intentionally NOT official district boundaries. They are a first
# version of our short-term-rental location model and should be tuned later
# against Airbnb revenue/occupancy data.
#
# The Aruodas map explicitly marks some pins as approximate, so the zones are
# deliberately broad enough to tolerate small coordinate offsets.
# ---------------------------------------------------------------------------

CLASSIFIER_VERSION = "kaunas-str-v1"


# Anchor points used by the first-pass rules.
# Coordinates are public landmark/address coordinates, not listing data.
ROTUSE = (54.89695, 23.88562)
PILIAMIESTIS = (54.90270, 23.87950)
ZALGIRIO_ARENA = (54.889974, 23.914408)
RESURRECTION_BASILICA = (54.90200, 23.91700)

# Approximate western/eastern ends of the Laisves/Naujamiestis STR corridor.
LAISVES_WEST = (54.89735, 23.89500)
LAISVES_EAST = (54.89680, 23.93150)


ARUODAS_VIEWPOINT_RE = re.compile(
    r"viewpoint=(-?\d{1,3}\.\d+),(-?\d{1,3}\.\d+)",
    flags=re.IGNORECASE,
)


def extract_aruodas_coordinates(html: str) -> tuple[float, float] | None:
    """Extract Aruodas' approximate map coordinate from detail-page HTML.

    Aruodas currently exposes the map point in the Google Street View link:

        ...&viewpoint=54.903446,23.878100&...

    Returns ``(latitude, longitude)`` or ``None`` when no coordinate exists.
    """

    match = ARUODAS_VIEWPOINT_RE.search(html)
    if not match:
        return None

    return float(match.group(1)), float(match.group(2))


def haversine_m(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """Great-circle distance in metres."""

    earth_radius_m = 6_371_000.0

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1)
        * math.cos(phi2)
        * math.sin(delta_lambda / 2.0) ** 2
    )

    return 2.0 * earth_radius_m * math.atan2(
        math.sqrt(a),
        math.sqrt(1.0 - a),
    )


def _local_xy_m(
    lat: float,
    lon: float,
    origin_lat: float,
    origin_lon: float,
) -> tuple[float, float]:
    """Convert nearby WGS84 coordinates to local metres.

    The equirectangular approximation is more than accurate enough for these
    sub-5-km Kaunas rules.
    """

    earth_radius_m = 6_371_000.0
    x = (
        math.radians(lon - origin_lon)
        * earth_radius_m
        * math.cos(math.radians(origin_lat))
    )
    y = math.radians(lat - origin_lat) * earth_radius_m
    return x, y


def distance_to_segment_m(
    lat: float,
    lon: float,
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    """Distance in metres from a point to a short geographic line segment."""

    origin_lat, origin_lon = start

    px, py = _local_xy_m(lat, lon, origin_lat, origin_lon)
    ax, ay = 0.0, 0.0
    bx, by = _local_xy_m(end[0], end[1], origin_lat, origin_lon)

    ab_x = bx - ax
    ab_y = by - ay
    ab_len_sq = ab_x * ab_x + ab_y * ab_y

    if ab_len_sq == 0:
        return math.hypot(px, py)

    t = ((px - ax) * ab_x + (py - ay) * ab_y) / ab_len_sq
    t = max(0.0, min(1.0, t))

    closest_x = ax + t * ab_x
    closest_y = ay + t * ab_y

    return math.hypot(px - closest_x, py - closest_y)


def _confidence(distance_m: float, limit_m: float) -> str:
    """Confidence based on how far a point is from a zone boundary."""

    ratio = distance_m / limit_m

    if ratio <= 0.70:
        return "high"
    if ratio <= 0.90:
        return "medium"
    return "low"


def _result(
    *,
    lat: float,
    lon: float,
    zone: str,
    label: str,
    grade: str,
    location_score: int,
    gate: str,
    confidence: str,
    distance_m: float | None,
    rationale: str,
) -> dict[str, Any]:
    return {
        "latitude": round(lat, 6),
        "longitude": round(lon, 6),
        "map_accuracy": "approximate",
        "location_zone": zone,
        "location_label": label,
        "location_grade": grade,
        "location_score": location_score,
        "location_gate": gate,
        "location_confidence": confidence,
        "zone_distance_m": round(distance_m, 1) if distance_m is not None else None,
        "location_rationale": rationale,
        "location_classifier_version": CLASSIFIER_VERSION,
    }


def classify_location(lat: float, lon: float) -> dict[str, Any]:
    """Classify a Kaunas coordinate into an STR-oriented micro-zone.

    Priority matters where zones overlap. The most valuable / most specific
    zones are checked first.
    """

    # 1. Old Town core around Rotuse / Vilniaus g. / main tourist core.
    old_town_limit_m = 750.0
    old_town_distance = haversine_m(lat, lon, *ROTUSE)

    if old_town_distance <= old_town_limit_m:
        return _result(
            lat=lat,
            lon=lon,
            zone="OLD_TOWN_CORE",
            label="Senamiestis core",
            grade="A+",
            location_score=100,
            gate="keep",
            confidence=_confidence(old_town_distance, old_town_limit_m),
            distance_m=old_town_distance,
            rationale="Inside the prime Old Town tourist/walkability zone.",
        )

    # 2. Laisves aleja / Naujamiestis core represented as a corridor rather
    # than a single circle because the attractive area is long and narrow.
    laisves_half_width_m = 450.0
    laisves_distance = distance_to_segment_m(
        lat,
        lon,
        LAISVES_WEST,
        LAISVES_EAST,
    )

    if laisves_distance <= laisves_half_width_m:
        return _result(
            lat=lat,
            lon=lon,
            zone="LAISVES_CORE",
            label="Laisves / Naujamiestis core",
            grade="A+",
            location_score=97,
            gate="keep",
            confidence=_confidence(laisves_distance, laisves_half_width_m),
            distance_m=laisves_distance,
            rationale="Inside the prime Laisves aleja / central Naujamiestis corridor.",
        )

    # 3. Piliamiestis must be separated from generic Vilijampole.
    piliamiestis_limit_m = 650.0
    piliamiestis_distance = haversine_m(lat, lon, *PILIAMIESTIS)

    if piliamiestis_distance <= piliamiestis_limit_m:
        return _result(
            lat=lat,
            lon=lon,
            zone="PILIAMIESTIS",
            label="Piliamiestis / Brastos riverside",
            grade="A",
            location_score=92,
            gate="keep",
            confidence=_confidence(piliamiestis_distance, piliamiestis_limit_m),
            distance_m=piliamiestis_distance,
            rationale="Inside the Piliamiestis / Brastos riverside development zone.",
        )

    # 4. Arena / Akropolis / Nemunas island edge.
    arena_limit_m = 950.0
    arena_distance = haversine_m(lat, lon, *ZALGIRIO_ARENA)

    if arena_distance <= arena_limit_m:
        return _result(
            lat=lat,
            lon=lon,
            zone="ARENA_AKROPOLIS",
            label="Arena / Akropolis / Nemunas island edge",
            grade="A",
            location_score=88,
            gate="keep",
            confidence=_confidence(arena_distance, arena_limit_m),
            distance_m=arena_distance,
            rationale="Strong event, shopping and central-walkability location near the arena.",
        )

    # 5. Central Zaliakalnis. Checked after Laisves so the lower slope nearest
    # the city centre remains classified as central Naujamiestis when suitable.
    zaliakalnis_limit_m = 850.0
    zaliakalnis_distance = haversine_m(lat, lon, *RESURRECTION_BASILICA)

    if lat >= 54.8990 and zaliakalnis_distance <= zaliakalnis_limit_m:
        return _result(
            lat=lat,
            lon=lon,
            zone="CENTRAL_ZALIAKALNIS",
            label="Central Zaliakalnis",
            grade="B+",
            location_score=76,
            gate="conditional",
            confidence=_confidence(zaliakalnis_distance, zaliakalnis_limit_m),
            distance_m=zaliakalnis_distance,
            rationale="Close to central Kaunas, but hill/walkability is weaker than prime centre zones.",
        )

    # Everything else is intentionally not treated as an automatic reject.
    # It simply needs exceptional economics before we spend effort enriching
    # descriptions/photos. This avoids hiding unusual bargains too early.
    nearest_anchor_distance = min(
        old_town_distance,
        laisves_distance,
        piliamiestis_distance,
        arena_distance,
        zaliakalnis_distance,
    )

    return _result(
        lat=lat,
        lon=lon,
        zone="OTHER_KAUNAS",
        label="Other / weak STR micro-location",
        grade="C",
        location_score=35,
        gate="exceptional_economics_only",
        confidence="high",
        distance_m=nearest_anchor_distance,
        rationale="Outside the first-pass STR priority zones; only continue for unusually strong economics.",
    )


def classify_listing_location(listing: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of a listing with location-classification fields added.

    Accepts either ``latitude``/``longitude`` or ``lat``/``lng`` keys. If no
    coordinate is present, the listing is returned with an explicit unknown
    location state instead of guessing from the Aruodas district name.
    """

    enriched = dict(listing)

    lat = enriched.get("latitude", enriched.get("lat"))
    lon = enriched.get("longitude", enriched.get("lng"))

    if lat is None or lon is None:
        enriched.update(
            {
                "location_zone": "UNKNOWN",
                "location_label": "Coordinate unavailable",
                "location_grade": None,
                "location_score": None,
                "location_gate": "needs_coordinates",
                "location_confidence": "unknown",
                "zone_distance_m": None,
                "location_rationale": "Do not infer the STR micro-zone from the broad Aruodas district alone.",
                "location_classifier_version": CLASSIFIER_VERSION,
            }
        )
        return enriched

    enriched.update(classify_location(float(lat), float(lon)))
    return enriched


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Classify a Kaunas coordinate into an STR micro-location zone.",
    )
    parser.add_argument("latitude", type=float)
    parser.add_argument("longitude", type=float)
    args = parser.parse_args()

    result = classify_location(args.latitude, args.longitude)

    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
