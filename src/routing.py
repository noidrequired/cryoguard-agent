import json
import math
import os
import requests
from typing import Dict, Any, List, Tuple

CACHE_FILE = "data/cache/routes_cache.json"

def _ensure_cache_file():
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    if not os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "w") as f:
            json.dump({}, f)

def _get_cache_key(origin: Tuple[float, float], dest: Tuple[float, float]) -> str:
    return f"{origin[0]:.4f},{origin[1]:.4f}->{dest[0]:.4f},{dest[1]:.4f}"

def _load_from_cache(cache_key: str) -> Dict[str, Any]:
    _ensure_cache_file()
    try:
        with open(CACHE_FILE, "r") as f:
            data = json.load(f)
            return data.get(cache_key)
    except Exception:
        return None

def _save_to_cache(cache_key: str, route_data: Dict[str, Any]):
    _ensure_cache_file()
    try:
        with open(CACHE_FILE, "r") as f:
            data = json.load(f)
        data[cache_key] = route_data
        with open(CACHE_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Warning: Failed to save route to cache: {e}")

def get_driving_route(
    origin_lat: float, 
    origin_lon: float, 
    dest_lat: float, 
    dest_lon: float
) -> Dict[str, Any]:
    """
    Fetches real highway driving distance, duration, and road geometry.
    Checks local disk cache first (0ms). Falls back to OSRM API, then to geodesic calculation.
    """
    cache_key = _get_cache_key((origin_lat, origin_lon), (dest_lat, dest_lon))
    
    # 1. Check Local Disk Cache
    cached_result = _load_from_cache(cache_key)
    if cached_result:
        cached_result["source"] = "LOCAL_DISK_CACHE"
        return cached_result

    # 2. Query OSRM OpenStreetMap Routing API
    try:
        # OSRM expects format: {lon},{lat};{lon},{lat}
        url = f"https://router.project-osrm.org/route/v1/driving/{origin_lon},{origin_lat};{dest_lon},{dest_lat}?overview=full&geometries=geojson"
        resp = requests.get(url, timeout=3.0)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == "Ok" and len(data.get("routes", [])) > 0:
                route = data["routes"][0]
                distance_miles = round(route["distance"] * 0.000621371, 1)
                duration_minutes = round(route["duration"] / 60.0, 1)
                
                # OSRM returns coordinates as [lon, lat]
                raw_coords = route["geometry"]["coordinates"]
                waypoints = [{"lat": round(pt[1], 5), "lon": round(pt[0], 5)} for pt in raw_coords]
                
                result = {
                    "source": "OSRM_OPENSTREETMAP",
                    "distance_miles": distance_miles,
                    "duration_minutes": duration_minutes,
                    "waypoints": waypoints
                }
                _save_to_cache(cache_key, result)
                return result
    except Exception as e:
        print(f"OSRM request failed, using fallback: {e}")

    # 3. Graceful Geodesic Fallback (if offline)
    R = 3958.8
    dlat = math.radians(dest_lat - origin_lat)
    dlon = math.radians(dest_lon - origin_lon)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(origin_lat)) * math.cos(math.radians(dest_lat)) *
         math.sin(dlon / 2) ** 2)
    dist = round(R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)), 1)
    
    fallback_pts = []
    for step in range(30):
        ratio = step / 29.0
        fallback_pts.append({
            "lat": round(origin_lat + (dest_lat - origin_lat) * ratio, 5),
            "lon": round(origin_lon + (dest_lon - origin_lon) * ratio, 5)
        })

    return {
        "source": "GEODESIC_OFFLINE_FALLBACK",
        "distance_miles": dist,
        "duration_minutes": round(dist / 55.0 * 60, 1),
        "waypoints": fallback_pts
    }

def resample_waypoints(waypoints: List[Dict[str, float]], target_count: int = 60) -> List[Dict[str, float]]:
    """Resamples a high-density OSRM polyline into an evenly spaced list for smooth animation."""
    if not waypoints:
        return []
    if len(waypoints) <= target_count:
        return waypoints
    
    step = (len(waypoints) - 1) / float(target_count - 1)
    resampled = []
    for i in range(target_count):
        idx = int(round(i * step))
        idx = min(idx, len(waypoints) - 1)
        resampled.append(waypoints[idx])
    return resampled
