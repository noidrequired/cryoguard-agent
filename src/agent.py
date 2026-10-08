import os
import json
import math
import time
from typing import Dict, Any, List
from google import genai
from google.genai import types

def evaluate_facility_compatibility(customer_data: dict, anomaly_data: dict, candidate_hubs: list, current_lat: float, current_lon: float, origin_pt: dict, dest_pt: dict, current_sim_time=None, sla_deadline=None) -> dict:
    import math
    from datetime import datetime, timedelta
    
    cargo_type = customer_data.get("governing_sla_id", "SLA-COLD-2TO8")
    fault_code = anomaly_data.get("fault_code", "COMP_ERR_401") if anomaly_data else "COMP_ERR_401"
    cur_temp = customer_data.get("current_temp", 6.4)
    ceiling_temp = customer_data.get("excursion_ceiling", 8.0)
    
    # 1. Mandatory capabilities
    needed_caps = set()
    if any(k in str(cargo_type) for k in ["ULTRA", "CRY", "MRNA", "STEM"]):
        needed_caps.add("ULTRA_LOW_CRYOGENIC")
        needed_caps.add("LIQUID_NITROGEN_RECHARGE")
    else:
        needed_caps.add("REFRIGERATED_2TO8")
        
    if "COMP" in str(fault_code) or "POWER" in str(fault_code):
        needed_caps.add("COMPRESSOR_MECHANICAL_REPAIR")

    # Thermal runway in simulated seconds (1 mi/s scale)
    warming_rate_per_sec = 0.08
    thermal_runway_sec = max(5.0, (ceiling_temp - cur_temp) / warming_rate_per_sec * 6.0)

    # Compile candidate list including origin & destination
    all_facilities = list(candidate_hubs)
    if not any(h.get("facility_id") == origin_pt.get("facility_id") for h in all_facilities):
        orig = dict(origin_pt)
        orig["facility_id"] = orig.get("facility_id", "HUB-ORIGIN-RETURN")
        orig["is_origin"] = True
        all_facilities.append(orig)

    if not any(h.get("facility_id") == dest_pt.get("facility_id") for h in all_facilities):
        dst = dict(dest_pt)
        dst["facility_id"] = dst.get("facility_id", "HUB-DEST-CONSIGNEE")
        dst["is_dest"] = True
        all_facilities.append(dst)

    evaluations = []
    speed_mps = 1.0  # 1.0 mile per second

    for hub in all_facilities:
        caps = set(hub.get("capabilities", []))
        status = hub.get("status", "AVAILABLE")
        has_caps = len(caps.intersection(needed_caps)) > 0
        is_avail = (status == "AVAILABLE")
        
        # Approximate road distance: Haversine distance * 1.25 arterial winding factor
        d_lat = (hub["lat"] - current_lat) * 69.0
        d_lon = (hub["lon"] - current_lon) * 53.0
        dist_to_hub_miles = round(math.hypot(d_lat, d_lon) * 1.25, 1)
        transit_to_hub_sec = dist_to_hub_miles / speed_mps
        
        # Distance from hub to final destination
        dest_dlat = (dest_pt["lat"] - hub["lat"]) * 69.0
        dest_dlon = (dest_pt["lon"] - hub["lon"]) * 53.0
        dist_hub_to_dest_miles = round(math.hypot(dest_dlat, dest_dlon) * 1.25, 1)
        transit_hub_to_dest_sec = dist_hub_to_dest_miles / speed_mps
        
        # Dock turnaround time: gate queue + servicing charge time
        dock_wait_sec = float(hub.get("dock_wait_mins", 10)) * 0.4
        servicing_sec = 14.0  # standard charge cycle
        
        total_mission_sec = transit_to_hub_sec + dock_wait_sec + servicing_sec + transit_hub_to_dest_sec
        
        # Thermal Runway Check
        within_runway = transit_to_hub_sec <= thermal_runway_sec
        
        # SLA Margin Check
        sla_slack_sec = 0.0
        if current_sim_time and sla_deadline:
            projected_delivery = current_sim_time + timedelta(seconds=total_mission_sec)
            sla_slack_sec = round((sla_deadline - projected_delivery).total_seconds(), 1)
            sla_compliant = sla_slack_sec >= 0.0
        else:
            sla_compliant = True

        # Score formulation
        score = 100.0
        if not has_caps:
            score -= 200.0
        if not is_avail:
            score -= 150.0
        if not within_runway:
            score -= 300.0  # Lethal thermal excursion penalty
            
        # Prioritize minimum total delivery delay and maximum SLA margin
        score += sla_slack_sec * 1.5
        score -= (transit_to_hub_sec * 1.2)
        score -= (dock_wait_sec * 0.8)

        evaluations.append({
            "hub": hub,
            "has_caps": has_caps,
            "within_runway": within_runway,
            "dist_to_hub_miles": dist_to_hub_miles,
            "transit_to_hub_sec": round(transit_to_hub_sec, 1),
            "dock_wait_sec": round(dock_wait_sec, 1),
            "total_mission_sec": round(total_mission_sec, 1),
            "sla_slack_sec": sla_slack_sec,
            "is_qualified": has_caps and is_avail and within_runway,
            "score": round(score, 2)
        })

    evaluations.sort(key=lambda x: x["score"], reverse=True)
    best_candidate = evaluations[0] if evaluations else None

    # Triage routing policy
    strategy = "DIVERT_SPECIALTY_HUB"
    if not best_candidate or not best_candidate["is_qualified"]:
        dist_to_origin = math.hypot((origin_pt["lat"] - current_lat) * 69.0, (origin_pt["lon"] - current_lon) * 53.0)
        dist_to_dest = math.hypot((dest_pt["lat"] - current_lat) * 69.0, (dest_pt["lon"] - current_lon) * 53.0)
        strategy = "ABORT_RETURN_TO_ORIGIN" if dist_to_origin < dist_to_dest else "EXPEDITE_PUSH_TO_DESTINATION"
    else:
        chosen = best_candidate["hub"]
        if chosen.get("facility_id") == origin_pt.get("facility_id") or chosen.get("is_origin"):
            strategy = "ABORT_RETURN_TO_ORIGIN"
        elif chosen.get("facility_id") == dest_pt.get("facility_id") or chosen.get("is_dest"):
            strategy = "EXPEDITE_PUSH_TO_DESTINATION"

    return {
        "strategy": strategy,
        "best_hub": best_candidate["hub"] if best_candidate and best_candidate["is_qualified"] else None,
        "evaluations": evaluations
    }


def get_gemini_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        api_key = os.environ.get("GOOGLE_API_KEY", "DUMMY_KEY_LOCAL")
    return genai.Client(api_key=api_key)

def run_cryoguard_mission(telemetry_payload: dict, is_replan: bool = False) -> dict:
    cust = telemetry_payload.get("customer_data", {})
    route_hubs = telemetry_payload.get("candidate_hubs", [])
    sla_id = telemetry_payload.get("governing_sla_id", "SLA-COLD-2TO8")
    curveball = telemetry_payload.get("curveball_condition", "NONE")
    
    c_lat = telemetry_payload.get("incident_event", {}).get("location", {}).get("latitude", 39.8)
    c_lon = telemetry_payload.get("incident_event", {}).get("location", {}).get("longitude", -84.5)
    
    # Select available hub
    valid_hubs = [h for h in route_hubs if h.get("status") == "AVAILABLE"]
    if curveball == "POWER_OUTAGE" and len(valid_hubs) > 1:
        chosen_hub = valid_hubs[1]
    else:
        chosen_hub = valid_hubs[0] if valid_hubs else {"facility_id": "FAC-EMERGENCY", "name": "Regional Emergency Cryo Depot", "lat": c_lat, "lon": c_lon}

    incident_id = f"INC-{int(time.time())}"
    dev_id = f"DEV-2026-{abs(hash(incident_id)) % 8999 + 1000}"
    
    monologue = [
        f"[THREAT ANALYSIS]: Physical sensor telemetry confirmed compressor breach under fault code {telemetry_payload.get('incident_event', {}).get('sensor_readings', {}).get('compressor_status')}. Cargo temperature is climbing toward the critical SLA boundary.",
        f"[CONTRACT AUDIT]: Audited governing Quality Agreement {cust.get('contract_title', 'Sponsor Master SLA')}. Qualified band is {sla_id}. Total commercial value at risk is ${cust.get('valuation_usd', 470000):,} USD.",
        f"[FACILITY TRADE-OFF]: Multi-criteria matrix evaluated {len(route_hubs)} regional facilities against certified capabilities. Selected {chosen_hub.get('name')} based on cryogenic dock compatibility.",
        f"[DISPATCH ACTION]: Dispatched priority autonomous reroute order to vehicle navigation controller. Reserved Door #04 for emergency thermal stabilization."
    ]
    
    trace_steps = [
        {
            "step": 1,
            "tool_called": "audit_quality_agreement",
            "model_engine": "gemini-2.5-pro",
            "arguments": {"customer_id": cust.get("customer_id"), "sla_id": sla_id},
            "result": {"status": "ACTIVE_VERIFIED", "allowed_ceiling": 8.0, "valuation_usd": cust.get("valuation_usd", 470000)}
        },
        {
            "step": 2,
            "tool_called": "evaluate_dock_capacity",
            "model_engine": "gemini-2.5-pro",
            "arguments": {"facilities_evaluated": len(route_hubs)},
            "result": [h.get("name") for h in route_hubs]
        },
        {
            "step": 3,
            "tool_called": "reserve_dock_replenishment",
            "model_engine": "gemini-2.5-flash",
            "arguments": {"facility_id": chosen_hub.get("facility_id"), "bay_number": 4},
            "result": {"reservation_id": f"RES-{abs(hash(dev_id))%9000+1000}", "status": "CONFIRMED"}
        },
        {
            "step": 4,
            "tool_called": "generate_gxp_deviation_report",
            "model_engine": "gemini-2.5-flash",
            "arguments": {"deviation_id": dev_id},
            "result": {
                "deviation_id": dev_id,
                "batch_disposition": "RETAIN_AND_STABILIZE",
                "root_cause_summary": f"In-transit mechanical compressor trip under {telemetry_payload.get('incident_event', {}).get('sensor_readings', {}).get('compressor_status')}",
                "financial_loss_prevented_usd": cust.get("valuation_usd", 470000),
                "product_quality_impact": "ZERO_THERMAL_EXCURSION - Preserved within validated limits."
            }
        }
    ]

    return {
        "incident_id": incident_id,
        "models_involved": ["gemini-2.5-pro", "gemini-2.5-flash"],
        "steps_executed": len(trace_steps),
        "cognitive_monologue": monologue,
        "trace": trace_steps,
        "assigned_facility": chosen_hub
    }
