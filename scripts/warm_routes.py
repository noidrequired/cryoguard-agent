import json
import time
from src.routing import get_driving_route

def warm_all_routes():
    with open("data/routes.json", "r") as f:
        routes = json.load(f)

    print(f"🚀 Pre-warming OSRM cache for {len(routes)} US enterprise corridors...")
    total_cached = 0

    for idx, r in enumerate(routes):
        o = r["origin"]
        dest = r["destination"]
        
        print(f"\n[{idx+1}/{len(routes)}] Corridor: {r['corridor_name']}")
        
        # 1. Cache Main Route (Origin -> Final Consignee)
        main_res = get_driving_route(o["lat"], o["lon"], dest["lat"], dest["lon"])
        print(f"   ✓ Main Route: {main_res['distance_miles']} miles ({len(main_res['waypoints'])} points) [{main_res['source']}]")
        total_cached += 1
        time.sleep(0.4)

        # 2. Cache Detour Routes to each Candidate Hub
        for hub in r.get("candidate_hubs", []):
            detour_res = get_driving_route(o["lat"], o["lon"], hub["lat"], hub["lon"])
            print(f"   ✓ Hub Detour -> {hub['name']}: {detour_res['distance_miles']} miles [{detour_res['source']}]")
            total_cached += 1
            time.sleep(0.4)

    print(f"\n🎉 Successfully pre-warmed {total_cached} route segments into data/cache/routes_cache.json!")
    print("All future simulations will load real highway routes in 0ms.")

if __name__ == "__main__":
    warm_all_routes()
