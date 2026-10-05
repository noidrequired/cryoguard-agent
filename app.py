import json
import math
import random
import time
import streamlit as st
import plotly.graph_objects as go
from src.agent import run_cryoguard_mission
from src.routing import get_driving_route, resample_waypoints

SIM_STEP_DELAY = 0.5

st.set_page_config(
    page_title="CryoGuard AI™ | Autonomous Operations Commander",
    page_icon="🧊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

RESOLUTION_LABELS = {
    "COLD_DOCK_RECHARGE": "Emergency Cold-Dock Diversion & Dry-Ice Recharge",
    "HOTSHOT_RELAY": "High-Priority Medical Hot-Shot Courier Relay (Gridlock Bypass)",
    "MOBILE_TECH_INTERCEPT": "24/7 Mobile Refrigeration Specialist Highway Intercept",
    "STERILE_RESEAL_INSPECT": "GxP Tamper-Evident Re-Seal & Barrier Inspection",
    "CRYOGENIC_LN2_RECHARGE": "Liquid Nitrogen High-Pressure Vapor Top-Off"
}

def format_tool_status(result_obj) -> str:
    """Safely extracts a display status from tool returns of any type."""
    if isinstance(result_obj, dict):
        return result_obj.get("status", result_obj.get("deviation_id", "CONFIRMED"))
    elif isinstance(result_obj, list):
        return f"{len(result_obj)} candidate facilities evaluated"
    elif isinstance(result_obj, str):
        return result_obj
    return "COMPLETED"

# --- HIGH-CONTRAST MISSION CONTROL DARK THEME ---
st.markdown("""
<style>
    .stApp {
        background-color: #090d16 !important;
        color: #f8fafc !important;
    }
    p, span, label, div, h1, h2, h3, h4, h5, h6 {
        color: #f8fafc;
    }
    
    .main-header {
        background: #111827 !important;
        border: 1px solid #1f2937 !important;
        border-radius: 10px;
        padding: 16px 24px;
        margin-bottom: 12px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
    }
    
    .config-card {
        background: #111827 !important;
        border: 1.5px solid #1f2937 !important;
        border-radius: 8px;
        padding: 14px 20px;
        margin-bottom: 14px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.2);
    }

    /* Selectbox Styling */
    .stSelectbox label {
        color: #94a3b8 !important;
        font-weight: 700 !important;
        font-size: 0.78rem !important;
        text-transform: uppercase;
        letter-spacing: 0.6px;
    }
    div[data-baseweb="select"] > div {
        background-color: #1e293b !important;
        border: 1px solid #334155 !important;
        color: #f8fafc !important;
        border-radius: 6px !important;
        height: 42px !important;
    }
    div[data-baseweb="select"] * {
        color: #f8fafc !important;
    }
    ul[data-baseweb="menu"] {
        background-color: #1e293b !important;
        border: 1px solid #334155 !important;
    }
    li[data-baseweb="option"] {
        color: #f8fafc !important;
    }
    li[data-baseweb="option"]:hover {
        background-color: #0284c7 !important;
    }

    /* Standardized Buttons */
    .stButton > button {
        border-radius: 6px !important;
        font-weight: 700 !important;
        font-size: 0.85rem !important;
        height: 42px !important;
        padding: 0 16px !important;
    }
    .stButton > button[kind="primary"] {
        background-color: #0284c7 !important;
        color: #ffffff !important;
        border: 1px solid #38bdf8 !important;
        box-shadow: 0 0 12px rgba(2, 132, 199, 0.4);
    }
    .stButton > button[kind="secondary"], 
    .stButton > button:not([kind="primary"]) {
        background-color: #1e293b !important;
        color: #f8fafc !important;
        border: 1.5px solid #334155 !important;
    }
    .stButton > button:hover {
        border-color: #38bdf8 !important;
        color: #38bdf8 !important;
    }

    /* Phase Progress Tracker */
    .phase-bar {
        display: flex;
        gap: 6px;
        margin: 6px 0 14px 0;
    }
    .phase-step {
        flex: 1;
        padding: 8px 6px;
        border-radius: 6px;
        font-size: 0.74rem;
        font-weight: 700;
        text-align: center;
        border: 1px solid #1f2937;
    }
    .phase-idle { background: #111827 !important; color: #64748b !important; }
    .phase-active { background: #0369a1 !important; color: #ffffff !important; border-color: #38bdf8 !important; box-shadow: 0 0 10px rgba(56, 189, 248, 0.3); }
    .phase-done { background: #14532d !important; color: #4ade80 !important; border-color: #22c55e !important; }
    .phase-alert { background: #7f1d1d !important; color: #fca5a5 !important; border-color: #ef4444 !important; }

    /* KPI Summary Cards */
    .kpi-card {
        background-color: #111827 !important;
        border: 1px solid #1f2937 !important;
        border-radius: 8px;
        padding: 14px 16px;
        text-align: left;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
    }
    .kpi-title {
        color: #94a3b8 !important;
        font-size: 0.74rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.6px;
    }
    .kpi-num {
        font-size: 1.55rem;
        font-weight: 800;
        margin: 3px 0;
    }
    .bad { color: #f87171 !important; }
    .good { color: #4ade80 !important; }
    .warn { color: #fbbf24 !important; }

    /* Structured Cognitive Monologue Box */
    .thought-container {
        background: #064e3b !important;
        border: 1.5px solid #059669 !important;
        border-radius: 8px;
        padding: 14px 18px;
        margin-bottom: 14px;
        box-shadow: 0 0 16px rgba(5, 150, 105, 0.25);
    }
    .thought-stage-pill {
        display: inline-block;
        font-weight: 800;
        font-size: 0.72rem;
        padding: 2px 8px;
        border-radius: 4px;
        margin-right: 6px;
        letter-spacing: 0.5px;
    }
    .stage-threat { background: #7f1d1d; color: #fee2e2; }
    .stage-contract { background: #1e3a8a; color: #dbeafe; }
    .stage-tradeoff { background: #78350f; color: #fef3c7; }
    .stage-action { background: #065f46; color: #d1fae5; }

    /* Live Stream Log Box */
    .log-box {
        background-color: #020617 !important;
        border: 1.5px solid #1e293b !important;
        border-radius: 8px;
        padding: 14px;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        font-size: 0.80rem;
        height: 380px;
        overflow-y: auto;
        color: #e2e8f0 !important;
    }
    .log-line {
        padding: 3px 0;
        border-bottom: 1px solid #0f172a;
        line-height: 1.45;
    }

    /* Tabs Styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        border-bottom: 2px solid #1e293b;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #111827 !important;
        border-radius: 6px 6px 0 0 !important;
        padding: 8px 16px !important;
        border: 1px solid #1e293b !important;
        border-bottom: none !important;
    }
    .stTabs [data-baseweb="tab"] p {
        color: #94a3b8 !important;
        font-weight: 600 !important;
        font-size: 0.88rem !important;
    }
    .stTabs [aria-selected="true"] {
        background-color: #1e293b !important;
        border-top: 3px solid #38bdf8 !important;
    }
    .stTabs [aria-selected="true"] p {
        color: #38bdf8 !important;
        font-weight: 800 !important;
    }

    /* Code & JSON Display */
    [data-testid="stJson"], [data-testid="stCodeBlock"], pre {
        background-color: #020617 !important;
        border: 1.5px solid #1e293b !important;
        border-radius: 6px !important;
        color: #e2e8f0 !important;
    }
    [data-testid="stJson"] * {
        color: #e2e8f0 !important;
    }
    code {
        background-color: #1e293b !important;
        color: #38bdf8 !important;
        font-weight: 700 !important;
        border: 1px solid #334155 !important;
        padding: 2px 5px !important;
        border-radius: 4px !important;
    }
    [data-testid="stExpander"] {
        background-color: #111827 !important;
        border: 1px solid #1f2937 !important;
        border-radius: 8px !important;
    }
    [data-testid="stExpander"] * {
        color: #f8fafc !important;
    }
</style>
""", unsafe_allow_html=True)

# Plotly Dark Matter Map Config
if hasattr(go, "Scattermap"):
    MapTrace = go.Scattermap
    map_config = dict(map_style="carto-darkmatter")
else:
    MapTrace = getattr(go, "Scattermapbox", go.Scatter)
    map_config = dict(mapbox_style="carto-darkmatter")

# Load All Databases
@st.cache_data
def load_all_databases():
    with open("data/customers.json", "r") as f:
        customers = json.load(f)
    with open("data/anomalies.json", "r") as f:
        anomalies = json.load(f)
    with open("data/sla_contracts.json", "r") as f:
        slas = json.load(f)
    with open("data/routes.json", "r") as f:
        routes = json.load(f)
    with open("data/telemetry_stream.json", "r") as f:
        raw_telemetry = json.load(f)
    return customers, anomalies, slas, routes, raw_telemetry

customers_pool, anomalies_pool, slas_db, routes_pool, base_telemetry = load_all_databases()

# Session State Initialization
if "has_run_started" not in st.session_state:
    st.session_state["has_run_started"] = False
if "is_running" not in st.session_state:
    st.session_state["is_running"] = False
if "mission_clock" not in st.session_state:
    st.session_state["mission_clock"] = 0
if "sim_state" not in st.session_state:
    st.session_state["sim_state"] = "STANDBY"
if "cur_lat" not in st.session_state:
    st.session_state["cur_lat"] = 0.0
if "cur_lon" not in st.session_state:
    st.session_state["cur_lon"] = 0.0
if "cur_temp" not in st.session_state:
    st.session_state["cur_temp"] = 3.5
if "cur_meter" not in st.session_state:
    st.session_state["cur_meter"] = 0
if "service_countdown" not in st.session_state:
    st.session_state["service_countdown"] = 0

# Dynamic OSRM Route Vectors
if "active_leg_points" not in st.session_state:
    st.session_state["active_leg_points"] = []
if "leg_point_idx" not in st.session_state:
    st.session_state["leg_point_idx"] = 0
if "passed_points" not in st.session_state:
    st.session_state["passed_points"] = []

if "active_customer" not in st.session_state:
    st.session_state["active_customer"] = None
if "active_route" not in st.session_state:
    st.session_state["active_route"] = None
if "chosen_hub" not in st.session_state:
    st.session_state["chosen_hub"] = None
if "active_anomaly" not in st.session_state:
    st.session_state["active_anomaly"] = None
if "anomaly_trigger_sec" not in st.session_state:
    st.session_state["anomaly_trigger_sec"] = 20
if "active_curveball" not in st.session_state:
    st.session_state["active_curveball"] = "NONE"
if "mission_result" not in st.session_state:
    st.session_state["mission_result"] = None

if "selected_customer_id" not in st.session_state:
    st.session_state["selected_customer_id"] = "AUTO"
if "selected_anomaly_id" not in st.session_state:
    st.session_state["selected_anomaly_id"] = "AUTO"
if "selected_curveball" not in st.session_state:
    st.session_state["selected_curveball"] = "AUTO"
if "is_partial_breach" not in st.session_state:
    st.session_state["is_partial_breach"] = False
if "run_logs" not in st.session_state:
    st.session_state["run_logs"] = []

# --- TOP HEADER ---
active_corr_label = st.session_state["active_route"]["corridor_name"] if st.session_state["has_run_started"] else "SYSTEM STANDBY (AWAITING MISSION LAUNCH)"

st.markdown(f"""
<div class="main-header">
    <div style="display: flex; justify-content: space-between; align-items: center;">
        <div>
            <h2 style="margin: 0; color: #f8fafc; font-weight: 800; font-size: 1.55rem;">🧊 CryoGuard AI™ | Operations Commander</h2>
            <span style="color: #94a3b8; font-size: 0.86rem; font-weight: 500;">OSRM Road-Navigated Telematics & Multi-Sponsor Quality Agreement Defense</span>
        </div>
        <div style="text-align: right;">
            <span style="background: #1e293b; border: 1px solid #38bdf8; color: #38bdf8; padding: 6px 14px; border-radius: 20px; font-size: 0.80rem; font-weight: 700;">
                {active_corr_label}
            </span>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# =========================================================================
# 1. DYNAMIC CONFIGURATION PANEL
# =========================================================================
with st.container():
    st.markdown('<div class="config-card">', unsafe_allow_html=True)
    c1, c2, c3, c4, c5 = st.columns([1.3, 1.3, 1.3, 1.0, 1.0])

    with c1:
        cust_opts = {"AUTO": "🎲 Auto (Random Sponsor)"}
        for c in customers_pool:
            cust_opts[c["customer_id"]] = f"{c['customer_name']} ({c['drug_product'][:20]}...)"
        
        sel_cust = st.selectbox(
            "Customer Sponsor & Cargo:",
            options=list(cust_opts.keys()),
            format_func=lambda k: cust_opts[k],
            index=list(cust_opts.keys()).index(st.session_state["selected_customer_id"]),
            disabled=st.session_state["is_running"]
        )
        st.session_state["selected_customer_id"] = sel_cust

    with c2:
        anomaly_opts = {"AUTO": "🎲 Auto (Dynamic Runtime Fault)"}
        for a in anomalies_pool:
            anomaly_opts[a["id"]] = f"{a['name']} ({a['category']})"
        
        sel_anom = st.selectbox(
            "Anomaly Protocol:",
            options=list(anomaly_opts.keys()),
            format_func=lambda k: anomaly_opts[k],
            index=list(anomaly_opts.keys()).index(st.session_state["selected_anomaly_id"]),
            disabled=st.session_state["is_running"]
        )
        st.session_state["selected_anomaly_id"] = sel_anom

    with c3:
        curveball_opts = {
            "AUTO": "🎲 Auto (Evaluate during triage)",
            "NONE": "Nominal Protocol (No Curveball)",
            "POWER_OUTAGE": "⚡ Substation Power Outage at Primary Hub",
            "DETOUR_BLOCKED": "🚧 Highway Detour Gridlock / Closure",
            "SURGERY_MOVED_UP": "🏥 Surgery Time Accelerated (-45m SLA)"
        }
        sel_cb = st.selectbox(
            "Corridor Modifier:",
            options=list(curveball_opts.keys()),
            format_func=lambda k: curveball_opts[k],
            index=list(curveball_opts.keys()).index(st.session_state["selected_curveball"]),
            disabled=st.session_state["is_running"]
        )
        st.session_state["selected_curveball"] = sel_cb

    with c4:
        st.write("")
        st.write("")
        if not st.session_state["is_running"]:
            if st.button("▶️ Launch", type="primary", use_container_width=True):
                chosen_route = random.choice(routes_pool)
                
                if st.session_state["selected_customer_id"] == "AUTO":
                    chosen_cust = random.choice(customers_pool)
                else:
                    chosen_cust = next(c for c in customers_pool if c["customer_id"] == st.session_state["selected_customer_id"])

                # Fetch real OSRM highway route for this corridor
                o = chosen_route["origin"]
                dest = chosen_route["destination"]
                road_route = get_driving_route(o["lat"], o["lon"], dest["lat"], dest["lon"])
                
                # Resample highway line to ~70 animated road waypoints
                sampled_pts = resample_waypoints(road_route["waypoints"], target_count=70)

                st.session_state["active_customer"] = chosen_cust
                st.session_state["active_route"] = chosen_route
                st.session_state["active_leg_points"] = sampled_pts
                st.session_state["leg_point_idx"] = 0
                st.session_state["active_anomaly"] = None
                st.session_state["chosen_hub"] = None
                st.session_state["active_curveball"] = "NONE"
                st.session_state["anomaly_trigger_sec"] = random.randint(16, 24)
                
                st.session_state["cur_lat"] = sampled_pts[0]["lat"]
                st.session_state["cur_lon"] = sampled_pts[0]["lon"]
                st.session_state["cur_temp"] = 3.5
                st.session_state["cur_meter"] = 0
                
                st.session_state["mission_clock"] = 0
                st.session_state["sim_state"] = "NOMINAL"
                st.session_state["mission_result"] = None
                st.session_state["passed_points"] = [{"sec": 0, "temp": 3.5, "lat": st.session_state["cur_lat"], "lon": st.session_state["cur_lon"]}]
                st.session_state["has_run_started"] = True
                st.session_state["run_logs"] = [
                    f"[T+00s] 🟢 Fleet telematics online. Unit #409 departed {chosen_route['origin']['name']}.",
                    f"[T+00s] 🛣️ OSRM Route: {road_route['distance_miles']} driving miles via interstate network ({road_route['source']}).",
                    f"[T+00s] 🏢 Sponsor: {chosen_cust['customer_name']} | Agreement: {chosen_cust['contract_title']}",
                    f"[T+00s] 📦 Drug Therapy: {chosen_cust['drug_product']} (Valuation: ${chosen_cust['valuation_usd']:,} USD)"
                ]
                st.session_state["is_running"] = True
                st.rerun()
        else:
            if st.button("⏹ Stop", type="secondary", use_container_width=True):
                st.session_state["is_running"] = False
                st.rerun()

    with c5:
        st.write("")
        st.write("")
        if st.button("🔄 Reset", type="secondary", use_container_width=True):
            st.session_state["has_run_started"] = False
            st.session_state["is_running"] = False
            st.session_state["mission_clock"] = 0
            st.session_state["sim_state"] = "STANDBY"
            st.session_state["active_customer"] = None
            st.session_state["active_route"] = None
            st.session_state["chosen_hub"] = None
            st.session_state["active_anomaly"] = None
            st.session_state["active_curveball"] = "NONE"
            st.session_state["mission_result"] = None
            st.session_state["active_leg_points"] = []
            st.session_state["passed_points"] = []
            st.session_state["run_logs"] = []
            st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

# Mission Clock & Mid-Flight Curveball Bar
bar_c1, bar_c2 = st.columns([2, 1.2])
with bar_c1:
    if st.session_state["has_run_started"]:
        cur_sec = st.session_state["mission_clock"]
        cust_badge = st.session_state['active_customer']['customer_name']
        st.markdown(f"""
        <div style="padding: 2px 0 6px 0;">
            <span style="font-size: 1.35rem; font-weight: 800; color: #f8fafc;">⏱️ Mission Clock: T+{cur_sec:02d}s</span>
            <span style="margin-left: 12px; font-size: 0.88rem; color: #38bdf8; font-family: ui-monospace, monospace; font-weight: 700;">
                {st.session_state['cur_meter']:,}m | ({st.session_state['cur_lat']:.5f}, {st.session_state['cur_lon']:.5f})
            </span>
            <span style="margin-left: 12px; background: #1e293b; color: #94a3b8; font-size: 0.8rem; padding: 4px 10px; border-radius: 4px;">
                Client: <b>{cust_badge}</b>
            </span>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("<div style='padding-top: 4px;'><span style='color: #64748b; font-weight: 600;'>Mission Standby — Select customer parameters and click Launch</span></div>", unsafe_allow_html=True)

with bar_c2:
    if st.session_state["has_run_started"] and st.session_state["is_running"]:
        if st.session_state["sim_state"] == "EN_ROUTE_HUB":
            if st.button("⚡ Inject Surprise Disruption at Hub!", type="primary", use_container_width=True):
                st.session_state["active_curveball"] = "POWER_OUTAGE"
                st.session_state["run_logs"].append(f"[T+{st.session_state['mission_clock']:02d}s] ⚠️ SURPRISE DISRUPTION: Target Hub reporting transformer explosion! Emergency re-plan triggered!")
                st.rerun()

# --- DYNAMIC PHASE PROGRESS BAR ---
if not st.session_state["has_run_started"]:
    st.markdown("""
    <div class="phase-bar">
        <div class="phase-step phase-idle">1. Nominal Cruise</div>
        <div class="phase-step phase-idle">2. Anomaly Ingestion</div>
        <div class="phase-step phase-idle">3. AI Autonomous Triage</div>
        <div class="phase-step phase-idle">4. Facility Servicing</div>
        <div class="phase-step phase-idle">5. Delivery & Audit</div>
    </div>
    """, unsafe_allow_html=True)
else:
    s_state = st.session_state["sim_state"]
    p1 = "phase-done" if s_state != "NOMINAL" else "phase-active"
    p2 = "phase-alert" if s_state == "FAULT_DETECTED" else ("phase-done" if s_state in ["EN_ROUTE_HUB", "SERVICING", "FINAL_LEG", "DELIVERED"] else "phase-idle")
    p3 = "phase-active" if s_state == "EN_ROUTE_HUB" else ("phase-done" if s_state in ["SERVICING", "FINAL_LEG", "DELIVERED"] else "phase-idle")
    p4 = "phase-active" if s_state == "SERVICING" else ("phase-done" if s_state in ["FINAL_LEG", "DELIVERED"] else "phase-idle")
    p5 = "phase-done" if s_state == "DELIVERED" else ("phase-active" if s_state == "FINAL_LEG" else "phase-idle")

    st.markdown(f"""
    <div class="phase-bar">
        <div class="phase-step {p1}">1. Nominal Cruise</div>
        <div class="phase-step {p2}">2. Anomaly Ingested</div>
        <div class="phase-step {p3}">3. AI Detour Navigation</div>
        <div class="phase-step {p4}">4. Facility Servicing</div>
        <div class="phase-step {p5}">5. Delivery & Audit</div>
    </div>
    """, unsafe_allow_html=True)

# --- DYNAMIC CONTRACTUAL KPI ROW ---
k1, k2, k3, k4 = st.columns(4)

if not st.session_state["has_run_started"]:
    for k, title, val in [(k1, "Cargo Sensor Temp", "-- °C"), (k2, "Excursion Runway", "-- Mins"), (k3, "Delivery Window", "--:-- AM"), (k4, "Financial Exposure", "$0")]:
        with k:
            st.markdown(f"<div class='kpi-card'><div class='kpi-title'>{title}</div><div class='kpi-num' style='color: #64748b;'>{val}</div><div style='font-size: 0.75rem; color: #64748b;'>Standby</div></div>", unsafe_allow_html=True)
else:
    cur_temp = st.session_state["cur_temp"]
    is_hot = cur_temp > 6.0
    anom = st.session_state["active_anomaly"]
    cust = st.session_state["active_customer"]

    if anom and cust:
        sla_key = anom.get("sla_governed", cust.get("governing_sla_id", "SLA-COLD-2TO8"))
        governing_sla = slas_db.get(sla_key, slas_db["SLA-COLD-2TO8"])
        sla_exposure_usd = cust.get("valuation_usd", 470000)
        ceiling_temp = governing_sla.get("excursion_ceiling", 8.0)
        band_spec = governing_sla.get("thermal_band", "+2.0°C to +8.0°C")
    else:
        sla_exposure_usd = cust.get("valuation_usd", 470000) if cust else 470000
        ceiling_temp = 8.0
        band_spec = "+2.0°C to +8.0°C"
        sla_key = "PENDING_INCIDENT"

    with k1:
        st.markdown(f"<div class='kpi-card'><div class='kpi-title'>Cargo Sensor Temp</div><div class='kpi-num {'bad' if is_hot else 'good'}'>{cur_temp:.1f} °C</div><div style='font-size: 0.75rem; color: #94a3b8;'>Band: {band_spec}</div></div>", unsafe_allow_html=True)
    with k2:
        runway_val = f"{max(4, int((ceiling_temp - cur_temp) / 0.04))} Mins" if is_hot else "NOMINAL"
        st.markdown(f"<div class='kpi-card'><div class='kpi-title'>Excursion Runway</div><div class='kpi-num {'bad' if is_hot else 'good'}'>{runway_val}</div><div style='font-size: 0.75rem; color: #94a3b8;'>Ceiling: {ceiling_temp}°C</div></div>", unsafe_allow_html=True)
    with k3:
        eta_str = "05:54 AM (On Time)" if not is_hot else "06:45 AM (Late)"
        eta_col = "good" if not is_hot else "bad"
        st.markdown(f"<div class='kpi-card'><div class='kpi-title'>Delivery Window</div><div class='kpi-num {eta_col}'>{eta_str}</div><div style='font-size: 0.75rem; color: #94a3b8;'>SLA Hard-Stop: 06:00 AM CT</div></div>", unsafe_allow_html=True)
    with k4:
        if is_hot:
            expo_str = f"${sla_exposure_usd:,}"
            expo_col = "bad"
            expo_sub = f"Liability: {cust.get('customer_name')[:20]}"
        elif st.session_state["sim_state"] == "DELIVERED":
            if st.session_state["is_partial_breach"]:
                partial_pen = 5000
                saved_net = sla_exposure_usd - partial_pen
                expo_str = f"${saved_net:,} SAVED"
                expo_col = "warn"
                expo_sub = f"⚠️ ${partial_pen:,} penalty deducted"
            else:
                expo_str = f"${sla_exposure_usd:,} SAVED"
                expo_col = "good"
                expo_sub = f"Zero penalties for {cust.get('customer_name')[:18]}"
        else:
            expo_str = "$0 AT RISK"
            expo_col = "good"
            expo_sub = f"Insured: ${sla_exposure_usd:,} USD"

        st.markdown(f"<div class='kpi-card'><div class='kpi-title'>Financial Protection</div><div class='kpi-num {expo_col}'>{expo_str}</div><div style='font-size: 0.75rem; color: #94a3b8;'>{expo_sub}</div></div>", unsafe_allow_html=True)

# =========================================================================
# STRUCTURED COGNITIVE STREAM (AI INNER MONOLOGUE)
# =========================================================================
if st.session_state["has_run_started"] and st.session_state["mission_result"]:
    res = st.session_state["mission_result"]
    raw_thoughts = list(res.get("cognitive_monologue", []))

    if raw_thoughts:
        st.markdown('<div class="thought-container">', unsafe_allow_html=True)
        st.markdown(f"""
        <div style="font-weight: 800; font-size: 0.88rem; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center;">
            <span style="color: #6ee7b7;">🧠 Gemini Live Cognitive Deliberation Feed (Engine: {', '.join(res['models_involved'])})</span>
            <span style="background: #047857; color: #ecfdf5; font-size: 0.75rem; font-weight: 700; padding: 2px 10px; border-radius: 12px;">
                Verified Multi-Turn Reasoning
            </span>
        </div>
        """, unsafe_allow_html=True)

        for thought in raw_thoughts:
            formatted_thought = thought
            formatted_thought = formatted_thought.replace("[THREAT ANALYSIS]:", '<span class="thought-stage-pill stage-threat">THREAT ANALYSIS</span>')
            formatted_thought = formatted_thought.replace("[CONTRACT AUDIT]:", '<span class="thought-stage-pill stage-contract">CONTRACT AUDIT</span>')
            formatted_thought = formatted_thought.replace("[FACILITY TRADE-OFF]:", '<span class="thought-stage-pill stage-tradeoff">FACILITY TRADE-OFF</span>')
            formatted_thought = formatted_thought.replace("[DISPATCH ACTION]:", '<span class="thought-stage-pill stage-action">DISPATCH ACTION</span>')
            
            st.markdown(f"<div style='margin-bottom: 6px; font-size: 0.84rem; line-height: 1.45; color: #d1fae5;'>{formatted_thought}</div>", unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)

# =========================================================================
# OPERATIONAL SECTION HEADERS AS TABS
# =========================================================================
tab_unified, tab_agent, tab_contract, tab_threat, tab_gxp = st.tabs([
    "🖥️ Unified Live Telematics & Log Stream",
    "🤖 Agent Tool Trace & Function Execution",
    "📑 Customer Contract & Governing Agreement",
    "🚨 Threat Physics & Thermal Excursion Curve",
    "📜 Certified GxP / FDA 21 CFR Part 11 Audit Log"
])

# --- TAB 1: UNIFIED STREAM (STRICTLY 1 MAP ON SCREEN) ---
with tab_unified:
    map_col, log_col = st.columns([1.15, 1])

    with map_col:
        st.markdown("<h5 style='margin-bottom: 6px;'>🗺️ Closed-Loop Telematics Map (OSRM Road Navigation)</h5>", unsafe_allow_html=True)
        fig_map = go.Figure()

        if not st.session_state["has_run_started"]:
            fig_map.add_trace(MapTrace(
                lat=[39.8283], lon=[-98.5795], mode='markers+text',
                marker=dict(size=10, color='#64748b'), text=["System in Standby"]
            ))
            fig_map.update_layout(**map_config, map=dict(center=dict(lat=39.8, lon=-98.5), zoom=3.5), margin=dict(l=0, r=0, t=0, b=0), height=380, showlegend=False)
        else:
            route_info = st.session_state["active_route"]
            chosen_hub = st.session_state["chosen_hub"]
            passed_pts = st.session_state["passed_points"]
            leg_pts = st.session_state["active_leg_points"]

            # Real Highway Network Polyline
            if leg_pts:
                fig_map.add_trace(MapTrace(
                    lat=[p["lat"] for p in leg_pts],
                    lon=[p["lon"] for p in leg_pts],
                    mode='lines',
                    line=dict(width=3, color="#38bdf8"),
                    name="Highway Network Route"
                ))

            # Breadcrumb trail of traversed points
            if passed_pts:
                fig_map.add_trace(MapTrace(
                    lat=[p["lat"] for p in passed_pts],
                    lon=[p["lon"] for p in passed_pts],
                    mode='lines',
                    line=dict(width=4, color="#ef4444" if cur_temp > 6.0 else "#22c55e"),
                    name="Traversed Path"
                ))

            # Vehicle marker
            fig_map.add_trace(MapTrace(
                lat=[st.session_state["cur_lat"]],
                lon=[st.session_state["cur_lon"]],
                mode='markers+text',
                marker=dict(size=18, color="#ef4444" if cur_temp > 6.0 else "#38bdf8"),
                text=[f"Unit #409 ({cur_temp:.1f}°C)"],
                textposition="top right",
                name="Carrier"
            ))

            fac_lats = [route_info["origin"]["lat"], route_info["destination"]["lat"]]
            fac_lons = [route_info["origin"]["lon"], route_info["destination"]["lon"]]
            fac_texts = [route_info["origin"]["name"], route_info["destination"]["name"]]
            fac_colors = ['#64748b', '#38bdf8']

            if chosen_hub:
                fac_lats.append(chosen_hub["lat"])
                fac_lons.append(chosen_hub["lon"])
                fac_texts.append(f"⭐ AI Target: {chosen_hub['name']}")
                fac_colors.append('#fbbf24')

            fig_map.add_trace(MapTrace(
                lat=fac_lats, lon=fac_lons, mode='markers+text',
                marker=dict(size=12, color=fac_colors),
                text=fac_texts, textposition="bottom right", name="Facilities"
            ))

            c_lat = (route_info["origin"]["lat"] + route_info["destination"]["lat"]) / 2.0
            c_lon = (route_info["origin"]["lon"] + route_info["destination"]["lon"]) / 2.0
            fig_map.update_layout(**map_config, uirevision="corridor_map", map=dict(center=dict(lat=c_lat, lon=c_lon), zoom=5.8), margin=dict(l=0, r=0, t=0, b=0), height=380, showlegend=False)

        st.plotly_chart(fig_map, use_container_width=True)

    with log_col:
        st.markdown("<h5 style='margin-bottom: 6px;'>📜 Real-Time Autonomous Operations Log Stream</h5>", unsafe_allow_html=True)
        if not st.session_state["has_run_started"]:
            log_html = '<div class="log-box"><div class="log-line">[T+00s] ⚪ System in standby. Select customer parameters and click "Launch".</div></div>'
        else:
            log_html = '<div class="log-box">'
            for entry in reversed(st.session_state["run_logs"]):
                log_html += f'<div class="log-line">{entry}</div>'
            log_html += '</div>'
        st.markdown(log_html, unsafe_allow_html=True)

# --- TAB 2: AGENT TOOL TRACE ---
with tab_agent:
    st.markdown("### 🤖 Autonomous Agent Reasoning & Function Calling Engine")
    if not st.session_state["has_run_started"]:
        st.info("Agent is standing by. Click 'Launch' to awaken the Gemini decision loop.")
    elif not st.session_state["mission_result"]:
        st.info("Autonomous agent in standby monitoring mode. Anomaly detection pending...")
    else:
        res = st.session_state["mission_result"]
        st.success(f"✅ Mission Orchestration Active: {res['steps_executed']} Autonomous Operations Executed via Gemini ({', '.join(res['models_involved'])})")

        for step in res["trace"]:
            st.markdown(f"""
            <div style="background: #111827; border-left: 4px solid #38bdf8; border: 1.5px solid #1f2937; padding: 10px 14px; margin-bottom: 8px; border-radius: 4px;">
                <span style="font-weight: 700; color: #f8fafc;">Step {step['step']}: <code>{step['tool_called']}</code></span>
                <span style="color: #94a3b8; font-size: 0.8rem; margin-left: 10px;">Model: {step['model_engine']}</span>
            </div>
            """, unsafe_allow_html=True)
            st.json(step["result"])

# --- TAB 3: CUSTOMER CONTRACT AUDIT ---
with tab_contract:
    st.markdown("### 📑 Customer Contract & Governing Quality Agreement")
    if not st.session_state["has_run_started"]:
        st.info("System in standby. Sponsor Quality Agreement will render upon mission launch.")
    else:
        cust = st.session_state["active_customer"]
        anom = st.session_state["active_anomaly"]
        sla_key = anom.get("sla_governed", cust.get("governing_sla_id", "SLA-COLD-2TO8")) if anom else cust.get("governing_sla_id", "SLA-COLD-2TO8")
        sla_val = slas_db.get(sla_key, slas_db["SLA-COLD-2TO8"])

        c_c1, c_c2 = st.columns(2)
        with c_c1:
            st.markdown(f"""
            #### 🏢 Commercial Sponsor Profile
            - **Client Organization:** `{cust['customer_name']}` (ID: `{cust['customer_id']}`)
            - **Therapeutic Asset:** `{cust['drug_product']}`
            - **Batch Lot Number:** `{cust['batch_lot']}`
            - **Commercial Valuation:** `${cust['valuation_usd']:,} USD`
            - **Consignee Medical Facility:** `{cust['consignee_facility']}`
            """)
        with c_c2:
            st.markdown(f"""
            #### 📜 Governing Legal Quality Agreement
            - **Agreement Title:** `{cust['contract_title']}`
            - **SLA Schedule Tier:** `{sla_val['name']}` (`{sla_key}`)
            - **Qualified Thermal Band:** `{sla_val['thermal_band']}`
            - **Regulatory Excursion Ceiling:** `{sla_val['excursion_ceiling']}°C`
            - **Max Allowed Excursion Window:** `{cust.get('allowed_excursion_mins', 60)} minutes`
            - **Liquidated Delay Penalty:** `{cust['delay_liquidated_damages']}`
            """)

# --- TAB 4: THREAT PHYSICS ---
with tab_threat:
    st.markdown("### 🚨 Threat Ingestion & Excursion Physics")
    if not st.session_state["has_run_started"]:
        st.info("System in standby. Initiate a mission to inspect anomaly physics.")
    else:
        t_c1, t_c2 = st.columns([1, 1.2])
        with t_c1:
            hub_name = st.session_state["chosen_hub"]["name"] if st.session_state["chosen_hub"] else "Evaluating Hubs..."
            anom_name = anom.get("name") if anom else "Scanning Sensors..."
            fault_code = anom.get("fault_code") if anom else "NOMINAL"
            st.markdown(f"""
            **Active Threat & Contract Evaluation:**
            - **Incident Anomaly:** `{anom_name}`
            - **Fault Code:** `{fault_code}`
            - **Active Target Facility:** **{hub_name}**
            - **Active Curveball Modifier:** `{st.session_state.get('active_curveball', 'NONE')}`
            - **Operational State:** `{st.session_state['sim_state']}`
            """)
        with t_c2:
            passed_pts = st.session_state["passed_points"]
            fig_t = go.Figure()
            fig_t.add_trace(go.Scatter(
                x=[p["sec"] for p in passed_pts],
                y=[p["temp"] for p in passed_pts],
                mode="lines+markers",
                line=dict(color="#ef4444" if cur_temp > 6.0 else "#22c55e", width=3),
                name="Cargo Temp"
            ))
            fig_t.add_hline(y=ceiling_temp, line_dash="dot", line_color="#fbbf24", annotation_text=f"SLA Ceiling ({ceiling_temp}°C)")
            fig_t.update_layout(title="Dynamic Sensor Trajectory (°C vs Time)", xaxis_title="Seconds Elapsed", yaxis_title="Temp (°C)", template="plotly_dark", height=260, margin=dict(l=20, r=20, t=35, b=20))
            st.plotly_chart(fig_t, use_container_width=True)

# --- TAB 5: GXP AUDIT ---
with tab_gxp:
    st.markdown("### 📜 Certified GxP / FDA 21 CFR Part 11 Regulatory Audit Log")
    if not st.session_state["has_run_started"] or not st.session_state["mission_result"]:
        st.info("Regulatory CAPA deviation log will compile dynamically upon incident resolution.")
    else:
        res = st.session_state["mission_result"]
        gxp_report = next((s["result"] for s in res["trace"] if s["tool_called"] == "generate_gxp_deviation_report"), None)
        if gxp_report:
            st.json(gxp_report)
            st.download_button(
                label="📥 Download Certified GxP Deviation Notice (JSON)",
                data=json.dumps(gxp_report, indent=2),
                file_name=f"GxP_Deviation_{res['incident_id']}.json",
                mime="application/json"
            )

# =========================================================================
# OSRM-POWERED CONTINUOUS VEHICLE ADVANCEMENT ENGINE
# =========================================================================
if st.session_state.get("is_running", False) and st.session_state.get("has_run_started", False):
    time.sleep(SIM_STEP_DELAY)
    
    st.session_state["mission_clock"] += 1
    clock = st.session_state["mission_clock"]
    s_state = st.session_state["sim_state"]
    route_info = st.session_state["active_route"]
    cust = st.session_state["active_customer"]
    f_sec = st.session_state["anomaly_trigger_sec"]
    
    leg_pts = st.session_state["active_leg_points"]
    pt_idx = st.session_state["leg_point_idx"]
    
    # Advance along actual OSRM waypoints
    if pt_idx < len(leg_pts) - 1:
        st.session_state["leg_point_idx"] += 1
        next_pt = leg_pts[st.session_state["leg_point_idx"]]
        st.session_state["cur_lat"] = next_pt["lat"]
        st.session_state["cur_lon"] = next_pt["lon"]
        st.session_state["cur_meter"] += 160

    # 1. NOMINAL STATE: Moving along main highway
    if s_state == "NOMINAL":
        st.session_state["cur_temp"] = round(3.5 + random.uniform(-0.03, 0.03), 2)
        st.session_state["run_logs"].append(
            f"[T+{clock:02d}s] 📍 GPS ({st.session_state['cur_lat']:.5f}, {st.session_state['cur_lon']:.5f}) | Temp: {st.session_state['cur_temp']}°C | Odometer: {st.session_state['cur_meter']:,}m | HIGHWAY_CRUISE"
        )
        
        # Trigger runtime anomaly
        if clock >= f_sec:
            st.session_state["sim_state"] = "FAULT_DETECTED"
            st.session_state["cur_temp"] = 6.4
            
            if st.session_state["selected_anomaly_id"] == "AUTO":
                active_anom = random.choice(anomalies_pool)
            else:
                active_anom = next(a for a in anomalies_pool if a["id"] == st.session_state["selected_anomaly_id"])
            st.session_state["active_anomaly"] = active_anom
            
            if st.session_state["selected_curveball"] == "AUTO":
                chosen_cb = random.choice(["NONE", "POWER_OUTAGE", "DETOUR_BLOCKED", "SURGERY_MOVED_UP"])
            else:
                chosen_cb = st.session_state["selected_curveball"]
            st.session_state["active_curveball"] = chosen_cb

            sla_key = active_anom.get("sla_governed", cust.get("governing_sla_id", "SLA-COLD-2TO8"))
            matched_sla = slas_db.get(sla_key, slas_db["SLA-COLD-2TO8"])
            risk_usd = cust.get("valuation_usd", 470000)
            
            st.session_state["run_logs"].append(
                f"[T+{clock:02d}s] 🚨 SENSOR FAULT DETECTED: {active_anom['name']} ({active_anom['fault_code']})!"
            )
            st.session_state["run_logs"].append(
                f"[T+{clock:02d}s] 📑 Contract Audit: Triggered {cust['contract_title']} (Valuation: ${risk_usd:,} USD)"
            )
            if chosen_cb != "NONE":
                st.session_state["run_logs"].append(f"[T+{clock:02d}s] ⚠️ Active Corridor Modifier: {chosen_cb}")
            
            # Invoke Gemini Agent
            active_payload = json.loads(json.dumps(base_telemetry))
            active_payload["customer_data"] = cust
            active_payload["governing_sla_id"] = sla_key
            active_payload["candidate_hubs"] = route_info.get("candidate_hubs", [])
            active_payload["curveball_condition"] = chosen_cb
            active_payload["incident_event"]["location"]["latitude"] = st.session_state["cur_lat"]
            active_payload["incident_event"]["location"]["longitude"] = st.session_state["cur_lon"]
            active_payload["incident_event"]["sensor_readings"]["compressor_status"] = active_anom["fault_code"]
            active_payload["incident_event"]["sensor_readings"]["cargo_temperature_celsius"] = 6.4
            
            res = run_cryoguard_mission(active_payload, is_replan=False)
            st.session_state["mission_result"] = res
            
            # Identify AI's chosen hub
            res_dock_call = next((s for s in res["trace"] if s["tool_called"] == "reserve_dock_replenishment"), None)
            cand_hubs = route_info.get("candidate_hubs", [])
            if res_dock_call:
                assigned_id = res_dock_call["arguments"].get("facility_id")
                chosen_hub = next((h for h in cand_hubs if h["facility_id"] == assigned_id), cand_hubs[0])
            else:
                chosen_hub = cand_hubs[0]
                
            st.session_state["chosen_hub"] = chosen_hub
            
            # Stitch real OSRM detour route from current GPS position to chosen hub
            detour_meta = get_driving_route(st.session_state["cur_lat"], st.session_state["cur_lon"], chosen_hub["lat"], chosen_hub["lon"])
            detour_pts = resample_waypoints(detour_meta["waypoints"], target_count=18)
            
            st.session_state["active_leg_points"] = detour_pts
            st.session_state["leg_point_idx"] = 0
            st.session_state["service_countdown"] = 14
            st.session_state["sim_state"] = "EN_ROUTE_HUB"
            
            for s in res["trace"]:
                st_str = format_tool_status(s.get("result"))
                st.session_state["run_logs"].append(
                    f"[T+{clock:02d}s] 🤖 Agent: Executed `{s['tool_called']}` ➔ {st_str}"
                )
            st.session_state["run_logs"].append(
                f"[T+{clock:02d}s] 🚀 Detour Route Calculated: Navigating via OSRM roads to {chosen_hub['name']} ({detour_meta['distance_miles']} mi)."
            )

    # 2. EN_ROUTE_HUB STATE: Detouring to hub along real road points
    elif s_state == "EN_ROUTE_HUB":
        st.session_state["cur_temp"] = round(min(7.35, st.session_state["cur_temp"] + 0.06), 2)
        st.session_state["run_logs"].append(
            f"[T+{clock:02d}s] 🛣️ Detour Transit: En route to {st.session_state['chosen_hub']['name']}. Temp: {st.session_state['cur_temp']}°C."
        )
        
        # Check arrival at hub
        if pt_idx >= len(leg_pts) - 1:
            st.session_state["sim_state"] = "SERVICING"
            st.session_state["run_logs"].append(
                f"[T+{clock:02d}s] 🏢 Bay Arrival: Docked at {st.session_state['chosen_hub']['name']} Door #04. Servicing initiated."
            )

    # 3. SERVICING STATE: Replenishing cooling
    elif s_state == "SERVICING":
        st.session_state["service_countdown"] -= 1
        st.session_state["cur_temp"] = round(max(3.6, st.session_state["cur_temp"] - 0.28), 2)
        
        st.session_state["run_logs"].append(
            f"[T+{clock:02d}s] ❄️ Servicing Active: Cryo charging in progress. Temp: {st.session_state['cur_temp']}°C. (Hold: {st.session_state['service_countdown']}s)"
        )
        
        if st.session_state["service_countdown"] <= 0:
            st.session_state["sim_state"] = "FINAL_LEG"
            
            # Fetch real OSRM route from hub to hospital destination
            dest = route_info["destination"]
            hub = st.session_state["chosen_hub"]
            final_meta = get_driving_route(hub["lat"], hub["lon"], dest["lat"], dest["lon"])
            final_pts = resample_waypoints(final_meta["waypoints"], target_count=22)
            
            st.session_state["active_leg_points"] = final_pts
            st.session_state["leg_point_idx"] = 0
            
            st.session_state["run_logs"].append(
                f"[T+{clock:02d}s] ✅ Servicing Complete: Thermal envelope restored (3.6°C). Merging onto highway to {cust['consignee_facility']}."
            )

    # 4. FINAL_LEG STATE: High-speed transit to destination
    elif s_state == "FINAL_LEG":
        st.session_state["cur_temp"] = round(3.6 + random.uniform(-0.02, 0.02), 2)
        st.session_state["run_logs"].append(
            f"[T+{clock:02d}s] 🛣️ Final Mile Approach: {st.session_state['cur_meter']:,}m traversed. Stabilized at {st.session_state['cur_temp']}°C."
        )
        
        if pt_idx >= len(leg_pts) - 1:
            st.session_state["sim_state"] = "DELIVERED"
            st.session_state["is_running"] = False
            saved_total = cust.get("valuation_usd", 470000)
            
            st.session_state["run_logs"].append(
                f"[T+{clock:02d}s] 🏥 Consignee Delivery Complete: Delivered at {cust['consignee_facility']}. Zero batch spoilage! Preserved ${saved_total:,} USD under {cust['contract_title']}."
            )

    # Record historical breadcrumb point
    st.session_state["passed_points"].append({
        "sec": clock,
        "temp": st.session_state["cur_temp"],
        "lat": st.session_state["cur_lat"],
        "lon": st.session_state["cur_lon"]
    })

    st.rerun()
