import hashlib
import json
import random
import time
from datetime import datetime, timedelta
import urllib.request
import urllib.error

def generate_yard_manifest(
    facility: dict, 
    customer: dict, 
    anomaly: dict, 
    current_sim_time: datetime, 
    detour_miles: float, 
    service_duration_sec: int = 14
) -> dict:
    """
    Calculates exact dynamic YMS reservations synchronized to kinematic transit models.
    """
    fac_id = facility.get("facility_id", "FAC-DEFAULT")
    fac_name = facility.get("name", "Regional Biologics Depot")
    lot_id = customer.get("batch_lot", "LOT-99201")
    
    # 1.0 mi/s constant kinematic speed
    transit_seconds = max(5, int(detour_miles / 1.0))
    eta_arrival = current_sim_time + timedelta(seconds=transit_seconds)
    
    # Window start is arrival with tight pre-dock margin (-2s), end covers servicing + bay departure clearance (+10s)
    window_start = (eta_arrival - timedelta(seconds=2)).strftime("%H:%M:%S")
    window_end = (eta_arrival + timedelta(seconds=service_duration_sec + 10)).strftime("%H:%M:%S")
    
    # Cryptographic gate token
    seed = f"{fac_id}:{lot_id}:{time.time()}"
    gate_token = hashlib.sha256(seed.encode()).hexdigest()[:12].upper()
    qr_data = f"CRYOGUARD|{gate_token}|LOT:{lot_id}|BAY:04|ETA:{eta_arrival.strftime('%H:%M:%S')}"
    
    caps = facility.get("capabilities", [])
    if "ULTRA_LOW_CRYOGENIC" in caps or "LIQUID_NITROGEN_RECHARGE" in caps:
        bay_assigned = "Bay #04 (Cryogenic Liquid N2 Quick-Dock)"
        intake_crew = "Team Alpha - Certified Cryo Technicians"
        consumable = "Liquid Nitrogen (LN2) 180L High-Pressure Manifold"
    elif "COMPRESSOR_MECHANICAL_REPAIR" in caps:
        bay_assigned = "Bay #02 (Reefer Mechanical Lift & Evacuation)"
        intake_crew = "HVAC Master Technicians - Bay 2"
        consumable = "R452A Refrigerant + Sealant Charge Kit"
    else:
        bay_assigned = "Bay #01 (Cold Staging 2°C to 8°C Pre-Cool)"
        intake_crew = "Logistics Intake Squad B"
        consumable = "Dry-Ice Pellets + Active Air Chiller"

    return {
        "gate_pass_id": f"GP-{abs(hash(gate_token)) % 89999 + 10000}",
        "security_token": gate_token,
        "qr_payload": qr_data,
        "facility_name": fac_name,
        "assigned_bay": bay_assigned,
        "staging_crew": intake_crew,
        "consumable_reserved": consumable,
        "reservation_window": f"{window_start} - {window_end} (ETA: {eta_arrival.strftime('%H:%M:%S')})",
        "yard_status": "RESERVED & EN ROUTE",
        "dock_door_pin": f"{random.randint(1000, 9999)}",
        "eta_target": eta_arrival.strftime("%H:%M:%S"),
        "actual_dock_time": None,
        "servicing_started": None,
        "actual_release_time": None,
        "active_hold_remaining": service_duration_sec
    }

def update_yard_status(manifest: dict, stage: str, current_sim_time: datetime, hold_sec: int = 0) -> dict:
    """
    Updates the YMS manifest in real time as the carrier approaches, docks, services, and departs.
    """
    if not manifest:
        return manifest
        
    t_str = current_sim_time.strftime("%H:%M:%S")
    manifest["active_hold_remaining"] = hold_sec
    
    if stage == "SERVICING":
        if manifest["actual_dock_time"] is None:
            manifest["actual_dock_time"] = t_str
            manifest["servicing_started"] = t_str
        manifest["yard_status"] = f"DOCKED — ACTIVE RECHARGE ({hold_sec}s REMAINING)"
    elif stage == "FINAL_LEG":
        if manifest["actual_release_time"] is None:
            manifest["actual_release_time"] = t_str
        manifest["yard_status"] = f"COMPLETED & RELEASED (Departed at {t_str})"
    elif stage == "EN_ROUTE_HUB":
        manifest["yard_status"] = "RESERVED — INBOUND APPROACH"
        
    return manifest

def build_stakeholder_alerts(customer: dict, anomaly: dict, chosen_hub: dict, current_temp: float, eta_time_str: str) -> list:
    lot = customer.get("batch_lot", "LOT-99201")
    drug = customer.get("drug_product", "Cellular Biologic")
    val_usd = customer.get("valuation_usd", 470000)
    anom_name = anomaly.get("name", "Active Temperature Anomaly")
    hub_name = chosen_hub.get("name", "Regional Service Depot")
    
    return [
        {
            "id": f"ALT-{int(time.time())}-CAB",
            "channel": "🚚 IN-CAB DRIVER TELEMATICS (ELD / IoT)",
            "priority": "P1 - CRITICAL DIVERSION",
            "badge_color": "#ef4444",
            "recipient": "In-Cab Mobile Display Unit #409",
            "message": f"CRITICAL RE-ROUTE DIRECTIVE: Compressor fault confirmed. Core temp {current_temp:.1f}°C. Proceed immediately to {hub_name}. Bay #04 reserved. Do not attempt unapproved stop.",
            "protocol": "In-Cab Siren Tone Dispatched | Auto-Navigation Loaded",
            "webhook_status": "DISPATCHED_HTTP_200"
        },
        {
            "id": f"ALT-{int(time.time())}-QA",
            "channel": "🏢 SPONSOR QUALITY DESK (Pharma QA / PagerDuty)",
            "priority": "P1 - URGENT GXP DEVIATION",
            "badge_color": "#f97316",
            "recipient": f"{customer.get('customer_name')} Global QA Escalations",
            "message": f"Active thermal drift detected on Lot {lot} ({drug}). Asset value: ${val_usd:,} USD. CryoGuard AI executed autonomous diversion to {hub_name} within qualified stability envelope.",
            "protocol": "Webhook ➔ Veeva QualityDocs / TrackWise Deviation Logged",
            "webhook_status": "DISPATCHED_HTTP_202"
        },
        {
            "channel": "📡 FLEET OPERATIONS (Slack / Teams / TMS Webhook)",
            "id": f"ALT-{int(time.time())}-TMS",
            "priority": "P2 - HIGH DISPATCH",
            "badge_color": "#38bdf8",
            "recipient": "Logistics Dispatch Center & 3PL Tower",
            "message": f"Carrier #409 vectoring off-corridor to {hub_name}. Arrival ETA: {eta_time_str}. Gate pre-clearance token generated. No driver turnaround permitted.",
            "protocol": "REST API ➔ Enterprise TMS (EDI 214 Status Code: X6 Rerouted)",
            "webhook_status": "DISPATCHED_HTTP_200"
        },
        {
            "channel": "🏥 CONSIGNEE MEDICAL CENTER (Hospital Dock Lead)",
            "id": f"ALT-{int(time.time())}-HOSP",
            "priority": "P2 - SCHEDULE ADVISORY",
            "badge_color": "#a855f7",
            "recipient": f"{customer.get('consignee_facility')} Cryo-Intake",
            "message": f"Inbound critical biologic ({drug}) undergoing precautionary temperature restabilization. Updated clinical delivery window: {eta_time_str}. Patient OR coordination advised.",
            "protocol": "HL7 / FHIR Supply Chain Notification Triggered",
            "webhook_status": "DISPATCHED_HTTP_200"
        }
    ]

def dispatch_live_webhook(webhook_url: str, alert_payload: dict) -> dict:
    """
    Dispatches real JSON webhooks via HTTP POST to live endpoints
    (e.g., Slack Webhook, MS Teams Connector, PagerDuty, or requestbin).
    """
    if not webhook_url or not webhook_url.startswith("http"):
        return {"status": "SKIPPED_EMPTY_URL", "code": 0}
        
    try:
        data = json.dumps(alert_payload).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "CryoGuard-Alert-Daemon/2026.1"}
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            return {"status": "DELIVERED_SUCCESS", "code": resp.getcode()}
    except urllib.error.HTTPError as e:
        return {"status": f"HTTP_ERROR_{e.code}", "code": e.code}
    except Exception as ex:
        return {"status": f"CONNECTION_FAILED", "error": str(ex)}

import os

CONFIG_FILE = ".streamlit/webhook_config.json"

def get_persisted_webhook_url() -> str:
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("webhook_url", "")
    except Exception:
        pass
    return ""

def persist_webhook_url(url: str):
    try:
        os.makedirs(".streamlit", exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"webhook_url": url.strip()}, f, indent=2)
    except Exception:
        pass
