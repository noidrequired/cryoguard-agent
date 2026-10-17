import os
import json
import asyncio
import random
from datetime import datetime, timedelta
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from src.agent import run_cryoguard_mission, evaluate_facility_compatibility
from src.routing import get_driving_route, resample_waypoints
from src.yard_manager import generate_yard_manifest, build_stakeholder_alerts, update_yard_status, dispatch_live_webhook

load_dotenv()

app = FastAPI(title="CryoGuard AI Mission Operations Commander")

WEBHOOK_CONFIG_PATH = ".streamlit/webhook_config.json"

def get_persisted_webhooks():
    try:
        if os.path.exists(WEBHOOK_CONFIG_PATH):
            with open(WEBHOOK_CONFIG_PATH, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {
        "webhook_incab": "",
        "webhook_qa": "",
        "webhook_tms": "",
        "webhook_hosp": ""
    }

def save_persisted_webhooks(data: dict):
    try:
        os.makedirs(".streamlit", exist_ok=True)
        with open(WEBHOOK_CONFIG_PATH, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

def load_databases():
    with open("data/customers.json", "r") as f:
        customers = json.load(f)
    with open("data/anomalies.json", "r") as f:
        anomalies = json.load(f)
    with open("data/sla_contracts.json", "r") as f:
        slas = json.load(f)
    with open("data/routes.json", "r") as f:
        routes = json.load(f)
    with open("data/telemetry_stream.json", "r") as f:
        base_telemetry = json.load(f)
    return customers, anomalies, slas, routes, base_telemetry

customers_pool, anomalies_pool, slas_db, routes_pool, base_telemetry = load_databases()

class WebhookSettings(BaseModel):
    webhook_incab: str = ""
    webhook_qa: str = ""
    webhook_tms: str = ""
    webhook_hosp: str = ""

@app.get("/", response_class=HTMLResponse)
async def get_index():
    with open("templates/index.html", "r") as f:
        return f.read()

@app.get("/api/config_options")
async def get_config_options():
    return {
        "customers": customers_pool,
        "anomalies": anomalies_pool,
        "routes": routes_pool,
        "slas": slas_db,
        "webhooks": get_persisted_webhooks()
    }

@app.post("/api/save_webhooks")
async def save_webhooks(settings: WebhookSettings):
    save_persisted_webhooks(settings.model_dump())
    return {"status": "SUCCESS", "settings": settings.model_dump()}

@app.websocket("/ws/telemetry")
async def telemetry_stream(websocket: WebSocket):
    await websocket.accept()
    
    sim_task = None
    is_running = False
    
    state = {
        "sim_state": "STANDBY",
        "route": None,
        "customer": None,
        "active_anomaly": None,
        "chosen_hub": None,
        "disabled_hub_ids": set(),
        "cur_temp": 3.5,
        "miles_traversed": 0.0,
        "total_miles": 180.0,
        "active_leg_pts": [],
        "main_highway_pts": [],
        "detour_road_pts": [],
        "passed_points": [],
        "leg_idx": 0,
        "cur_lat": 0.0,
        "cur_lon": 0.0,
        "sim_speed": 1.0,
        "mission_clock": 0,
        "incident_history": [],
        "mission_start_time": None,
        "current_sim_time": None,
        "sla_deadline_time": None,
        "current_eta_time": None,
        "anomaly_trigger_mile": 50.0,
        "service_countdown": 14,
        "yard_manifest": None,
        "stakeholder_alerts": [],
        "gemini_result": None,
        "gxp_report": None
    }

    async def execute_anomaly_triage(disruption_code=None, custom_anomaly=None):
        nonlocal state
        if custom_anomaly:
            active_anom = custom_anomaly
        elif disruption_code:
            active_anom = next((a for a in anomalies_pool if a.get("fault_code") == disruption_code), anomalies_pool[0])
        else:
            active_anom = random.choice(anomalies_pool)

        fault_code = active_anom.get("fault_code", "COMP_ERR_401")
        state["active_anomaly"] = active_anom

        # Distinguish Facility Infrastructure Disruption vs Mechanical Reefer Breakdowns
        is_grid_outage = (fault_code == "GRID_OUTAGE_805")

        if is_grid_outage:
            # The carrier truck is intact; the target/nearby service station lost power
            compromised_hub = state["chosen_hub"] or (state["route"]["candidate_hubs"][0] if state["route"].get("candidate_hubs") else None)
            comp_name = compromised_hub["name"] if compromised_hub else "Regional Cryo Depot"
            if compromised_hub:
                state["disabled_hub_ids"].add(compromised_hub.get("facility_id"))
            
            # Cargo temp remains in spec or experiences slight idle drift, not immediate mechanical failure
            state["cur_temp"] = round(state["cur_temp"] + 0.15, 2)
            log_desc = f"Substation blackout knocked {comp_name} completely offline. Inbound intake closed."
        else:
            # Vehicle-side mechanical failure (compressor seize, APU trip, manifold rupture)
            state["cur_temp"] = round(max(state["cur_temp"] + 0.6, 6.4 + (len(state["incident_history"]) * 0.3)), 2)
            log_desc = f"{active_anom.get('name')} confirmed on Unit #409."

        state["sim_state"] = "FAULT_DETECTED"
        cur_t = state["current_sim_time"].strftime("%H:%M:%S")

        state["incident_history"].append({
            "timestamp": cur_t,
            "fault": fault_code,
            "temp_at_event": state["cur_temp"],
            "state": state["sim_state"],
            "details": log_desc
        })

        cust = state["customer"]
        route_info = state["route"]
        cand_hubs = route_info.get("candidate_hubs", [])

        # Filter out power-compromised hubs and currently docked hubs
        usable_hubs = [
            h for h in cand_hubs 
            if h.get("facility_id") not in state["disabled_hub_ids"]
        ]
        if not usable_hubs:
            usable_hubs = cand_hubs

        cust["current_temp"] = state["cur_temp"]
        cust["excursion_ceiling"] = 8.0

        decision = evaluate_facility_compatibility(
            cust, active_anom, usable_hubs, state["cur_lat"], state["cur_lon"],
            route_info["origin"], route_info["destination"],
            current_sim_time=state["current_sim_time"],
            sla_deadline=state["sla_deadline_time"]
        )

        chosen_hub = decision["best_hub"] if decision["best_hub"] else usable_hubs[0]
        state["chosen_hub"] = chosen_hub

        active_payload = json.loads(json.dumps(base_telemetry))
        active_payload["customer_data"] = cust
        active_payload["governing_sla_id"] = active_anom.get("sla_governed", cust.get("governing_sla_id", "SLA-COLD-2TO8"))
        active_payload["candidate_hubs"] = usable_hubs
        active_payload["assigned_hub"] = chosen_hub
        active_payload["incident_history"] = state["incident_history"]
        active_payload["curveball_condition"] = fault_code
        active_payload["incident_event"]["location"]["latitude"] = state["cur_lat"]
        active_payload["incident_event"]["location"]["longitude"] = state["cur_lon"]
        active_payload["incident_event"]["sensor_readings"]["compressor_status"] = fault_code
        active_payload["incident_event"]["sensor_readings"]["cargo_temperature_celsius"] = state["cur_temp"]

        res = run_cryoguard_mission(active_payload, is_replan=(len(state["incident_history"]) > 1))
        state["gemini_result"] = res

        gxp = next((s["result"] for s in res["trace"] if s["tool_called"] == "generate_gxp_deviation_report"), None)
        state["gxp_report"] = gxp

        detour_meta = get_driving_route(state["cur_lat"], state["cur_lon"], chosen_hub["lat"], chosen_hub["lon"])
        detour_waypoints = detour_meta["waypoints"]
        detour_mi = max(12, int(detour_meta.get("distance_miles", 20)))

        ym = generate_yard_manifest(
            chosen_hub, cust, active_anom,
            current_sim_time=state["current_sim_time"],
            detour_miles=detour_meta.get("distance_miles", 20.0),
            service_duration_sec=14
        )
        alerts = build_stakeholder_alerts(cust, active_anom, chosen_hub, state["cur_temp"], ym["eta_target"])
        state["yard_manifest"] = ym
        state["stakeholder_alerts"] = alerts

        hooks = get_persisted_webhooks()
        hook_map = {
            "CAB": hooks.get("webhook_incab"),
            "QA": hooks.get("webhook_qa"),
            "TMS": hooks.get("webhook_tms"),
            "HOSP": hooks.get("webhook_hosp")
        }
        for al in alerts:
            al_id = al.get("id", "")
            for key, url in hook_map.items():
                if key in al_id and url:
                    dispatch_live_webhook(url, al)

        state["detour_road_pts"] = detour_waypoints
        state["active_leg_pts"] = resample_waypoints(detour_waypoints, target_count=detour_mi)
        state["leg_idx"] = 0
        state["service_countdown"] = 14
        state["sim_state"] = "EN_ROUTE_HUB"

        await websocket.send_text(json.dumps({
            "type": "ANOMALY_TRIGGERED",
            "anomaly": active_anom,
            "chosen_hub": chosen_hub,
            "detour_pts": detour_waypoints,
            "gemini_result": res,
            "yard_manifest": ym,
            "stakeholder_alerts": alerts,
            "gxp_report": gxp,
            "incident_count": len(state["incident_history"]),
            "is_facility_outage": is_grid_outage
        }))

    async def run_simulation_loop():
        nonlocal is_running
        try:
            while is_running:
                spd = max(1.0, float(state["sim_speed"]))
                await asyncio.sleep(max(0.08, 0.8 / spd))
                
                time_inc = int(spd)
                state["mission_clock"] += time_inc
                state["current_sim_time"] += timedelta(seconds=time_inc)
                cur_time_str = state["current_sim_time"].strftime("%H:%M:%S")
                
                s_state = state["sim_state"]
                leg_pts = state["active_leg_pts"]
                pt_idx = state["leg_idx"]

                if leg_pts and len(leg_pts) > 1:
                    ratio = min(1.0, pt_idx / (len(leg_pts) - 1))
                    if s_state == "NOMINAL":
                        state["miles_traversed"] = round(state["total_miles"] * (pt_idx / len(leg_pts)), 1)
                    elif s_state in ["EN_ROUTE_HUB", "SERVICING"]:
                        state["miles_traversed"] = min(state["total_miles"], round(state["miles_traversed"] + (0.4 * spd), 1))
                    elif s_state == "FINAL_LEG":
                        rem = state["total_miles"] - state["anomaly_trigger_mile"]
                        state["miles_traversed"] = min(state["total_miles"], round(state["anomaly_trigger_mile"] + (rem * ratio), 1))

                if pt_idx < len(leg_pts) - 1:
                    step_jump = max(1, int(spd))
                    state["leg_idx"] = min(len(leg_pts) - 1, pt_idx + step_jump)
                    next_pt = leg_pts[state["leg_idx"]]
                    state["cur_lat"] = next_pt["lat"]
                    state["cur_lon"] = next_pt["lon"]

                log_entry = None

                rem_mi = max(0.0, state["total_miles"] - state["miles_traversed"])
                hold = state["service_countdown"] if s_state in ["EN_ROUTE_HUB", "SERVICING"] else 0
                state["current_eta_time"] = state["current_sim_time"] + timedelta(seconds=int(rem_mi + hold))

                cur_t_val = state["cur_temp"]
                cur_mi_val = state["miles_traversed"]
                cur_lt = state["cur_lat"]
                cur_ln = state["cur_lon"]

                if s_state == "NOMINAL":
                    state["cur_temp"] = round(3.5 + random.uniform(-0.03, 0.03), 2)
                    cur_t_val = state["cur_temp"]
                    log_entry = f"[{cur_time_str}] 📍 GPS ({cur_lt:.4f}, {cur_ln:.4f}) | Temp: {cur_t_val}°C | {cur_mi_val:.1f} mi"

                    if len(state["incident_history"]) == 0 and state["miles_traversed"] >= state["anomaly_trigger_mile"]:
                        await execute_anomaly_triage()
                        continue

                elif s_state == "EN_ROUTE_HUB":
                    state["cur_temp"] = round(state["cur_temp"] + 0.08, 2)
                    cur_t_val = state["cur_temp"]
                    hub_name = state["chosen_hub"]["name"] if state["chosen_hub"] else "Hub"
                    log_entry = f"[{cur_time_str}] 🛣️ Detour Transit ➔ {hub_name}. Temp: {cur_t_val}°C"
                    
                    if state.get("yard_manifest"):
                        state["yard_manifest"] = update_yard_status(state["yard_manifest"], "EN_ROUTE_HUB", state["current_sim_time"])

                    if pt_idx >= len(leg_pts) - 1:
                        state["sim_state"] = "SERVICING"
                        state["service_countdown"] = 14
                        log_entry = f"[{cur_time_str}] 🏢 Docked at {hub_name} Door #04. Servicing cryo re-charge initiated."

                elif s_state == "SERVICING":
                    step_jump = max(1, int(spd))
                    state["service_countdown"] = max(0, state["service_countdown"] - step_jump)
                    state["cur_temp"] = round(max(3.5, state["cur_temp"] - 0.35), 2)
                    cur_t_val = state["cur_temp"]
                    hub_name = state["chosen_hub"]["name"] if state["chosen_hub"] else "Hub"
                    cnt = state["service_countdown"]
                    log_entry = f"[{cur_time_str}] ❄️ Cryo Charging Active @ {hub_name}: Temp {cur_t_val}°C (Hold: {cnt}s)"

                    if state.get("yard_manifest"):
                        state["yard_manifest"] = update_yard_status(state["yard_manifest"], "SERVICING", state["current_sim_time"], hold_sec=state["service_countdown"])

                    if state["service_countdown"] <= 0:
                        state["sim_state"] = "FINAL_LEG"
                        dest = state["route"]["destination"]
                        hub = state["chosen_hub"]
                        final_meta = get_driving_route(hub["lat"], hub["lon"], dest["lat"], dest["lon"], corridor_id=state["route"].get("route_id"))
                        state["main_highway_pts"] = final_meta["waypoints"]
                        rem_drive_miles = max(15, int(final_meta.get("distance_miles", 50)))
                        state["active_leg_pts"] = resample_waypoints(final_meta["waypoints"], target_count=rem_drive_miles)
                        state["leg_idx"] = 0
                        dest_name = dest["name"]
                        log_entry = f"[{cur_time_str}] ✅ Servicing Complete: Thermal envelope restored (3.5°C). Re-entering highway to {dest_name}."

                elif s_state == "FINAL_LEG":
                    state["cur_temp"] = round(3.5 + random.uniform(-0.02, 0.02), 2)
                    cur_t_val = state["cur_temp"]
                    dest_name = state["route"]["destination"]["name"]
                    log_entry = f"[{cur_time_str}] 📍 GPS ({cur_lt:.4f}, {cur_ln:.4f}) | Approach ➔ {dest_name[:24]}"
                    
                    if state.get("yard_manifest"):
                        state["yard_manifest"] = update_yard_status(state["yard_manifest"], "FINAL_LEG", state["current_sim_time"])

                    if pt_idx >= len(leg_pts) - 1:
                        state["sim_state"] = "DELIVERED"
                        state["miles_traversed"] = state["total_miles"]
                        is_running = False
                        saved_total = state["customer"].get("valuation_usd", 470000)
                        log_entry = f"[{cur_time_str}] 🏥 Delivery Complete! 0% Batch Spoilage. Preserved ${saved_total:,} USD."

                state["passed_points"].append({"lat": state["cur_lat"], "lon": state["cur_lon"], "temp": state["cur_temp"], "sec": state["mission_clock"]})

                eta_str = state["current_eta_time"].strftime("%H:%M:%S") if state.get("current_eta_time") else "--:--:--"
                sla_str = state["sla_deadline_time"].strftime("%H:%M:%S") if state.get("sla_deadline_time") else "--:--:--"
                dep_str = state["mission_start_time"].strftime("%H:%M:%S") if state.get("mission_start_time") else "--:--:--"
                diff_sec = (state["sla_deadline_time"] - state["current_eta_time"]).total_seconds() if state.get("sla_deadline_time") and state.get("current_eta_time") else 0
                is_breach = diff_sec < 0

                payload = {
                    "type": "TELEMETRY_TICK",
                    "sim_state": state["sim_state"],
                    "cur_lat": state["cur_lat"],
                    "cur_lon": state["cur_lon"],
                    "cur_temp": state["cur_temp"],
                    "miles_traversed": state["miles_traversed"],
                    "total_miles": state["total_miles"],
                    "log_entry": log_entry,
                    "clock": cur_time_str,
                    "departure_time": dep_str,
                    "eta_str": eta_str,
                    "sla_str": sla_str,
                    "sla_slack_sec": round(diff_sec, 0),
                    "is_breach": is_breach,
                    "yard_manifest": state.get("yard_manifest")
                }
                await websocket.send_text(json.dumps(payload))

        except asyncio.CancelledError:
            pass

    try:
        while True:
            raw = await websocket.receive_text()
            cmd = json.loads(raw)
            action = cmd.get("action")

            if action == "LAUNCH_MISSION":
                route_id = cmd.get("route_id")
                cust_id = cmd.get("customer_id")
                state["sim_speed"] = float(cmd.get("sim_speed", 1.0))

                if route_id and route_id != "AUTO":
                    state["route"] = next((r for r in routes_pool if r["route_id"] == route_id), routes_pool[0])
                else:
                    state["route"] = random.choice(routes_pool)

                if cust_id and cust_id != "AUTO":
                    state["customer"] = next((c for c in customers_pool if c["customer_id"] == cust_id), customers_pool[0])
                else:
                    state["customer"] = random.choice(customers_pool)

                o = state["route"]["origin"]
                d = state["route"]["destination"]
                road_route = get_driving_route(o["lat"], o["lon"], d["lat"], d["lon"], corridor_id=state["route"].get("route_id"))
                
                highway_waypoints = road_route["waypoints"]
                total_miles = float(road_route.get("distance_miles", 180.0))
                sampled_pts = resample_waypoints(highway_waypoints, target_count=max(60, int(total_miles)))

                now_dt = datetime.now()
                nom_transit_sec = total_miles / 1.0
                sla_deadline = now_dt + timedelta(seconds=nom_transit_sec + 55.0)

                state["sim_state"] = "NOMINAL"
                state["main_highway_pts"] = highway_waypoints
                state["detour_road_pts"] = []
                state["active_leg_pts"] = sampled_pts
                state["passed_points"] = []
                state["leg_idx"] = 0
                state["cur_lat"] = sampled_pts[0]["lat"]
                state["cur_lon"] = sampled_pts[0]["lon"]
                state["cur_temp"] = 3.5
                state["miles_traversed"] = 0.0
                state["total_miles"] = total_miles
                state["mission_clock"] = 0
                state["mission_start_time"] = now_dt
                state["current_sim_time"] = now_dt
                state["sla_deadline_time"] = sla_deadline
                state["current_eta_time"] = now_dt + timedelta(seconds=nom_transit_sec)
                state["anomaly_trigger_mile"] = round(total_miles * random.uniform(0.42, 0.58), 1)
                state["chosen_hub"] = None
                state["active_anomaly"] = None
                state["disabled_hub_ids"] = set()
                state["incident_history"] = []
                state["yard_manifest"] = None
                state["stakeholder_alerts"] = []
                state["gemini_result"] = None
                state["gxp_report"] = None

                await websocket.send_text(json.dumps({
                    "type": "MISSION_INITIALIZED",
                    "route": state["route"],
                    "customer": state["customer"],
                    "highway_pts": highway_waypoints,
                    "total_miles": total_miles,
                    "cur_lat": state["cur_lat"],
                    "cur_lon": state["cur_lon"],
                    "cur_temp": state["cur_temp"],
                    "departure_time": now_dt.strftime("%H:%M:%S"),
                    "sla_deadline": sla_deadline.strftime("%H:%M:%S")
                }))

                is_running = True
                if sim_task:
                    sim_task.cancel()
                sim_task = asyncio.create_task(run_simulation_loop())

            elif action == "UPDATE_SPEED":
                new_speed = float(cmd.get("sim_speed", 1.0))
                state["sim_speed"] = max(1.0, new_speed)

            elif action == "STOP_MISSION":
                is_running = False
                if sim_task:
                    sim_task.cancel()
                await websocket.send_text(json.dumps({"type": "MISSION_STOPPED"}))

            elif action == "RESET_MISSION":
                is_running = False
                if sim_task:
                    sim_task.cancel()
                state["sim_state"] = "STANDBY"
                state["miles_traversed"] = 0.0
                state["active_leg_pts"] = []
                state["passed_points"] = []
                state["detour_road_pts"] = []
                state["disabled_hub_ids"] = set()
                state["yard_manifest"] = None
                state["stakeholder_alerts"] = []
                state["gemini_result"] = None
                state["gxp_report"] = None
                state["incident_history"] = []
                await websocket.send_text(json.dumps({"type": "MISSION_RESET"}))

            elif action == "TRIGGER_ANOMALY":
                if is_running and state["sim_state"] != "STANDBY":
                    anom_id = cmd.get("anomaly_id", "AUTO")
                    selected_anom = None
                    if anom_id != "AUTO":
                        selected_anom = next((a for a in anomalies_pool if a["id"] == anom_id), None)
                    await execute_anomaly_triage(custom_anomaly=selected_anom)

            elif action == "TRIGGER_SURPRISE_OUTAGE":
                if is_running and state["sim_state"] != "STANDBY":
                    await execute_anomaly_triage(disruption_code="GRID_OUTAGE_805")

    except WebSocketDisconnect:
        is_running = False
        if sim_task:
            sim_task.cancel()
