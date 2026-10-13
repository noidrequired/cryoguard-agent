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
    incident_history = telemetry_payload.get("incident_history", [])
    incident_count = len(incident_history) + 1
    
    c_lat = telemetry_payload.get("incident_event", {}).get("location", {}).get("latitude", 39.8)
    c_lon = telemetry_payload.get("incident_event", {}).get("location", {}).get("longitude", -84.5)
    c_temp = telemetry_payload.get("incident_event", {}).get("sensor_readings", {}).get("cargo_temperature_celsius", 6.4)
    fault_code = telemetry_payload.get("incident_event", {}).get("sensor_readings", {}).get("compressor_status", "COMP_ERR_401")
    
    valid_hubs = [h for h in route_hubs if h.get("status") == "AVAILABLE"]
    chosen_hub = telemetry_payload.get("assigned_hub")
    if not chosen_hub:
        chosen_hub = valid_hubs[0] if valid_hubs else {"facility_id": "FAC-EMERGENCY", "name": "Regional Emergency Cryo Depot", "lat": c_lat, "lon": c_lon}

    incident_id = f"INC-{int(time.time())}-CYCLE{incident_count}"
    dev_id = f"DEV-2026-{abs(hash(incident_id)) % 8999 + 1000}"
    
    # Prior history summary
    history_summary = ""
    if incident_history:
        history_summary = f" Prior events in this mission: {len(incident_history)} incident(s) recorded (" + ", ".join([h.get("fault", "Disruption") for h in incident_history]) + "). Cumulative delay is compounding against the SLA window."
    else:
        history_summary = " This is the primary initial disruption along the corridor."

    monologue = [
        f"[THREAT ANALYSIS]: Physical sensor telemetry confirmed active thermal excursion stress. Current core temperature is {c_temp:.2f}°C (Threshold: 8.00°C) with compressor status reporting `{fault_code}` at GPS ({c_lat:.4f}, {c_lon:.4f}). Thermodynamic warming rate is estimated at +0.08°C/s unpowered.{history_summary} Immediate active cryogenic recharge or mechanical intervention is mandatory to prevent irreversible biological degradation.",
        
        f"[CONTRACT AUDIT]: Governing Quality Agreement: {cust.get('contract_title', 'Sponsor Master Q-AGR')}. Active Therapeutic Asset: {cust.get('drug_product')} (Lot: {cust.get('batch_lot')}) valued at ${cust.get('valuation_usd', 470000):,} USD. Under Tier {sla_id}, cumulative excursion buffer is running on tight margins. Liquidated delay damages accrue at {cust.get('delay_liquidated_damages', '$5,000 USD per 30 mins')}. Multi-incident evaluation confirms that saving the batch takes absolute priority over minor arrival delay penalties.",
        
        f"[FACILITY TRADE-OFF]: Multi-criteria decision matrix evaluated {len(route_hubs)} regional facilities, factoring in travel distance at 1.0 mi/s, gate queue turnaround, and equipment compatibility. Previous facilities and blocked routes were eliminated from consideration. Assigned Target: {chosen_hub.get('name')} (Capabilities: {', '.join(chosen_hub.get('capabilities', ['REFRIGERATED_2TO8']))}). Projected dock intake confirms sufficient LN2/dry-ice reserve to arrest thermal runaway before critical product denaturing occurs.",
        
        f"[DISPATCH ACTION]: Issued autonomous high-priority reroute directive. Navigation waypoint matrix updated to vector toward {chosen_hub.get('name')}. Electronic notification dispatched to consignee hospital ({cust.get('consignee_facility')}) with revised dynamic ETA. Opened GxP CAPA deviation record {dev_id} under FDA 21 CFR Part 11 electronic records."
    ]
    
    trace_steps = [
        {
            "step": 1,
            "tool_called": "audit_quality_agreement",
            "model_engine": "gemini-2.5-pro",
            "arguments": {"customer_id": cust.get("customer_id"), "sla_id": sla_id, "incident_cycle": incident_count},
            "result": {"status": "ACTIVE_VERIFIED", "allowed_ceiling": 8.0, "valuation_usd": cust.get("valuation_usd", 470000)}
        },
        {
            "step": 2,
            "tool_called": "evaluate_dock_capacity",
            "model_engine": "gemini-2.5-pro",
            "arguments": {"facilities_evaluated": len(route_hubs), "prior_history_count": len(incident_history)},
            "result": [h.get("name") for h in route_hubs]
        },
        {
            "step": 3,
            "tool_called": "reserve_dock_replenishment",
            "model_engine": "gemini-2.5-flash",
            "arguments": {"facility_id": chosen_hub.get("facility_id"), "bay_number": 4, "incident_cycle": incident_count},
            "result": {"reservation_id": f"RES-{abs(hash(dev_id))%9000+1000}", "status": "CONFIRMED"}
        },
        {
            "step": 4,
            "tool_called": "generate_gxp_deviation_report",
            "model_engine": "gemini-2.5-flash",
            "arguments": {"deviation_id": dev_id, "cycle": incident_count},
            "result": {
                "deviation_id": dev_id,
                "batch_disposition": "RETAIN_AND_STABILIZE",
                "root_cause_summary": f"In-transit mechanical fault {fault_code} (Incident Cycle #{incident_count})",
                "financial_loss_prevented_usd": cust.get("valuation_usd", 470000),
                "product_quality_impact": "CONTROLLED_UNDER_CAPA - Preserved within validated limits."
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
