import json
import math
import os
from datetime import datetime
from typing import Dict, Any, List

SLA_DB_PATH = "data/sla_contracts.json"

def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 3958.8
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 1)

def get_contract_clauses(topic: str = "all", sla_id: str = "SLA-COLD-2TO8") -> Dict[str, Any]:
    """Retrieves legal and operational clauses from governing Quality Agreement SLA."""
    sla_data = {}
    if os.path.exists(SLA_DB_PATH):
        with open(SLA_DB_PATH, "r") as f:
            all_slas = json.load(f)
            sla_data = all_slas.get(sla_id, all_slas.get("SLA-COLD-2TO8", {}))
            
    return {
        "status": "success",
        "sla_id": sla_id,
        "governing_sla": sla_data,
        "contract_summary": f"Governing SLA: {sla_data.get('name')}. Band: {sla_data.get('thermal_band')}. Ceiling: {sla_data.get('excursion_ceiling')}C. Allowed Excursion: {sla_data.get('max_cumulative_excursion_mins')} mins. Liability: {sla_data.get('financial_liability')}."
    }

def find_nearby_cold_storage(
    current_lat: float, 
    current_lng: float, 
    candidate_hubs: List[Dict[str, Any]] = None,
    curveball_condition: str = None
) -> List[Dict[str, Any]]:
    """
    Evaluates candidate facilities along the active corridor.
    Simulates real-world dynamic operational availability and outages.
    """
    if not candidate_hubs:
        candidate_hubs = [
            {
                "facility_id": "DEPOT-CORRIDOR-PRIMARY",
                "name": "Regional GxP Thermal Hub",
                "lat": current_lat + 0.08,
                "lon": current_lng - 0.06,
                "capabilities": ["Dry Ice Refill", "Refrigerated Cross-Dock (2-8C)"],
                "gxp_certified": True,
                "status": "AVAILABLE"
            },
            {
                "facility_id": "DEPOT-CORRIDOR-BACKUP",
                "name": "Apex Secondary Thermal Storage",
                "lat": current_lat - 0.05,
                "lon": current_lng + 0.04,
                "capabilities": ["Refrigerated Cross-Dock (2-8C)", "Dry Ice Refill"],
                "gxp_certified": True,
                "status": "AVAILABLE"
            }
        ]
    
    results = []
    for idx, hub in enumerate(candidate_hubs):
        h_copy = hub.copy()
        h_copy["distance_miles"] = _haversine_distance(current_lat, current_lng, hub["lat"], hub["lon"])
        
        # Apply curveball outage if active
        if curveball_condition == "PRIMARY_FACILITY_OUTAGE" and idx == 0:
            h_copy["status"] = "UNAVAILABLE_EMERGENCY_POWER_OUTAGE"
            h_copy["service_warning"] = "Facility experiencing substation transformer fire; cannot accept cryo cargo."
        else:
            h_copy.setdefault("status", "AVAILABLE")
            
        results.append(h_copy)
        
    results.sort(key=lambda x: x["distance_miles"])
    return results

def reserve_dock_replenishment(facility_id: str, shipment_id: str, required_service: str = "Dry Ice Refill") -> Dict[str, Any]:
    """Reserves emergency bay and servicing at cold-dock."""
    return {
        "status": "CONFIRMED",
        "reservation_id": f"RES-{facility_id[-7:]}-9981",
        "facility_id": facility_id,
        "service_confirmed": required_service,
        "bay_assigned": "Door #04 (Rapid Cryo Bay)",
        "duration_minutes": 18,
        "dock_master_contact": "VHF Channel 14 / Tel: +1-800-CRYO-OPS"
    }

def dispatch_hotshot_courier_relay(carrier_id: str, rendezvous_lat: float, rendezvous_lon: float) -> Dict[str, Any]:
    """Dispatches priority medical courier to bypass traffic gridlock."""
    return {
        "status": "DISPATCHED",
        "dispatch_id": "HOTSHOT-RELAY-902",
        "carrier_unit": "Apex MedVan Rapid-01",
        "rendezvous_location": f"Rest Area Mile Marker ({rendezvous_lat:.4f}, {rendezvous_lon:.4f})",
        "eta_rendezvous_minutes": 12,
        "time_saved_minutes": 85,
        "cargo_transfer_protocol": "Validated 2-8C Port-to-Port Transfer Box"
    }

def deploy_mobile_tech_intercept(unit_id: str, fault_type: str, rendezvous_mile_marker: int = 142) -> Dict[str, Any]:
    """Dispatches roadside 24/7 mobile high-voltage reefer maintenance van."""
    return {
        "status": "EN_ROUTE",
        "service_van_id": "MOBI-TECH-VAN-08",
        "technician": "Certified ThermoKing Specialist",
        "rendezvous_point": "Highway Exit Park & Ride",
        "service_actions": ["Inverter Bypass", "Auxiliary 24V Battery Pack Swap", "Drive Belt Retensioning"],
        "est_repair_time_minutes": 22
    }

def execute_sterile_seal_inspection(incident_id: str, seal_integrity_status: str) -> Dict[str, Any]:
    """Executes electronic chain-of-custody tamper inspection."""
    return {
        "status": "COMPLETED_VERIFIED",
        "inspection_id": f"SEAL-INSP-{incident_id[-5:]}",
        "gxp_tamper_evident_seal": "RE-SEALED_BARCODE_SEC_88201",
        "vacuum_barrier": "INTACT",
        "sterility_assurance_level": "SAL_10_MINUS_6_CONFIRMED"
    }

def recharge_cryogenic_dewar(facility_id: str, target_vapor_pressure_psi: int = 22) -> Dict[str, Any]:
    """Restores ultra-low cryogenic envelope."""
    return {
        "status": "LN2_RECHARGED",
        "station_id": facility_id,
        "dewar_tank_level": "100% Liquid Nitrogen Vapor Phase",
        "operating_temperature_celsius": -185.0
    }

def recalculate_reroute_eta(current_eta_str: str, detour_minutes: int, service_duration_minutes: int) -> Dict[str, Any]:
    """Recalculates transit schedule against SLA deadline."""
    return {
        "original_eta": current_eta_str,
        "added_delay_minutes": detour_minutes + service_duration_minutes,
        "new_estimated_eta": "05:54 AM CT",
        "sla_deadline": "06:00 AM CT",
        "status": "ON_TRACK_BEFORE_SLA_DEADLINE",
        "margin_buffer_minutes": 6
    }

def notify_clinical_stakeholders(hospital_id: str, patient_id: str, status_update: str, updated_eta: str) -> Dict[str, Any]:
    """Dispatches HL7 emergency advisory to the hospital surgical coordinator."""
    return {
        "status": "DISPATCHED",
        "recipient": f"Logistics Coordinator ({hospital_id})",
        "patient_cohort": patient_id,
        "channel": "EMERGENCY_SMS_AND_HL7_EVENT",
        "message_body": f"ALERT: Mitigation executed. New ETA: {updated_eta}. Surgical window safe.",
        "dispatched_at": datetime.now().isoformat()
    }

def generate_gxp_deviation_report(incident_id: str, root_cause: str, corrective_actions: List[str], final_disposition: str) -> Dict[str, Any]:
    """Files formal FDA 21 CFR Part 11 / GxP CAPA regulatory log entry."""
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
