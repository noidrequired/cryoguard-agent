import json
import math
import random
import time
import streamlit as st
import plotly.graph_objects as go
from src.agent import run_cryoguard_mission

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
    """Safely extracts a display status from tool returns of any type (dict, list, str)."""
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
    /* Global Background & Text */
    .stApp {
        background-color: #090d16 !important;
        color: #f8fafc !important;
    }
    p, span, label, div, h1, h2, h3, h4, h5, h6 {
        color: #f8fafc;
    }
    
    /* Top Header */
    .main-header {
        background: #111827 !important;
        border: 1px solid #1f2937 !important;
        border-radius: 10px;
        padding: 14px 22px;
        margin-bottom: 12px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
    }
    
    /* Mission Config Box */
    .config-card {
        background: #111827 !important;
        border: 1.5px solid #1f2937 !important;
        border-radius: 8px;
        padding: 14px 18px;
        margin-bottom: 14px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.2);
    }

    /* Form Controls & Selectboxes (High-Visibility Dark Styling) */
    .stSelectbox label {
        color: #94a3b8 !important;
        font-weight: 700 !important;
        font-size: 0.82rem !important;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    div[data-baseweb="select"] > div {
        background-color: #1e293b !important;
        border-color: #334155 !important;
        color: #f8fafc !important;
        border-radius: 6px !important;
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

    /* Buttons */
    .stButton > button {
        border-radius: 6px !important;
        font-weight: 700 !important;
        font-size: 0.85rem !important;
        padding: 8px 14px !important;
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
        font-size: 0.75rem;
        font-weight: 700;
        text-align: center;
        border: 1px solid #1f2937;
    }
    .phase-idle { background: #111827 !important; color: #64748b !important; }
    .phase-active { background: #0369a1 !important; color: #ffffff !important; border-color: #38bdf8 !important; box-shadow: 0 0 10px rgba(56, 189, 248, 0.3); }
    .phase-done { background: #14532d !important; color: #4ade80 !important; border-color: #22c55e !important; }
    .phase-alert { background: #7f1d1d !important; color: #fca5a5 !important; border-color: #ef4444 !important; animation: pulse 1.5s infinite; }

    /* KPI Summary Cards */
    .kpi-card {
        background-color: #111827 !important;
        border: 1px solid #1f2937 !important;
        border-radius: 8px;
        padding: 12px 14px;
        text-align: left;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
    }
    .kpi-title {
        color: #94a3b8 !important;
        font-size: 0.74rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .kpi-num {
        font-size: 1.55rem;
        font-weight: 800;
        margin: 2px 0;
    }
    .bad { color: #f87171 !important; }
    .good { color: #4ade80 !important; }
    .warn { color: #fbbf24 !important; }

    /* Cognitive Monologue Box */
    .thought-box {
        background-color: #064e3b !important;
        border: 1.5px solid #059669 !important;
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 12px;
        box-shadow: 0 0 15px rgba(5, 150, 105, 0.2);
    }
    .thought-box * {
        color: #a7f3d0 !important;
    }

    /* Live Stream Log Box */
    .log-box {
        background-color: #020617 !important;
        border: 1.5px solid #1e293b !important;
        border-radius: 8px;
        padding: 12px;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        font-size: 0.80rem;
        height: 380px;
        overflow-y: auto;
        color: #e2e8f0 !important;
        box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.5);
    }
    .log-line {
        padding: 3px 0;
        border-bottom: 1px solid #0f172a;
        line-height: 1.4;
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
        font-size: 0.9rem !important;
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
        font-family: ui-monospace, monospace !important;
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

# Map Configuration (Dark Matter)
if hasattr(go, "Scattermap"):
    MapTrace = go.Scattermap
    map_config = dict(map_style="carto-darkmatter")
else:
    MapTrace = getattr(go, "Scattermapbox", go.Scatter)
    map_config = dict(mapbox_style="carto-darkmatter")

# Load Databases
@st.cache_data
def load_all_databases():
    with open("data/anomalies.json", "r") as f:
        anomalies = json.load(f)
    with open("data/sla_contracts.json", "r") as f:
        slas = json.load(f)
    with open("data/routes.json", "r") as f:
        routes = json.load(f)
    with open("data/telemetry_stream.json", "r") as f:
        raw_telemetry = json.load(f)
    return anomalies, slas, routes, raw_telemetry

anomalies_pool, slas_db, routes_pool, base_telemetry = load_all_databases()

# Session State Initialization (Blank Slate by Default)
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
if "target_coords" not in st.session_state:
    st.session_state["target_coords"] = (0.0, 0.0)
if "service_countdown" not in st.session_state:
    st.session_state["service_countdown"] = 0
if "passed_points" not in st.session_state:
    st.session_state["passed_points"] = []

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
            <span style="color: #94a3b8; font-size: 0.88rem; font-weight: 500;">Autonomous Post-Sales SLA Risk Defense & Closed-Loop Regulatory Preservation</span>
        </div>
        <div style="text-align: right;">
            <span style="background: #1e293b; border: 1px solid #38bdf8; color: #38bdf8; padding: 6px 14px; border-radius: 20px; font-size: 0.82rem; font-weight: 700;">
                {active_corr_label}
            </span>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# =========================================================================
# 1. DYNAMIC MISSION CONFIGURATION PANEL (FULLY VISIBLE DROPDOWNS)
# =========================================================================
with st.container():
    st.markdown('<div class="config-card">', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns([1.5, 1.5, 1.2, 1.2])

    with c1:
        anomaly_opts = {"AUTO": "🎲 Auto (Randomize when fault occurs)"}
        for a in anomalies_pool:
            anomaly_opts[a["id"]] = f"{a['name']} ({a['category']})"
        
        sel_anom = st.selectbox(
            "Incident Anomaly Protocol:",
            options=list(anomaly_opts.keys()),
            format_func=lambda k: anomaly_opts[k],
            index=list(anomaly_opts.keys()).index(st.session_state["selected_anomaly_id"]),
            disabled=st.session_state["is_running"]
        )
        st.session_state["selected_anomaly_id"] = sel_anom

    with c2:
        curveball_opts = {
            "AUTO": "🎲 Auto (Evaluate during triage)",
            "NONE": "Nominal Protocol (No Curveball)",
            "POWER_OUTAGE": "⚡ Substation Power Outage at Primary Hub",
            "DETOUR_BLOCKED": "🚧 Highway Detour Gridlock / Closure",
            "SURGERY_MOVED_UP": "🏥 Surgery Time Accelerated (-45m SLA)"
        }
        sel_cb = st.selectbox(
            "Operational Curveball Modifier:",
            options=list(curveball_opts.keys()),
            format_func=lambda k: curveball_opts[k],
            index=list(curveball_opts.keys()).index(st.session_state["selected_curveball"]),
            disabled=st.session_state["is_running"]
        )
        st.session_state["selected_curveball"] = sel_cb

    with c3:
        st.write("")
        if not st.session_state["is_running"]:
            if st.button("▶️ Launch Mission", type="primary", use_container_width=True):
                chosen_route = random.choice(routes_pool)
                
                # We DO NOT pre-assign anomaly or SLA! They will be sampled at runtime.
                st.session_state["active_route"] = chosen_route
                st.session_state["active_anomaly"] = None  # chosen dynamically at fault
                st.session_state["chosen_hub"] = None      # chosen dynamically by AI
                st.session_state["active_curveball"] = "NONE"
                st.session_state["anomaly_trigger_sec"] = random.randint(16, 24)
                
                o_lat, o_lon = chosen_route["origin"]["lat"], chosen_route["origin"]["lon"]
                dest_lat, dest_lon = chosen_route["destination"]["lat"], chosen_route["destination"]["lon"]
                
                st.session_state["cur_lat"] = o_lat
                st.session_state["cur_lon"] = o_lon
                st.session_state["cur_temp"] = 3.5
                st.session_state["cur_meter"] = 0
                st.session_state["target_coords"] = (dest_lat, dest_lon)
                
                st.session_state["mission_clock"] = 0
                st.session_state["sim_state"] = "NOMINAL"
                st.session_state["mission_result"] = None
                st.session_state["passed_points"] = [{"sec": 0, "temp": 3.5, "lat": o_lat, "lon": o_lon}]
                st.session_state["has_run_started"] = True
                st.session_state["run_logs"] = [
                    f"[T+00s] 🟢 Fleet telematics online. Unit #409 departed {chosen_route['origin']['name']}.",
                    f"[T+00s] 📋 Active Corridor: {chosen_route['corridor_name']} | Consignee: {chosen_route['destination_facility']}",
                    f"[T+00s] 📦 Cargo Manifest: Autologous Life Sciences Batch | Telemetry: Nominal 3.5°C"
                ]
                st.session_state["is_running"] = True
                st.rerun()
        else:
            if st.button("⏹ Stop Run", type="secondary", use_container_width=True):
                st.session_state["is_running"] = False
                st.rerun()

    with c4:
        st.write("")
        if st.button("🔄 Reset Mission", type="secondary", use_container_width=True):
            st.session_state["has_run_started"] = False
            st.session_state["is_running"] = False
            st.session_state["mission_clock"] = 0
            st.session_state["sim_state"] = "STANDBY"
            st.session_state["active_route"] = None
            st.session_state["chosen_hub"] = None
            st.session_state["active_anomaly"] = None
            st.session_state["active_curveball"] = "NONE"
            st.session_state["mission_result"] = None
            st.session_state["passed_points"] = []
            st.session_state["run_logs"] = []
            st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

# Mission Clock Bar (Pure Open-Ended Stopwatch)
bar_c1, bar_c2 = st.columns([2, 1.2])
with bar_c1:
    if st.session_state["has_run_started"]:
        cur_sec = st.session_state["mission_clock"]
        st.markdown(f"""
        <div style="padding: 2px 0 6px 0;">
            <span style="font-size: 1.35rem; font-weight: 800; color: #f8fafc;">⏱️ Mission Clock: T+{cur_sec:02d}s</span>
            <span style="margin-left: 12px; font-size: 0.88rem; color: #38bdf8; font-family: ui-monospace, monospace; font-weight: 700;">
                {st.session_state['cur_meter']:,}m | ({st.session_state['cur_lat']:.5f}, {st.session_state['cur_lon']:.5f})
            </span>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("<div style='padding-top: 4px;'><span style='color: #64748b; font-weight: 600;'>Mission Standby — Select scenario and click Launch</span></div>", unsafe_allow_html=True)

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

    # If anomaly has occurred, pull dynamic SLA parameters
    if anom:
        sla_key = anom.get("sla_governed", "SLA-COLD-2TO8")
        governing_sla = slas_db.get(sla_key, slas_db["SLA-COLD-2TO8"])
        sla_exposure_usd = governing_sla.get("liability_amount_usd", 470000)
        ceiling_temp = governing_sla.get("excursion_ceiling", 8.0)
        band_spec = governing_sla.get("thermal_band", "+2.0°C to +8.0°C")
    else:
        sla_exposure_usd = 470000
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
            expo_sub = f"Exposed under {sla_key}"
        elif st.session_state["sim_state"] == "DELIVERED":
            if st.session_state["is_partial_breach"]:
                partial_pen = 5000
                saved_net = sla_exposure_usd - partial_pen
                expo_str = f"${saved_net:,} SAVED"
                expo_col = "warn"
                expo_sub = f"⚠️ ${partial_pen:,} delay fee deducted ({sla_key})"
            else:
                expo_str = f"${sla_exposure_usd:,} SAVED"
                expo_col = "good"
                expo_sub = f"Zero penalties incurred under {sla_key}"
        else:
            expo_str = "$0 AT RISK"
            expo_col = "good"
            expo_sub = "Nominal Transit Protocol"

        st.markdown(f"<div class='kpi-card'><div class='kpi-title'>Financial Protection</div><div class='kpi-num {expo_col}'>{expo_str}</div><div style='font-size: 0.75rem; color: #94a3b8;'>{expo_sub}</div></div>", unsafe_allow_html=True)

# =========================================================================
# LIVE COGNITIVE STREAM (AI INNER MONOLOGUE)
# =========================================================================
if st.session_state["has_run_started"] and st.session_state["mission_result"]:
    res = st.session_state["mission_result"]
    thoughts = list(res.get("cognitive_monologue", []))

    if thoughts:
        st.markdown(f"""
        <div class="thought-box">
            <div style="font-weight: 800; font-size: 0.88rem; margin-bottom: 4px; display: flex; justify-content: space-between;">
                <span>🧠 Gemini Live Cognitive Deliberation Feed (Engine: {', '.join(res['models_involved'])})</span>
                <span style="font-size: 0.78rem; font-weight: 600;">Verified Multi-Turn Autonomous Reasoning</span>
            </div>
            <div style="font-size: 0.85rem; line-height: 1.45;">
                {'<br>'.join([f"• {t}" for t in thoughts])}
            </div>
        </div>
        """, unsafe_allow_html=True)

# =========================================================================
# OPERATIONAL SECTION HEADERS AS TABS
# =========================================================================
tab_unified, tab_threat, tab_agent, tab_gxp = st.tabs([
    "🖥️ Unified Live Stream & Map",
    "🚨 Threat Physics & Curve",
    "🤖 Autonomous Agent Engine",
    "📑 GxP Audit & SLA Contracts"
])

# --- TAB 1: UNIFIED STREAM (STRICTLY 1 MAP ON SCREEN) ---
with tab_unified:
    map_col, log_col = st.columns([1.15, 1])

    with map_col:
        st.markdown("<h5 style='margin-bottom: 6px;'>🗺️ Closed-Loop Telematics Map (AI-Controlled Movement)</h5>", unsafe_allow_html=True)
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

            if passed_pts:
                fig_map.add_trace(MapTrace(
                    lat=[p["lat"] for p in passed_pts],
                    lon=[p["lon"] for p in passed_pts],
                    mode='lines',
                    line=dict(width=3, color="#ef4444" if cur_temp > 6.0 else "#22c55e"),
                    name="Breadcrumbs"
                ))

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
            log_html = '<div class="log-box"><div class="log-line">[T+00s] ⚪ System in standby. Select parameters and click "Launch Mission".</div></div>'
        else:
            log_html = '<div class="log-box">'
            for entry in reversed(st.session_state["run_logs"]):
                log_html += f'<div class="log-line">{entry}</div>'
            log_html += '</div>'
        st.markdown(log_html, unsafe_allow_html=True)

# --- TAB 2: THREAT PHYSICS (NO DUPLICATE MAP) ---
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
            - **Active Curveball:** `{st.session_state.get('active_curveball', 'NONE')}`
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

# --- TAB 3: AGENT REASONING ENGINE ---
with tab_agent:
    st.markdown("### 🤖 Autonomous Agent Reasoning & Function Calling Engine")
    if not st.session_state["has_run_started"]:
        st.info("Agent is standing by. Click 'Launch Mission' to awaken the Gemini autonomous decision loop.")
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

# --- TAB 4: GXP AUDIT ---
with tab_gxp:
    st.markdown("### 📑 Enterprise SLA Portfolio & GxP Regulatory Audit")
    if not st.session_state["has_run_started"]:
        st.info("System in standby. SLA and CAPA forms will compile upon mission execution.")
    else:
        g1, g2 = st.columns([1, 1.2])
        with g1:
            st.markdown("#### 📜 Governing SLA Schedule")
            if anom:
                sla_val = slas_db.get(anom.get("sla_governed", "SLA-COLD-2TO8"))
                st.markdown(f"""
                - **Name:** `{sla_val['name']}`
                - **Thermal Band:** `{sla_val['thermal_band']}`
                - **Excursion Ceiling:** `{sla_val['excursion_ceiling']}°C`
                - **Max Allowed Window:** `{sla_val['max_cumulative_excursion_mins']} mins`
                - **Contractual Liability:** `${sla_val.get('liability_amount_usd', 470000):,} USD`
                """)
            else:
                st.info("Awaiting anomaly ingestion to link governing Quality Agreement SLA schedule.")
        with g2:
            st.markdown("#### 📑 GxP Deviation Notice")
            if st.session_state["mission_result"]:
                res = st.session_state["mission_result"]
                gxp_report = next((s["result"] for s in res["trace"] if s["tool_called"] == "generate_gxp_deviation_report"), None)
                if gxp_report:
                    st.json(gxp_report)
                    st.download_button(label="📥 Download Certified GxP Notice", data=json.dumps(gxp_report, indent=2), file_name=f"GxP_Deviation_{res['incident_id']}.json", mime="application/json")

# =========================================================================
# CONTINUOUS PHYSICAL VECTOR ENGINE & RUNTIME INCIDENT INGESTION
# =========================================================================
if st.session_state.get("is_running", False) and st.session_state.get("has_run_started", False):
    time.sleep(SIM_STEP_DELAY)
    
    st.session_state["mission_clock"] += 1
    clock = st.session_state["mission_clock"]
    s_state = st.session_state["sim_state"]
    route_info = st.session_state["active_route"]
    f_sec = st.session_state["anomaly_trigger_sec"]
    
    cur_lat, cur_lon = st.session_state["cur_lat"], st.session_state["cur_lon"]
    t_lat, t_lon = st.session_state["target_coords"]
    
    # 1. NOMINAL STATE: Cruising along highway
    if s_state == "NOMINAL":
        d_lat = (t_lat - cur_lat) * 0.03
        d_lon = (t_lon - cur_lon) * 0.03
        st.session_state["cur_lat"] += d_lat
        st.session_state["cur_lon"] += d_lon
        st.session_state["cur_meter"] += 120
        st.session_state["cur_temp"] = round(3.5 + random.uniform(-0.03, 0.03), 2)
        
        st.session_state["run_logs"].append(
            f"[T+{clock:02d}s] 📍 GPS ({st.session_state['cur_lat']:.5f}, {st.session_state['cur_lon']:.5f}) | Temp: {st.session_state['cur_temp']}°C | Odometer: {st.session_state['cur_meter']:,}m | NOMINAL_CRUISE"
        )
        
        # Anomaly triggers at randomized second
        if clock >= f_sec:
            st.session_state["sim_state"] = "FAULT_DETECTED"
            st.session_state["cur_temp"] = 6.4
            
            # RUNTIME DYNAMIC SELECTION OF ANOMALY
            if st.session_state["selected_anomaly_id"] == "AUTO":
                active_anom = random.choice(anomalies_pool)
            else:
                active_anom = next(a for a in anomalies_pool if a["id"] == st.session_state["selected_anomaly_id"])
            st.session_state["active_anomaly"] = active_anom
            
            # RUNTIME DYNAMIC SELECTION OF CURVEBALL
            if st.session_state["selected_curveball"] == "AUTO":
                chosen_cb = random.choice(["NONE", "POWER_OUTAGE", "DETOUR_BLOCKED", "SURGERY_MOVED_UP"])
            else:
                chosen_cb = st.session_state["selected_curveball"]
            st.session_state["active_curveball"] = chosen_cb

            # DYNAMIC SLA LOOKUP
            sla_key = active_anom.get("sla_governed", "SLA-COLD-2TO8")
            matched_sla = slas_db.get(sla_key, slas_db["SLA-COLD-2TO8"])
            risk_usd = matched_sla.get("liability_amount_usd", 470000)
            
            st.session_state["run_logs"].append(
                f"[T+{clock:02d}s] 🚨 TELEMETRY ANOMALY INGESTED: {active_anom['name']} ({active_anom['fault_code']})!"
            )
            st.session_state["run_logs"].append(
                f"[T+{clock:02d}s] 📑 SLA Ingestion: Governed by {matched_sla['name']} | Exposure Cap: ${risk_usd:,} USD"
            )
            if chosen_cb != "NONE":
                st.session_state["run_logs"].append(f"[T+{clock:02d}s] ⚠️️ Active Corridor Modifier: {chosen_cb}")
            
            # Execute Gemini Agent
            active_payload = json.loads(json.dumps(base_telemetry))
            active_payload["governing_sla_id"] = sla_key
            active_payload["candidate_hubs"] = route_info.get("candidate_hubs", [])
            active_payload["curveball_condition"] = chosen_cb
            active_payload["incident_event"]["location"]["latitude"] = st.session_state["cur_lat"]
            active_payload["incident_event"]["location"]["longitude"] = st.session_state["cur_lon"]
            active_payload["incident_event"]["sensor_readings"]["compressor_status"] = active_anom["fault_code"]
            active_payload["incident_event"]["sensor_readings"]["cargo_temperature_celsius"] = 6.4
            
            res = run_cryoguard_mission(active_payload, is_replan=False)
            st.session_state["mission_result"] = res
            
            # Determine AI's chosen hub
            res_dock_call = next((s for s in res["trace"] if s["tool_called"] == "reserve_dock_replenishment"), None)
            cand_hubs = route_info.get("candidate_hubs", [])
            if res_dock_call:
                assigned_id = res_dock_call["arguments"].get("facility_id")
                chosen_hub = next((h for h in cand_hubs if h["facility_id"] == assigned_id), cand_hubs[0])
            else:
                chosen_hub = cand_hubs[0]
                
            st.session_state["chosen_hub"] = chosen_hub
            st.session_state["target_coords"] = (chosen_hub["lat"], chosen_hub["lon"])
            st.session_state["service_countdown"] = 14
            st.session_state["sim_state"] = "EN_ROUTE_HUB"
            
            for s in res["trace"]:
                st_str = format_tool_status(s.get("result"))
                st.session_state["run_logs"].append(
                    f"[T+{clock:02d}s] 🤖 Agent: Executed `{s['tool_called']}` ➔ {st_str}"
                )
            st.session_state["run_logs"].append(
                f"[T+{clock:02d}s] 🚀 Detour Vector Dispatched: Navigating to AI Target: {chosen_hub['name']}."
            )

    # 2. EN_ROUTE_HUB STATE: Detouring to AI's hub
    elif s_state == "EN_ROUTE_HUB":
        d_lat = (t_lat - cur_lat) * 0.12
        d_lon = (t_lon - cur_lon) * 0.12
        st.session_state["cur_lat"] += d_lat
        st.session_state["cur_lon"] += d_lon
        st.session_state["cur_meter"] += 90
        st.session_state["cur_temp"] = round(min(7.35, st.session_state["cur_temp"] + 0.06), 2)
        
        st.session_state["run_logs"].append(
            f"[T+{clock:02d}s] 🛣️ Detour Transit: Heading to {st.session_state['chosen_hub']['name']}. Temp: {st.session_state['cur_temp']}°C."
        )
        
        dist_to_hub = math.hypot(t_lat - st.session_state["cur_lat"], t_lon - st.session_state["cur_lon"])
        if dist_to_hub < 0.015:
            st.session_state["sim_state"] = "SERVICING"
            st.session_state["run_logs"].append(
                f"[T+{clock:02d}s] 🏢 Bay Arrival: Docked at {st.session_state['chosen_hub']['name']} Door #04. Servicing initiated."
            )

    # 3. SERVICING STATE: Docked
    elif s_state == "SERVICING":
        st.session_state["service_countdown"] -= 1
        st.session_state["cur_temp"] = round(max(3.6, st.session_state["cur_temp"] - 0.28), 2)
        
        st.session_state["run_logs"].append(
            f"[T+{clock:02d}s] ❄️ Servicing Active: Cryo charging in progress. Temp: {st.session_state['cur_temp']}°C. (Hold: {st.session_state['service_countdown']}s)"
        )
        
        if st.session_state["service_countdown"] <= 0:
            st.session_state["sim_state"] = "FINAL_LEG"
            dest_lat = route_info["destination"]["lat"]
            dest_lon = route_info["destination"]["lon"]
            st.session_state["target_coords"] = (dest_lat, dest_lon)
            st.session_state["run_logs"].append(
                f"[T+{clock:02d}s] ✅ Servicing Complete: Thermal envelope restored (3.6°C). Departing for {route_info['destination_facility']}."
            )

    # 4. FINAL_LEG STATE: High-speed transit to hospital
    elif s_state == "FINAL_LEG":
        d_lat = (t_lat - cur_lat) * 0.10
        d_lon = (t_lon - cur_lon) * 0.10
        st.session_state["cur_lat"] += d_lat
        st.session_state["cur_lon"] += d_lon
        st.session_state["cur_meter"] += 140
        st.session_state["cur_temp"] = round(3.6 + random.uniform(-0.02, 0.02), 2)
        
        st.session_state["run_logs"].append(
            f"[T+{clock:02d}s] 🛣️ Final Mile Approach: {st.session_state['cur_meter']:,}m traversed. Stabilized at {st.session_state['cur_temp']}°C."
        )
        
        dist_to_dest = math.hypot(t_lat - st.session_state["cur_lat"], t_lon - st.session_state["cur_lon"])
        if dist_to_dest < 0.02:
            st.session_state["sim_state"] = "DELIVERED"
            st.session_state["is_running"] = False
            
            anom = st.session_state["active_anomaly"]
            sla_key = anom.get("sla_governed", "SLA-COLD-2TO8")
            matched_sla = slas_db.get(sla_key, slas_db["SLA-COLD-2TO8"])
            saved_total = matched_sla.get("liability_amount_usd", 470000)
            
            st.session_state["run_logs"].append(
                f"[T+{clock:02d}s] 🏥 Consignee Delivery Complete: Successfully delivered at {route_info['destination_facility']}. Zero batch spoilage! Preserved ${saved_total:,} USD under {matched_sla['name']}."
            )

    # Record historical breadcrumb point
    st.session_state["passed_points"].append({
        "sec": clock,
        "temp": st.session_state["cur_temp"],
        "lat": st.session_state["cur_lat"],
        "lon": st.session_state["cur_lon"]
    })

    st.rerun()
