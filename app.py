import json
import random
import time
import streamlit as st
import plotly.graph_objects as go
from src.agent import run_cryoguard_mission

SIM_STEP_DELAY = 0.5

st.set_page_config(
    page_title="CryoGuard AI™ | Autonomous Operations & SLA Defense",
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

# --- LIGHT MODE ENTERPRISE THEME ---
st.markdown("""
<style>
    .stApp {
        background-color: #f8fafc !important;
        color: #0f172a !important;
    }
    p, span, label, div, h1, h2, h3, h4, h5, h6 {
        color: #0f172a;
    }
    .main-header {
        background: #ffffff !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 10px;
        padding: 14px 22px;
        margin-bottom: 12px;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
    }
    .stButton > button {
        border-radius: 6px !important;
        font-weight: 700 !important;
        font-size: 0.85rem !important;
        padding: 8px 14px !important;
    }
    .stButton > button[kind="primary"] {
        background-color: #0284c7 !important;
        color: #ffffff !important;
        border: 1px solid #0284c7 !important;
    }
    .stButton > button[kind="secondary"], 
    .stButton > button:not([kind="primary"]) {
        background-color: #ffffff !important;
        color: #0f172a !important;
        border: 1.5px solid #cbd5e1 !important;
    }
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
        border: 1px solid #cbd5e1;
    }
    .phase-idle { background: #f1f5f9 !important; color: #64748b !important; }
    .phase-active { background: #0284c7 !important; color: #ffffff !important; border-color: #0284c7 !important; }
    .phase-done { background: #16a34a !important; color: #ffffff !important; border-color: #16a34a !important; }
    .phase-alert { background: #dc2626 !important; color: #ffffff !important; border-color: #dc2626 !important; }

    .kpi-card {
        background-color: #ffffff !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 8px;
        padding: 12px 14px;
        text-align: left;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.04);
    }
    .kpi-title {
        color: #64748b !important;
        font-size: 0.74rem;
        font-weight: 700;
        text-transform: uppercase;
    }
    .kpi-num {
        font-size: 1.5rem;
        font-weight: 800;
        margin: 2px 0;
    }
    .bad { color: #dc2626 !important; }
    .good { color: #16a34a !important; }
    .warn { color: #d97706 !important; }

    /* Cognitive Monologue Box */
    .thought-box {
        background-color: #f0fdf4 !important;
        border: 1.5px solid #86efac !important;
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 12px;
        box-shadow: 0 1px 3px rgba(22, 163, 74, 0.08);
    }
    .log-box {
        background-color: #ffffff !important;
        border: 1.5px solid #cbd5e1 !important;
        border-radius: 8px;
        padding: 12px;
        font-family: ui-monospace, monospace;
        font-size: 0.80rem;
        height: 380px;
        overflow-y: auto;
        color: #0f172a !important;
    }
    .log-line {
        padding: 3px 0;
        border-bottom: 1px solid #f1f5f9;
        line-height: 1.4;
    }
    code, pre {
        background-color: #f8fafc !important;
        color: #0f172a !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 4px !important;
        padding: 2px 6px !important;
        font-family: ui-monospace, monospace !important;
    }
    [data-testid="stJson"], [data-testid="stCodeBlock"] {
        background-color: #ffffff !important;
        border: 1px solid #cbd5e1 !important;
        border-radius: 6px !important;
    }
</style>
""", unsafe_allow_html=True)

# Map Configuration
if hasattr(go, "Scattermap"):
    MapTrace = go.Scattermap
    map_config = dict(map_style="carto-positron")
else:
    MapTrace = getattr(go, "Scattermapbox", go.Scatter)
    map_config = dict(mapbox_style="carto-positron")

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

def build_corridor_trajectory(route_info, chosen_hub, total_sec):
    points = []
    o_lat, o_lon = route_info["origin"]["lat"], route_info["origin"]["lon"]
    d_lat, d_lon = chosen_hub["lat"], chosen_hub["lon"]
    dest_lat, dest_lon = route_info["destination"]["lat"], route_info["destination"]["lon"]

    fault_sec = 25
    dock_arrive_sec = 42
    dock_depart_sec = min(total_sec - 16, 60)

    for i in range(fault_sec):
        ratio = i / float(fault_sec)
        mid_lat = o_lat + (d_lat - o_lat) * 0.5
        mid_lon = o_lon + (d_lon - o_lon) * 0.5
        points.append({
            "sec": i,
            "meter": i * 100,
            "lat": round(o_lat + (mid_lat - o_lat) * ratio, 5),
            "lon": round(o_lon + (mid_lon - o_lon) * ratio, 5),
            "temp": round(3.5 + (i * 0.008) + random.uniform(-0.02, 0.02), 2),
            "status": "NOMINAL_CRUISE",
            "phase": 1
        })

    fault_lat = round(o_lat + (d_lat - o_lat) * 0.5, 5)
    fault_lon = round(o_lon + (d_lon - o_lon) * 0.5, 5)
    points.append({
        "sec": 25,
        "meter": 2500,
        "lat": fault_lat,
        "lon": fault_lon,
        "temp": 6.40,
        "status": "ANOMALY_TRIGGERED",
        "phase": 2
    })

    for i in range(26, dock_arrive_sec + 1):
        ratio = (i - 25) / float(dock_arrive_sec - 25)
        points.append({
            "sec": i,
            "meter": i * 100,
            "lat": round(fault_lat + (d_lat - fault_lat) * ratio, 5),
            "lon": round(fault_lon + (d_lon - fault_lon) * ratio, 5),
            "temp": round(6.4 + ((i - 25) * 0.045), 2),
            "status": f"DETOUR_TO_{chosen_hub['name'][:18]}",
            "phase": 3
        })

    for i in range(dock_arrive_sec + 1, dock_depart_sec + 1):
        step_cool = i - dock_arrive_sec
        points.append({
            "sec": i,
            "meter": dock_arrive_sec * 100,
            "lat": d_lat,
            "lon": d_lon,
            "temp": round(max(3.60, 7.15 - (step_cool * 0.22)), 2),
            "status": f"SERVICING_{chosen_hub['name'][:18]}",
            "phase": 4
        })

    remaining_steps = total_sec - dock_depart_sec
    for i in range(dock_depart_sec + 1, total_sec + 1):
        ratio = (i - dock_depart_sec) / float(remaining_steps)
        points.append({
            "sec": i,
            "meter": (dock_arrive_sec * 100) + int(ratio * 4000),
            "lat": round(d_lat + (dest_lat - d_lat) * ratio, 5),
            "lon": round(d_lon + (dest_lon - d_lon) * ratio, 5),
            "temp": round(3.60 + random.uniform(-0.02, 0.02), 2),
            "status": "TRANSIT_STABILIZED" if i < total_sec else "DELIVERED_AT_CONSIGNEE",
            "phase": 5
        })

    return points

# Session State Initialization
if "has_run_started" not in st.session_state:
    st.session_state["has_run_started"] = False
if "current_sec" not in st.session_state:
    st.session_state["current_sec"] = 0
if "is_running" not in st.session_state:
    st.session_state["is_running"] = False
if "active_route" not in st.session_state:
    st.session_state["active_route"] = None
if "chosen_hub" not in st.session_state:
    st.session_state["chosen_hub"] = None
if "active_anomaly" not in st.session_state:
    st.session_state["active_anomaly"] = None
if "corridor_points" not in st.session_state:
    st.session_state["corridor_points"] = []
if "mission_result" not in st.session_state:
    st.session_state["mission_result"] = None
if "curveball_active" not in st.session_state:
    st.session_state["curveball_active"] = False
if "is_partial_breach" not in st.session_state:
    st.session_state["is_partial_breach"] = False
if "run_logs" not in st.session_state:
    st.session_state["run_logs"] = []

# Safe Defaults
if st.session_state["has_run_started"] and st.session_state["active_anomaly"]:
    anom = st.session_state["active_anomaly"]
    governing_sla_id = anom.get("sla_governed", "SLA-COLD-2TO8")
    governing_sla = slas_db.get(governing_sla_id, slas_db["SLA-COLD-2TO8"])
    res_label = RESOLUTION_LABELS.get(anom.get("resolution_type"), "Autonomous Remediation")
    tot_sec = len(st.session_state["corridor_points"]) - 1
    cur_sec = st.session_state["current_sec"]
    cur_pt = st.session_state["corridor_points"][min(cur_sec, tot_sec)]
    has_anomaly = cur_sec >= 25
    is_stabilized = cur_sec >= (tot_sec - 16)
    r_color = "#dc2626" if (has_anomaly and not is_stabilized) else ("#16a34a" if is_stabilized else "#0284c7")
else:
    anom = {}
    governing_sla_id = "SLA-COLD-2TO8"
    governing_sla = slas_db["SLA-COLD-2TO8"]
    res_label = "Pending Triage & Assessment"
    tot_sec = 80
    cur_sec = 0
    cur_pt = {"temp": 0.0, "meter": 0, "lat": 0.0, "lon": 0.0}
    has_anomaly = False
    is_stabilized = False
    r_color = "#0284c7"

# --- TOP HEADER ---
active_corr_label = st.session_state["active_route"]["corridor_name"] if st.session_state["has_run_started"] else "SYSTEM STANDBY (AWAITING RUN)"

st.markdown(f"""
<div class="main-header">
    <div style="display: flex; justify-content: space-between; align-items: center;">
        <div>
            <h2 style="margin: 0; color: #0f172a; font-weight: 800; font-size: 1.55rem;">🧊 CryoGuard AI™ | Operations Commander</h2>
            <span style="color: #475569; font-size: 0.88rem; font-weight: 500;">Autonomous Post-Sales SLA Risk Defense & Closed-Loop Regulatory Preservation</span>
        </div>
        <div style="text-align: right;">
            <span style="background: #e0f2fe; border: 1px solid #bae6fd; color: #0369a1; padding: 6px 14px; border-radius: 20px; font-size: 0.82rem; font-weight: 700;">
                {active_corr_label}
            </span>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# Top Control Bar (Start / Stop / Reset / Curveball Toggle)
ctrl_c1, ctrl_c2, ctrl_c3, ctrl_c4 = st.columns([1.4, 1.1, 1.5, 1.4])

with ctrl_c1:
    if not st.session_state["is_running"]:
        if st.button("▶️ Start Auto-Run", type="primary", use_container_width=True):
            chosen_route = random.choice(routes_pool)
            chosen_anom = random.choice(anomalies_pool)
            tot_sec = chosen_anom.get("sim_duration_sec", 78)
            
            cand_hubs = chosen_route.get("candidate_hubs", [])
            chosen_hub = cand_hubs[0]
            
            st.session_state["active_route"] = chosen_route
            st.session_state["chosen_hub"] = chosen_hub
            st.session_state["active_anomaly"] = chosen_anom
            st.session_state["is_partial_breach"] = random.random() < chosen_anom.get("partial_breach_chance", 0.20)
            st.session_state["corridor_points"] = build_corridor_trajectory(chosen_route, chosen_hub, tot_sec)
            st.session_state["current_sec"] = 0
            st.session_state["mission_result"] = None
            st.session_state["has_run_started"] = True
            st.session_state["run_logs"] = [
                f"[00:00s] 🟢 Telematics initiated. Unit #409 departed {chosen_route['origin']['name']}.",
                f"[00:00s] 📋 Route: {chosen_route['corridor_name']} | Consignee: {chosen_route['destination_facility']}",
                f"[00:00s] ⏱️ Adaptive Timeline: {tot_sec}s configured for {chosen_anom.get('recovery_description', 'Recovery')}"
            ]
            st.session_state["is_running"] = True
            st.rerun()
    else:
        if st.button("⏹ Stop Run", type="secondary", use_container_width=True):
            st.session_state["is_running"] = False
            st.rerun()

with ctrl_c2:
    if st.button("🔄 Reset to Blank", type="secondary", use_container_width=True):
        st.session_state["has_run_started"] = False
        st.session_state["current_sec"] = 0
        st.session_state["is_running"] = False
        st.session_state["active_route"] = None
        st.session_state["chosen_hub"] = None
        st.session_state["active_anomaly"] = None
        st.session_state["corridor_points"] = []
        st.session_state["mission_result"] = None
        st.session_state["curveball_active"] = False
        st.session_state["is_partial_breach"] = False
        st.session_state["run_logs"] = []
        st.rerun()

with ctrl_c3:
    # THE JUDGE CURVEBALL TRIGGER
    if st.session_state["has_run_started"]:
        curveball_label = "⚡ Curveball: Substation Outage at Hub" if not st.session_state["curveball_active"] else "⚠️ Curveball Injected (Outage Active)"
        if st.button(curveball_label, type="secondary" if not st.session_state["curveball_active"] else "primary", use_container_width=True):
            st.session_state["curveball_active"] = not st.session_state["curveball_active"]
            st.session_state["run_logs"].append("[OPERATIONAL OVERRIDE] ⚠️ Judge Curveball Injected: Primary Hub Substation Outage!")
            st.rerun()
    else:
        st.caption("Curveball injector activates upon start.")

with ctrl_c4:
    if st.session_state["has_run_started"]:
        st.markdown(f"""
        <div style="text-align: right; padding-top: 4px;">
            <span style="font-size: 1.15rem; font-weight: 800; color: #0f172a;">⏱️ {cur_sec}s / {tot_sec}s</span><br>
            <span style="font-size: 0.8rem; color: #0284c7; font-family: ui-monospace, monospace; font-weight: 700;">
                {cur_pt['meter']:,}m | ({cur_pt['lat']:.5f}, {cur_pt['lon']:.5f})
            </span>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("<div style='text-align: right; padding-top: 8px;'><span style='color: #64748b; font-weight: 600;'>System Standby</span></div>", unsafe_allow_html=True)

# --- PHASE PROGRESS BAR ---
if not st.session_state["has_run_started"]:
    st.markdown("""
    <div class="phase-bar">
        <div class="phase-step phase-idle">1. Cruise (0–24s)</div>
        <div class="phase-step phase-idle">2. Anomaly Ingested (25s)</div>
        <div class="phase-step phase-idle">3. AI Autonomous Triage</div>
        <div class="phase-step phase-idle">4. Servicing & Cooldown</div>
        <div class="phase-step phase-idle">5. Delivery & Audit</div>
    </div>
    """, unsafe_allow_html=True)
else:
    p1_cls = "phase-done" if cur_sec >= 25 else ("phase-active" if cur_sec > 0 else "phase-idle")
    p2_cls = "phase-alert" if (cur_sec == 25 and not st.session_state["mission_result"]) else ("phase-done" if cur_sec > 25 else "phase-idle")
    p3_cls = "phase-active" if (26 <= cur_sec <= 42) else ("phase-done" if cur_sec > 42 else "phase-idle")
    p4_cls = "phase-active" if (43 <= cur_sec <= (tot_sec - 16)) else ("phase-done" if cur_sec > (tot_sec - 16) else "phase-idle")
    p5_cls = "phase-done" if cur_sec >= tot_sec else ("phase-active" if cur_sec > (tot_sec - 16) else "phase-idle")

    st.markdown(f"""
    <div class="phase-bar">
        <div class="phase-step {p1_cls}">1. Cruise (0–24s)</div>
        <div class="phase-step {p2_cls}">2. Anomaly (25s)</div>
        <div class="phase-step {p3_cls}">3. AI Triage (26–42s)</div>
        <div class="phase-step {p4_cls}">4. Servicing ({tot_sec-16}s)</div>
        <div class="phase-step {p5_cls}">5. Delivery ({tot_sec}s)</div>
    </div>
    """, unsafe_allow_html=True)

# --- KPI METRICS ---
k1, k2, k3, k4 = st.columns(4)

if not st.session_state["has_run_started"]:
    for k, title, val in [(k1, "Cargo Sensor Temp", "-- °C"), (k2, "Excursion Runway", "-- Mins"), (k3, "Delivery Window", "--:-- AM"), (k4, "Financial Exposure", "$0")]:
        with k:
            st.markdown(f"<div class='kpi-card'><div class='kpi-title'>{title}</div><div class='kpi-num' style='color: #94a3b8;'>{val}</div><div style='font-size: 0.75rem; color: #94a3b8;'>Standby</div></div>", unsafe_allow_html=True)
else:
    with k1:
        st.markdown(f"<div class='kpi-card'><div class='kpi-title'>Cargo Sensor Temp</div><div class='kpi-num {'bad' if (has_anomaly and not is_stabilized) else 'good'}'>{cur_pt['temp']} °C</div><div style='font-size: 0.75rem; color: #475569;'>Limit: {governing_sla['thermal_band']}</div></div>", unsafe_allow_html=True)
    with k2:
        runway_str = f"{max(8, 68 - (cur_sec - 25))} Mins" if (has_anomaly and not is_stabilized) else ("NOMINAL" if not has_anomaly else "PROTECTED")
        st.markdown(f"<div class='kpi-card'><div class='kpi-title'>Excursion Runway</div><div class='kpi-num {'bad' if (has_anomaly and not is_stabilized) else 'good'}'>{runway_str}</div><div style='font-size: 0.75rem; color: #475569;'>Max Budget: {governing_sla['max_cumulative_excursion_mins']} mins</div></div>", unsafe_allow_html=True)
    with k3:
        eta_str = "06:14 AM (Late)" if (st.session_state["is_partial_breach"] and cur_sec >= tot_sec) else ("06:45 AM (Late)" if (has_anomaly and not is_stabilized) else "05:54 AM (On Time)")
        eta_col = "warn" if "06:14" in eta_str else ("bad" if "06:45" in eta_str else "good")
        st.markdown(f"<div class='kpi-card'><div class='kpi-title'>Delivery Window</div><div class='kpi-num {eta_col}'>{eta_str}</div><div style='font-size: 0.75rem; color: #475569;'>SLA Hard-Stop: 06:00 AM CT</div></div>", unsafe_allow_html=True)
    with k4:
        expo_str = "$5,000 PENALTY" if (st.session_state["is_partial_breach"] and cur_sec >= tot_sec) else ("$470,000" if (has_anomaly and not is_stabilized) else ("$470,000 SAVED" if cur_sec >= tot_sec else "$0 AT RISK"))
        expo_col = "warn" if "$5,000" in expo_str else ("bad" if "$470,000" in expo_str and not is_stabilized else "good")
        st.markdown(f"<div class='kpi-card'><div class='kpi-title'>Financial Exposure</div><div class='kpi-num {expo_col}'>{expo_str}</div><div style='font-size: 0.75rem; color: #475569;'>Governed by {governing_sla_id}</div></div>", unsafe_allow_html=True)

# =========================================================================
# LIVE COGNITIVE STREAM (AI INNER MONOLOGUE)
# =========================================================================
if st.session_state["has_run_started"] and st.session_state["mission_result"]:
    res = st.session_state["mission_result"]
    thoughts = res.get("cognitive_monologue", [])
    if thoughts:
        st.markdown(f"""
        <div class="thought-box">
            <div style="font-weight: 800; color: #15803d; font-size: 0.88rem; margin-bottom: 4px; display: flex; justify-content: space-between;">
                <span>🧠 Gemini Live Cognitive Deliberation Feed (Engine: {', '.join(res['models_involved'])})</span>
                <span style="font-size: 0.78rem; font-weight: 600; color: #166534;">Verified Autonomous Reasoning Trace</span>
            </div>
            <div style="color: #14532d; font-size: 0.85rem; line-height: 1.45;">
                {'<br>'.join([f"• {t}" for t in thoughts])}
            </div>
        </div>
        """, unsafe_allow_html=True)

# =========================================================================
# OPERATIONAL SECTION HEADERS AS TABS
# =========================================================================
tab_unified, tab_threat, tab_agent, tab_gxp = st.tabs([
    "🖥️ Unified Live Stream & Map",
    "🚨 Threat Ingestion & Physics",
    "🤖 Autonomous Agent Engine",
    "📑 GxP Audit & SLA Contracts"
])

# --- TAB 1: UNIFIED STREAM ---
with tab_unified:
    map_col, log_col = st.columns([1.15, 1])

    with map_col:
        st.markdown("<h5 style='color: #0f172a; margin-bottom: 6px;'>🗺️ Closed-Loop Telematics Map (AI-Routed)</h5>", unsafe_allow_html=True)
        fig_map = go.Figure()

        if not st.session_state["has_run_started"]:
            fig_map.add_trace(MapTrace(
                lat=[39.8283], lon=[-98.5795], mode='markers+text',
                marker=dict(size=10, color='#94a3b8'), text=["System in Standby"]
            ))
            fig_map.update_layout(**map_config, map=dict(center=dict(lat=39.8, lon=-98.5), zoom=3.5), margin=dict(l=0, r=0, t=0, b=0), height=380, showlegend=False)
        else:
            route_info = st.session_state["active_route"]
            chosen_hub = st.session_state["chosen_hub"]
            c_points = st.session_state["corridor_points"]

            fig_map.add_trace(MapTrace(
                lat=[p["lat"] for p in c_points], lon=[p["lon"] for p in c_points],
                mode='lines', line=dict(width=3, color=r_color), name="AI Route"
            ))
            fig_map.add_trace(MapTrace(
                lat=[cur_pt["lat"]], lon=[cur_pt["lon"]], mode='markers+text',
                marker=dict(size=18, color=r_color), text=[f"Unit #409 ({cur_pt['temp']}°C)"],
                textposition="top right", name="Carrier"
            ))
            fig_map.add_trace(MapTrace(
                lat=[route_info["origin"]["lat"], chosen_hub["lat"], route_info["destination"]["lat"]],
                lon=[route_info["origin"]["lon"], chosen_hub["lon"], route_info["destination"]["lon"]],
                mode='markers+text', marker=dict(size=12, color=['#64748b', '#d97706', '#0284c7']),
                text=[route_info["origin"]["name"], f"⭐ AI Selected: {chosen_hub['name']}", route_info["destination"]["name"]],
                textposition="bottom right", name="Facilities"
            ))
            c_lat = (route_info["origin"]["lat"] + route_info["destination"]["lat"]) / 2.0
            c_lon = (route_info["origin"]["lon"] + route_info["destination"]["lon"]) / 2.0
            fig_map.update_layout(**map_config, uirevision="corridor_map", map=dict(center=dict(lat=c_lat, lon=c_lon), zoom=5.8), margin=dict(l=0, r=0, t=0, b=0), height=380, showlegend=False)

        st.plotly_chart(fig_map, use_container_width=True)

    with log_col:
        st.markdown("<h5 style='color: #0f172a; margin-bottom: 6px;'>📜 Real-Time Autonomous Operations Log Stream</h5>", unsafe_allow_html=True)
        if not st.session_state["has_run_started"]:
            log_html = '<div class="log-box"><div class="log-line">[--:--s] ⚪ System in standby. Click "▶️ Start Auto-Run" to initialize live telematics.</div></div>'
        else:
            log_html = '<div class="log-box">'
            for entry in reversed(st.session_state["run_logs"]):
                log_html += f'<div class="log-line">{entry}</div>'
            log_html += '</div>'
        st.markdown(log_html, unsafe_allow_html=True)

# --- TAB 2: THREAT PHYSICS ---
with tab_threat:
    st.markdown("<h3 style='color: #0f172a;'>🚨 Threat Ingestion & Excursion Physics</h3>", unsafe_allow_html=True)
    if not st.session_state["has_run_started"]:
        st.info("System in standby. Initiate Auto-Run to inspect anomaly physics.")
    else:
        t_c1, t_c2 = st.columns([1, 1.2])
        with t_c1:
            st.markdown(f"""
            **Active Threat Profile:**
            - **Incident:** `{anom.get('name')}`
            - **Fault Code:** `{anom.get('fault_code')}`
            - **Selected Strategy:** **{res_label}**
            - **AI Target Facility:** **{st.session_state['chosen_hub']['name']}**
            - **Thermal Drift:** `+{anom.get('temp_rate')}°C/hr`
            - **Governing SLA:** `{governing_sla['name']}`
            """)
        with t_c2:
            passed_pts = st.session_state["corridor_points"][:cur_sec + 1]
            fig_t = go.Figure()
            fig_t.add_trace(go.Scatter(x=[p["sec"] for p in passed_pts], y=[p["temp"] for p in passed_pts], mode="lines+markers", line=dict(color=r_color, width=3), name="Temp"))
            fig_t.add_hline(y=governing_sla["excursion_ceiling"], line_dash="dot", line_color="#d97706", annotation_text=f"Ceiling ({governing_sla['excursion_ceiling']}°C)")
            fig_t.update_layout(title="Thermal Trajectory vs Excursion Ceiling", xaxis_title="Seconds", yaxis_title="Temp (°C)", template="plotly_white", height=260, margin=dict(l=20, r=20, t=35, b=20))
            st.plotly_chart(fig_t, use_container_width=True)

# --- TAB 3: AGENT REASONING ENGINE ---
with tab_agent:
    st.markdown("<h3 style='color: #0f172a;'>🤖 Autonomous Agent Reasoning & Function Calling Engine</h3>", unsafe_allow_html=True)
    if not st.session_state["has_run_started"]:
        st.info("Agent is standing by. Click '▶ Start Auto-Run' to awaken the Gemini autonomous decision loop.")
    elif not st.session_state["mission_result"]:
        st.info("Autonomous agent in standby monitoring mode. Anomaly triggers at second 25.")
    else:
        res = st.session_state["mission_result"]
        st.success(f"✅ Mission Orchestration Active: {res['steps_executed']} Autonomous Operations Executed via Gemini ({', '.join(res['models_involved'])})")
        for step in res["trace"]:
            st.markdown(f"""
            <div style="background: #ffffff; border-left: 4px solid #0284c7; border: 1px solid #e2e8f0; padding: 10px 14px; margin-bottom: 8px; border-radius: 4px;">
                <span style="font-weight: 700; color: #0f172a;">Step {step['step']}: <code>{step['tool_called']}</code></span>
                <span style="color: #64748b; font-size: 0.8rem; margin-left: 10px;">Model: {step['model_engine']}</span>
            </div>
            """, unsafe_allow_html=True)
            st.json(step["result"])

# --- TAB 4: GXP AUDIT ---
with tab_gxp:
    st.markdown("<h3 style='color: #0f172a;'>📑 Enterprise SLA Portfolio & GxP Regulatory Audit</h3>", unsafe_allow_html=True)
    if not st.session_state["has_run_started"]:
        st.info("System in standby. SLA and CAPA forms will compile upon mission execution.")
    else:
        g1, g2 = st.columns([1, 1.2])
        with g1:
            st.markdown("<h4 style='color: #0f172a;'>📜 Governing SLA Schedule</h4>", unsafe_allow_html=True)
            st.markdown(f"""
            - **Name:** `{governing_sla['name']}`
            - **Thermal Band:** `{governing_sla['thermal_band']}`
            - **Excursion Ceiling:** `{governing_sla['excursion_ceiling']}°C`
            - **Max Allowed Window:** `{governing_sla['max_cumulative_excursion_mins']} mins`
            - **Financial Liability:** `{governing_sla['financial_liability']}`
            """)
        with g2:
            st.markdown("<h4 style='color: #0f172a;'>📑 GxP Deviation Notice</h4>", unsafe_allow_html=True)
            if st.session_state["mission_result"]:
                res = st.session_state["mission_result"]
                gxp_report = next((s["result"] for s in res["trace"] if s["tool_called"] == "generate_gxp_deviation_report"), None)
                if gxp_report:
                    st.json(gxp_report)
                    st.download_button(label="📥 Download Certified GxP Notice", data=json.dumps(gxp_report, indent=2), file_name=f"GxP_Deviation_{res['incident_id']}.json", mime="application/json")

# =========================================================================
# REAL-TIME UNINTERRUPTED TICKER LOOP
# =========================================================================
if st.session_state.get("is_running", False) and st.session_state.get("has_run_started", False):
    cur_sec = st.session_state["current_sec"]
    tot_sec = len(st.session_state["corridor_points"]) - 1
    anom = st.session_state["active_anomaly"]
    route_info = st.session_state["active_route"]
    governing_sla_id = anom.get("sla_governed", "SLA-COLD-2TO8")

    if cur_sec < tot_sec:
        time.sleep(SIM_STEP_DELAY)
        next_sec = cur_sec + 1
        st.session_state["current_sec"] = next_sec
        cur_pt = st.session_state["corridor_points"][next_sec]

        # At second 25: Awaken Gemini
        if next_sec == 25:
            st.session_state["run_logs"].append(
                f"[00:25s] 🚨 ALERT! Ingested: {anom['name']} ({anom['fault_code']}) | SLA Exposure: $470,000"
            )
            curveball_flag = "PRIMARY_FACILITY_OUTAGE" if st.session_state["curveball_active"] else None
            
            active_payload = json.loads(json.dumps(base_telemetry))
            active_payload["governing_sla_id"] = governing_sla_id
            active_payload["candidate_hubs"] = route_info.get("candidate_hubs", [])
            active_payload["curveball_condition"] = curveball_flag
            active_payload["incident_event"]["sensor_readings"]["compressor_status"] = anom["fault_code"]
            active_payload["incident_event"]["sensor_readings"]["cargo_temperature_celsius"] = 6.4
            
            res = run_cryoguard_mission(active_payload)
            st.session_state["mission_result"] = res

            # Update chosen hub based on AI's actual reservation tool argument!
            res_dock_call = next((s for s in res["trace"] if s["tool_called"] == "reserve_dock_replenishment"), None)
            if res_dock_call:
                assigned_id = res_dock_call["arguments"].get("facility_id")
                matched_hub = next((h for h in route_info.get("candidate_hubs", []) if h["facility_id"] == assigned_id), None)
                if matched_hub:
                    st.session_state["chosen_hub"] = matched_hub
                    # Recompute trajectory closed-loop to the AI's chosen hub
                    st.session_state["corridor_points"] = build_corridor_trajectory(route_info, matched_hub, tot_sec)

        # Continuous Agent Tool Logging across seconds 26 to 31
        elif 26 <= next_sec <= 31 and st.session_state["mission_result"]:
            trace = st.session_state["mission_result"]["trace"]
            idx = next_sec - 26
            if idx < len(trace):
                step = trace[idx]
                r_val = step["result"]
                status_str = r_val.get("status", r_val.get("deviation_id", "CONFIRMED")) if isinstance(r_val, dict) else (f"{len(r_val)} candidate hubs evaluated" if isinstance(r_val, list) else "OK")
                st.session_state["run_logs"].append(
                    f"[{next_sec:02d}:00s] 🤖 Agent Step {step['step']}: `{step['tool_called']}` ➔ {status_str}"
                )

        # Real-world narrative milestones
        elif next_sec == 35:
            st.session_state["run_logs"].append(
                f"[{next_sec:02d}:00s] 🛣️ Detour Transit: Rerouted to AI-selected hub: {st.session_state['chosen_hub']['name']}."
            )
        elif next_sec == 43:
            st.session_state["run_logs"].append(
                f"[{next_sec:02d}:00s] 🏢 Bay Arrival: Docked at {st.session_state['chosen_hub']['name']} Bay #04. Recovery active."
            )
        elif next_sec == 54:
            st.session_state["run_logs"].append(
                f"[{next_sec:02d}:00s] ❄️ Cooldown Verified: Thermal envelope restored at {cur_pt['temp']}°C."
            )
        elif next_sec == (tot_sec - 15):
            st.session_state["run_logs"].append(
                f"[{next_sec:02d}:00s] 🛣️ Highway Resumption: Departing hub. Proceeding to {route_info['destination_facility']}."
            )
        elif next_sec == tot_sec:
            if st.session_state["is_partial_breach"]:
                st.session_state["run_logs"].append(
                    f"[{next_sec:02d}:00s] ⚠️ Consignee Arrival: Delivered at {route_info['destination_facility']}. Controlled 14m delay ($5k fee incurred). $420k batch preserved!"
                )
            else:
                st.session_state["run_logs"].append(
                    f"[{next_sec:02d}:00s] 🏥 Consignee Arrival: Delivered at {route_info['destination_facility']} on time. Zero SLA penalties."
                )
        else:
            st.session_state["run_logs"].append(
                f"[{next_sec:02d}:00s] 📍 GPS ({cur_pt['lat']:.5f}, {cur_pt['lon']:.5f}) | Temp: {cur_pt['temp']}°C | Odometer: {cur_pt['meter']:,}m | {cur_pt['status']}"
            )

        st.rerun()
    else:
        st.session_state["is_running"] = False
        st.rerun()
