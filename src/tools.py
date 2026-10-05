import json
import math
import os
from datetime import datetime
from typing import Dict, Any, List

SLA_DB_PATH = "data/sla_contracts.json"
CUSTOMERS_DB_PATH = "data/customers.json"

def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 3958.8  # Earth radius in miles
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 1)

def get_contract_clauses(customer_id: str = None, sla_id: str = "SLA-COLD-2TO8") -> Dict[str, Any]:
    """
    Dynamically retrieves governing Quality Agreement clauses and SLA penalties
    for the specific customer sponsor and therapy in transit.
    """
    sla_data = {}
    if os.path.exists(SLA_DB_PATH):
        with open(SLA_DB_PATH, "r") as f:
            all_slas = json.load(f)
            sla_data = all_slas.get(sla_id, all_slas.get("SLA-COLD-2TO8", {}))

    customer_info = {}
    if os.path.exists(CUSTOMERS_DB_PATH) and customer_id:
        with open(CUSTOMERS_DB_PATH, "r") as f:
            customers = json.load(f)
            customer_info = next((c for c in customers if c["customer_id"] == customer_id), {})

    cust_name = customer_info.get("customer_name", "Global Life Sciences Sponsor")
    contract_title = customer_info.get("contract_title", "Master Quality Agreement")
    batch_val = customer_info.get("valuation_usd", sla_data.get("liability_amount_usd", 470000))
    delay_damages = customer_info.get("delay_liquidated_damages", sla_data.get("financial_liability", "Liquidated damages applicable"))

    return {
        "status": "success",
        "customer_id": customer_id,
        "sponsor": cust_name,
        "governing_agreement": contract_title,
        "governing_sla_id": sla_id,
        "product_valuation_usd": batch_val,
        "delay_penalties": delay_damages,
        "thermal_band_spec": sla_data.get("thermal_band", "+2.0°C to +8.0°C"),
        "excursion_ceiling": sla_data.get("excursion_ceiling", 8.0),
        "allowed_excursion_mins": customer_info.get("allowed_excursion_mins", sla_data.get("max_cumulative_excursion_mins", 120)),
        "contract_summary": f"Active Agreement: {contract_title} for {cust_name}. Thermal spec: {sla_data.get('thermal_band')}. Ceiling: {sla_data.get('excursion_ceiling')}C. Batch Valuation: ${batch_val:,} USD. Delay Penalty: {delay_damages}."
    }

def find_nearby_cold_storage(
    current_lat: float, 
    current_lng: float, 
    candidate_hubs: List[Dict[str, Any]] = None,
    curveball_condition: str = "NONE"
) -> List[Dict[str, Any]]:
    """Evaluates candidate facilities with live operational availability and outage simulation."""
    if not candidate_hubs:
        candidate_hubs = [
            {
                "facility_id": "DEPOT-CORRIDOR-PRIMARY",
                "name": "Regional GxP Thermal Hub",
                "lat": current_lat + 0.08,
                "lon": current_lng - 0.06,
                "capabilities": ["Dry Ice Refill", "Refrigerated Cross-Dock (2-8C)"],
                "gxp_certified": True
            },
            {
                "facility_id": "DEPOT-CORRIDOR-BACKUP",
                "name": "Apex Secondary Storage Dock",
                "lat": current_lat - 0.05,
                "lon": current_lng + 0.04,
                "capabilities": ["Refrigerated Cross-Dock (2-8C)", "Dry Ice Refill"],
                "gxp_certified": True
            }
        ]
    
    results = []
    for idx, hub in enumerate(candidate_hubs):
        h_copy = hub.copy()
        h_copy["distance_miles"] = _haversine_distance(current_lat, current_lng, hub["lat"], hub["lon"])
        
        if "POWER_OUTAGE" in curveball_condition and idx == 0:
            h_copy["status"] = "UNAVAILABLE_SUBSTATION_FIRE"
            h_copy["service_alert"] = "CRITICAL: Electrical substation fire. Facility offline; intake doors closed."
        elif "DETOUR_BLOCKED" in curveball_condition and idx == 0:
            h_copy["status"] = "ACCESS_RAMP_CLOSED"
            h_copy["service_alert"] = "ROAD CLOSURE: Access ramp blocked by multi-vehicle tanker jackknife."
        else:
            h_copy["status"] = "AVAILABLE"
            
        results.append(h_copy)
        
    results.sort(key=lambda x: x["distance_miles"])
    return results

def reserve_dock_replenishment(facility_id: str, shipment_id: str, required_service: str = "Dry Ice Refill") -> Dict[str, Any]:
    return {
        "status": "CONFIRMED",
        "reservation_id": f"RES-{facility_id[-8:]}-9981",
        "facility_id": facility_id,
        "service_confirmed": required_service,
        "bay_assigned": "Door #04 (Rapid Cryo Bay)",
        "service_duration_sim_sec": 14,
        "dock_master_contact": "VHF Channel 14 / Priority Ops Cell"
    }

def dispatch_hotshot_courier_relay(carrier_id: str, rendezvous_lat: float, rendezvous_lon: float) -> Dict[str, Any]:
    return {
        "status": "DISPATCHED",
        "dispatch_id": "HOTSHOT-RELAY-902",
        "carrier_unit": "Apex MedVan Rapid-01",
        "rendezvous_location": f"Highway Rest Area Mile Marker ({rendezvous_lat:.4f}, {rendezvous_lon:.4f})",
        "service_duration_sim_sec": 10,
        "time_saved_minutes": 85,
        "cargo_transfer_protocol": "Validated 2-8C Port-to-Port Transfer Box"
    }

def deploy_mobile_tech_intercept(unit_id: str, fault_type: str, rendezvous_mile_marker: int = 142) -> Dict[str, Any]:
    return {
        "status": "EN_ROUTE",
        "service_van_id": "MOBI-TECH-VAN-08",
        "technician": "Certified ThermoKing Specialist",
        "rendezvous_point": "Highway Exit Park & Ride",
        "service_duration_sim_sec": 18,
        "service_actions": ["Inverter Bypass", "Auxiliary 24V Battery Pack Swap", "Drive Belt Retensioning"]
    }

def execute_sterile_seal_inspection(incident_id: str, seal_integrity_status: str) -> Dict[str, Any]:
    return {
        "status": "COMPLETED_VERIFIED",
        "inspection_id": f"SEAL-INSP-{incident_id[-5:]}",
        "service_duration_sim_sec": 8,
        "gxp_tamper_evident_seal": "RE-SEALED_BARCODE_SEC_88201",
        "vacuum_barrier": "INTACT",
        "sterility_assurance_level": "SAL_10_MINUS_6_CONFIRMED"
    }

def recharge_cryogenic_dewar(facility_id: str, target_vapor_pressure_psi: int = 22) -> Dict[str, Any]:
    return {
        "status": "LN2_RECHARGED",
        "station_id": facility_id,
        "service_duration_sim_sec": 16,
        "dewar_tank_level": "100% Liquid Nitrogen Vapor Phase",
        "operating_temperature_celsius": -185.0
    }

def recalculate_reroute_eta(
    current_eta_str: str, 
    detour_minutes: int, 
    service_duration_minutes: int,
    curveball_condition: str = "NONE"
) -> Dict[str, Any]:
    sla_time = "05:15 AM CT" if "SURGERY_MOVED_UP" in curveball_condition else "06:00 AM CT"
    
    return {
        "original_eta": current_eta_str,
        "added_delay_minutes": detour_minutes + service_duration_minutes,
        "new_estimated_eta": "05:54 AM CT",
        "sla_deadline": sla_time,
        "status": "ON_TRACK" if "SURGERY_MOVED_UP" not in curveball_condition else "CRITICAL_TIGHT_MARGIN",
        "margin_buffer_minutes": 6 if "SURGERY_MOVED_UP" not in curveball_condition else -39
    }

def notify_clinical_stakeholders(hospital_id: str, patient_id: str, status_update: str, updated_eta: str) -> Dict[str, Any]:
    return {
        "status": "DISPATCHED",
        "recipient": f"Logistics Coordinator ({hospital_id})",
        "patient_cohort": patient_id,
        "channel": "EMERGENCY_SMS_AND_HL7_EVENT",
        "message_body": f"ALERT: Proactive thermal mitigation active. Updated ETA: {updated_eta}. Surgical window safe.",
        "dispatched_at": datetime.now().isoformat()
    }

def generate_gxp_deviation_report(
    incident_id: str, 
    root_cause: str, 
    corrective_actions: List[str], 
    final_disposition: str,
    customer_id: str = None,
    sla_id: str = "SLA-COLD-2TO8"
) -> Dict[str, Any]:
    liability_saved = 470000.00
    if os.path.exists(CUSTOMERS_DB_PATH) and customer_id:
        try:
            with open(CUSTOMERS_DB_PATH, "r") as f:
                custs = json.load(f)
                c_match = next((c for c in custs if c["customer_id"] == customer_id), None)
                if c_match:
                    liability_saved = float(c_match.get("valuation_usd", 470000))
        except Exception:
            pass

    return {
        "deviation_id": f"DEV-2026-{incident_id[-5:]}",
        "timestamp": datetime.now().isoformat(),
        "regulatory_standard": "FDA 21 CFR Part 11 / GxP Annex 15",
        "customer_id": customer_id,
        "governing_sla_schedule": sla_id,
        "root_cause_summary": root_cause,
        "corrective_actions_executed": corrective_actions,
        "product_quality_impact": "ZERO_SPOILAGE - Cargo maintained in validated state.",
        "batch_disposition": final_disposition,
        "financial_loss_prevented_usd": liability_saved
    }
