import json
import math
import os
from datetime import datetime
from typing import Dict, Any, List

CONTRACT_PATH = "contracts/biovanguard_quality_agreement.md"
SLA_DB_PATH = "data/sla_contracts.json"
FACILITIES_PATH = "data/facilities.json"

def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 3958.8  # Earth radius in miles
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 1)

def get_contract_clauses(topic: str = "all", sla_id: str = "SLA-COLD-2TO8") -> Dict[str, Any]:
    """
    Retrieves legal and operational clauses from the governing Quality Agreement and SLA schedule.
    """
    sla_data = {}
    if os.path.exists(SLA_DB_PATH):
        with open(SLA_DB_PATH, "r") as f:
            all_slas = json.load(f)
            sla_data = all_slas.get(sla_id, all_slas.get("SLA-COLD-2TO8", {}))
            
    contract_summary = f"Governing SLA: {sla_data.get('name', 'Standard GxP SLA')}. " \
                       f"Thermal Band: {sla_data.get('thermal_band', '+2°C to +8°C')}. " \
                       f"Critical Excursion Ceiling: {sla_data.get('excursion_ceiling', 8.0)}°C. " \
                       f"Max Allowed Excursion Budget: {sla_data.get('max_cumulative_excursion_mins', 120)} mins. " \
                       f"Financial Liability: {sla_data.get('financial_liability', '$470,000 USD')}."

    return {
        "status": "success",
        "sla_id": sla_id,
        "governing_sla": sla_data,
        "contract_summary": contract_summary
    }

def find_nearby_cold_storage(current_lat: float, current_lng: float, max_radius_miles: float = 50.0) -> List[Dict[str, Any]]:
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
    return {
        "original_eta": current_eta_str,
        "total_added_delay_minutes": detour_minutes + service_duration_minutes,
        "new_estimated_eta": "2026-10-04T05:54:00-05:00",
        "sla_deadline": "2026-10-04T06:00:00-05:00",
        "status": "ON_TRACK_BEFORE_SLA_DEADLINE",
        "margin_buffer_minutes": 6
    }

def notify_clinical_stakeholders(hospital_id: str, patient_id: str, status_update: str, updated_eta: str) -> Dict[str, Any]:
    return {
        "status": "DISPATCHED",
        "recipient": f"Logistics Coordinator ({hospital_id})",
        "patient_cohort": patient_id,
        "channel": "EMERGENCY_SMS_AND_HL7_EVENT",
        "message_body": f"ALERT: Proactive thermal mitigation initiated. New ETA: {updated_eta}. Surgical window preserved.",
        "dispatched_at": datetime.now().isoformat()
    }

def generate_gxp_deviation_report(incident_id: str, root_cause: str, corrective_actions: List[str], final_disposition: str) -> Dict[str, Any]:
    return {
        "deviation_id": f"DEV-2026-{incident_id[-5:]}",
        "timestamp": datetime.now().isoformat(),
        "regulatory_standard": "FDA 21 CFR Part 11 / GxP Annex 15",
        "root_cause_summary": root_cause,
        "corrective_actions_executed": corrective_actions,
        "product_quality_impact": "ZERO_SPOILAGE - Cargo maintained in validated state.",
        "batch_disposition": final_disposition,
        "financial_loss_prevented_usd": 470000.00
    }
