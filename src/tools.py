import json
import math
import os
from datetime import datetime, timedelta
from typing import Dict, Any, List

CONTRACT_PATH = "contracts/biovanguard_quality_agreement.md"
FACILITIES_PATH = "data/facilities.json"

def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in miles between two coordinates."""
    R = 3958.8  # Earth radius in miles
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 1)

def get_contract_clauses(topic: str = "all") -> Dict[str, Any]:
    """
    Retrieves legal and operational clauses from the BioVanguard Quality Agreement SLA.
    Use this to look up critical temperature ceilings, allowable excursion times, and financial penalties.
    """
    if not os.path.exists(CONTRACT_PATH):
        return {"error": f"Contract file not found at {CONTRACT_PATH}"}
    
    with open(CONTRACT_PATH, "r") as f:
        contract_text = f.read()
    
    return {
        "status": "success",
        "document_ref": "QA-SLA-2026-BV-0489",
        "contract_summary": contract_text
    }

def find_nearby_cold_storage(current_lat: float, current_lng: float, max_radius_miles: float = 50.0) -> List[Dict[str, Any]]:
    """
    Queries certified cold-storage depots within a given radius from the carrier's current GPS location.
    Returns facility details including capabilities, GxP certification, and operational status.
    """
    if not os.path.exists(FACILITIES_PATH):
        return [{"error": "Facilities database missing"}]
    
    with open(FACILITIES_PATH, "r") as f:
        facilities = json.load(f)
    
    results = []
    for fac in facilities:
        dist = _haversine_distance(current_lat, current_lng, fac["lat"], fac["lng"])
        if dist <= max_radius_miles:
            fac_info = fac.copy()
            fac_info["distance_miles"] = dist
            results.append(fac_info)
            
    results.sort(key=lambda x: x["distance_miles"])
    return results

def reserve_dock_replenishment(facility_id: str, shipment_id: str, required_service: str = "Dry Ice Refill") -> Dict[str, Any]:
    """
    Reserves an emergency bay and service replenishment (dry ice refill / cross-dock) at an authorized depot.
    """
    return {
        "status": "CONFIRMED",
        "reservation_id": f"RES-{facility_id[-3:]}-9981",
        "facility_id": facility_id,
        "shipment_id": shipment_id,
        "service_confirmed": required_service,
        "bay_assigned": "Door #04 (Rapid Cryo Bay)",
        "est_service_duration_minutes": 20,
        "timestamp": datetime.now().isoformat()
    }

def recalculate_reroute_eta(current_eta_str: str, detour_minutes: int, service_duration_minutes: int) -> Dict[str, Any]:
    """
    Computes updated delivery ETA taking into account highway detour time and depot service time.
    """
    # Assuming baseline format ISO or HH:MM
    return {
        "original_eta": current_eta_str,
        "total_added_delay_minutes": detour_minutes + service_duration_minutes,
        "new_estimated_eta": "2026-10-04T05:54:00-05:00",
        "sla_deadline": "2026-10-04T06:00:00-05:00",
        "status": "ON_TRACK_BEFORE_SLA_DEADLINE",
        "margin_buffer_minutes": 6
    }

def notify_clinical_stakeholders(hospital_id: str, patient_id: str, status_update: str, updated_eta: str) -> Dict[str, Any]:
    """
    Dispatches priority clinical notification to the surgical desk and logistics coordinator.
    """
    return {
        "status": "DISPATCHED",
        "recipient": f"Logistics Coordinator ({hospital_id})",
        "patient_cohort": patient_id,
        "channel": "EMERGENCY_SMS_AND_HL7_EVENT",
        "message_body": f"ALERT: Proactive thermal mitigation initiated for CAR-T Lot. Preserving 2-8C band. New ETA: {updated_eta}. Surgical schedule remains uncompromised.",
        "dispatched_at": datetime.now().isoformat()
    }

def generate_gxp_deviation_report(incident_id: str, root_cause: str, corrective_actions: List[str], final_disposition: str) -> Dict[str, Any]:
    """
    Generates a formal 21 CFR Part 11 / GxP regulatory deviation and CAPA log entry.
    """
    return {
        "deviation_id": f"DEV-2026-{incident_id[-5:]}",
        "timestamp": datetime.now().isoformat(),
        "regulatory_standard": "FDA 21 CFR Part 211 / GxP Annex 15",
        "root_cause_summary": root_cause,
        "corrective_actions_executed": corrective_actions,
        "product_quality_impact": "ZERO_SPOILAGE - Cargo preserved within qualified 2-8C envelope.",
        "batch_disposition": final_disposition,
        "financial_loss_prevented_usd": 470000.00
    }
