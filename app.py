import json
import random
import time
import streamlit as st
import plotly.graph_objects as go
from src.agent import run_cryoguard_mission

# Standard simulation speed (0.5s per 100m step)
SIM_STEP_DELAY = 0.5

st.set_page_config(
    page_title="CryoGuard AI™ | Autonomous Operations & SLA Defense",
    page_icon="🧊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- LIGHT MODE ENTERPRISE THEME (HIGH CONTRAST & BUTTON FIX) ---
st.markdown("""
<style>
    /* Global Container & Background */
    .stApp {
        background-color: #f8fafc !important;
        color: #0f172a !important;
    }
    
    /* Force dark text on all standard markdown and labels */
    p, span, label, div, h1, h2, h3, h4, h5, h6 {
        color: #0f172a;
    }
    
    /* Top Header Box */
    .main-header {
        background: #ffffff !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 10px;
        padding: 16px 24px;
        margin-bottom: 12px;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
    }

    /* Streamlit Button Styling (Fix for Invisible Reset Text) */
    .stButton > button {
        border-radius: 6px !important;
        font-weight: 700 !important;
        font-size: 0.86rem !important;
        padding: 8px 16px !important;
        transition: all 0.15s ease-in-out !important;
    }
    /* Primary Action Buttons */
    .stButton > button[kind="primary"] {
        background-color: #0284c7 !important;
        color: #ffffff !important;
        border: 1px solid #0284c7 !important;
    }
    .stButton > button[kind="primary"]:hover {
        background-color: #0369a1 !important;
        color: #ffffff !important;
    }
    /* Secondary & Reset Buttons (Forced High Contrast) */
    .stButton > button[kind="secondary"], 
    .stButton > button:not([kind="primary"]) {
        background-color: #ffffff !important;
        color: #0f172a !important;
        border: 1.5px solid #cbd5e1 !important;
        box-shadow: 0 1px 2px rgba(0,0,0,0.05) !important;
    }
    .stButton > button[kind="secondary"]:hover, 
    .stButton > button:not([kind="primary"]):hover {
        background-color: #f1f5f9 !important;
        color: #0284c7 !important;
        border-color: #0284c7 !important;
    }
    
    /* Phase Progress Tracker */
    .phase-bar {
        display: flex;
        gap: 6px;
        margin: 8px 0 14px 0;
    }
    .phase-step {
        flex: 1;
        padding: 8px 8px;
        border-radius: 6px;
        font-size: 0.76rem;
        font-weight: 700;
        text-align: center;
        border: 1px solid #cbd5e1;
        transition: all 0.2s ease;
    }
    .phase-idle { background: #f1f5f9 !important; color: #64748b !important; }
    .phase-active { background: #0284c7 !important; color: #ffffff !important; border-color: #0284c7 !important; }
    .phase-done { background: #16a34a !important; color: #ffffff !important; border-color: #16a34a !important; }
    .phase-alert { background: #dc2626 !important; color: #ffffff !important; border-color: #dc2626 !important; }

    /* KPI Summary Cards */
    .kpi-card {
        background-color: #ffffff !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 8px;
        padding: 12px 16px;
        text-align: left;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.04);
    }
    .kpi-title {
        color: #64748b !important;
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
    .bad { color: #dc2626 !important; }
    .good { color: #16a34a !important; }
    .warn { color: #d97706 !important; }

    /* Streamlit Tab Text High-Contrast Fix */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        border-bottom: 2px solid #e2e8f0;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #f1f5f9 !important;
        border-radius: 6px 6px 0 0 !important;
        padding: 8px 16px !important;
        border: 1px solid #e2e8f0 !important;
        border-bottom: none !important;
    }
    .stTabs [data-baseweb="tab"] p {
        color: #475569 !important;
        font-weight: 600 !important;
        font-size: 0.9rem !important;
    }
    .stTabs [aria-selected="true"] {
        background-color: #ffffff !important;
        border-top: 3px solid #0284c7 !important;
    }
    .stTabs [aria-selected="true"] p {
        color: #0284c7 !important;
        font-weight: 800 !important;
    }

    /* Expander Light Contrast Fix */
    [data-testid="stExpander"] {
        background-color: #ffffff !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 8px !important;
        margin-bottom: 8px !important;
    }
    [data-testid="stExpander"] details summary span {
        color: #0f172a !important;
        font-weight: 600 !important;
    }

    /* Live Stream Log Box */
    .log-box {
        background-color: #ffffff !important;
        border: 1.5px solid #cbd5e1 !important;
        border-radius: 8px;
        padding: 14px;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        font-size: 0.80rem;
        height: 380px;
        overflow-y: auto;
        color: #0f172a !important;
        box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.04);
    }
    .log-line {
        padding: 3px 0;
        border-bottom: 1px solid #f1f5f9;
        line-height: 1.4;
        color: #1e293b !important;
    }
</style>
""", unsafe_allow_html=True)

# Adaptive Light-Mode Plotly Map Config
if hasattr(go, "Scattermap"):
    MapTrace = go.Scattermap
    map_config = dict(
        map_style="carto-positron",
        map=dict(center=dict(lat=43.25, lon=-90.5), zoom=6.2)
    )
else:
    MapTrace = getattr(go, "Scattermapbox", go.Scatter)
    map_config = dict(
        mapbox_style="carto-positron",
        mapbox=dict(center=dict(lat=43.25, lon=-90.5), zoom=6.2)
    )

# Load Static Data
@st.cache_data
def load_base_data():
    with open("data/anomalies.json", "r") as f:
        anomalies = json.load(f)
    with open("data/facilities.json", "r") as f:
        facilities = json.load(f)
    with open("data/sla_contracts.json", "r") as f:
        slas = json.load(f)
    with open("data/telemetry_stream.json", "r") as f:
        raw_telemetry = json.load(f)
    return anomalies, facilities, slas, raw_telemetry

anomalies_pool, facilities_db, slas_db, base_telemetry = load_base_data()

# 80-Second Realistic Corridor Trajectory
def generate_80s_corridor():
    points = []
    start_lat, start_lon = 42.85000, -89.15000
    madison_lat, madison_lon = 43.07310, -89.40120
    rochester_lat, rochester_lon = 44.01210, -92.48020

    # Phase 1: 0 to 24s (Nominal Cruise)
    for i in range(25):
        ratio = i / 25.0
        lat = round(start_lat + (42.98100 - start_lat) * ratio, 5)
        lon = round(start_lon + (-89.30210 - start_lon) * ratio, 5)
        points.append({
            "sec": i,
            "meter": i * 100,
            "lat": lat,
            "lon": lon,
            "temp": round(3.5 + (i * 0.008) + random.uniform(-0.02, 0.02), 2),
            "status": "NOMINAL_CRUISE",
            "phase": 1
        })

    # Phase 2: 25s (Fault Ingested)
    points.append({
        "sec": 25,
        "meter": 2500,
        "lat": 42.98100,
        "lon": -89.30210,
        "temp": 6.40,
        "status": "ANOMALY_TRIGGERED",
        "phase": 2
    })

    # Phase 3: 26 to 45s (Physical Detour / En Route to Dock)
    for i in range(26, 46):
        ratio = (i - 25) / 20.0
        lat = round(42.98100 + (madison_lat - 42.98100) * ratio, 5)
        lon = round(-89.30210 + (madison_lon - -89.30210) * ratio, 5)
        temp_climb = 6.4 + ((i - 25) * 0.045)  # Reaches ~7.25°C at sec 45
        points.append({
            "sec": i,
            "meter": i * 100,
            "lat": lat,
            "lon": lon,
            "temp": round(temp_climb, 2),
            "status": "DETOUR_EN_ROUTE_TO_DOCK",
            "phase": 3
        })

    # Phase 4: 46 to 60s (Stationary at Dock Bay #04: Servicing & Cool-Down)
    for i in range(46, 61):
        dock_step = i - 45
        temp_cool = max(3.60, 7.25 - (dock_step * 0.25))
        points.append({
            "sec": i,
            "meter": 4500,  # Stationary at dock
            "lat": madison_lat,
            "lon": madison_lon,
            "temp": round(temp_cool, 2),
            "status": "DOCK_BAY_SERVICING",
            "phase": 4
        })

    # Phase 5: 61 to 80s (Resumed Transit to Mayo Clinic Rochester)
    for i in range(61, 81):
        ratio = (i - 60) / 20.0
        lat = round(madison_lat + (rochester_lat - madison_lat) * ratio, 5)
        lon = round(madison_lon + (rochester_lon - madison_lon) * ratio, 5)
        meter_val = 4500 + ((i - 60) * 175)
        points.append({
            "sec": i,
            "meter": meter_val,
            "lat": lat,
            "lon": lon,
            "temp": round(3.60 + random.uniform(-0.02, 0.02), 2),
            "status": "HIGHWAY_TRANSIT_STABILIZED" if i < 80 else "DELIVERED_ON_TIME_MAYO",
            "phase": 5
        })

    return points

corridor_points = generate_80s_corridor()

# Initialize Session State
if "current_sec" not in st.session_state:
    st.session_state["current_sec"] = 0
if "is_running" not in st.session_state:
    st.session_state["is_running"] = False
if "active_anomaly" not in st.session_state:
    st.session_state["active_anomaly"] = anomalies_pool[0]
if "mission_result" not in st.session_state:
    st.session_state["mission_result"] = None
if "run_logs" not in st.session_state:
    st.session_state["run_logs"] = ["[00:00s] 🟢 Fleet telematics online. Unit #409 departed Chicago DC (0 meters)."]

cur_sec = st.session_state["current_sec"]
cur_pt = corridor_points[min(cur_sec, len(corridor_points) - 1)]
has_anomaly = cur_sec >= 25
is_resolved = st.session_state["mission_result"] is not None
is_stabilized = cur_sec >= 58

# Global styling and route color definitions
route_color = "#dc2626" if (has_anomaly and not is_stabilized) else ("#16a34a" if is_stabilized else "#0284c7")

anom = st.session_state["active_anomaly"]
governing_sla_id = anom.get("sla_governed", "SLA-COLD-2TO8")
governing_sla = slas_db.get(governing_sla_id, slas_db["SLA-COLD-2TO8"])

RESOLUTION_LABELS = {
    "COLD_DOCK_RECHARGE": "Emergency Cold-Dock Diversion & Dry-Ice Recharge",
    "HOTSHOT_RELAY": "High-Priority Medical Hot-Shot Courier Relay (Gridlock Bypass)",
    "MOBILE_TECH_INTERCEPT": "24/7 Mobile Refrigeration Specialist Highway Intercept",
    "STERILE_RESEAL_INSPECT": "GxP Tamper-Evident Re-Seal & Barrier Inspection",
    "CRYOGENIC_LN2_RECHARGE": "Liquid Nitrogen High-Pressure Vapor Top-Off"
}
res_label = RESOLUTION_LABELS.get(anom.get("resolution_type"), "Autonomous Remediation")

# =========================================================================
# 1. TOP HEADER & PROMINENT CONTROLS
# =========================================================================
st.markdown("""
<div class="main-header">
    <div style="display: flex; justify-content: space-between; align-items: center;">
        <div>
            <h2 style="margin: 0; color: #0f172a; font-weight: 800; font-size: 1.55rem;">🧊 CryoGuard AI™ | Operations Commander</h2>
            <span style="color: #475569; font-size: 0.88rem; font-weight: 500;">Autonomous Post-Sales SLA Risk Defense & Regulatory Life Sciences Preservation</span>
        </div>
        <div style="text-align: right;">
            <span style="background: #e0f2fe; border: 1px solid #bae6fd; color: #0369a1; padding: 6px 14px; border-radius: 20px; font-size: 0.82rem; font-weight: 700;">
                CORRIDOR: CHICAGO ➔ ROCHESTER
            </span>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# Top Control Bar (Start / Stop / Reset)
ctrl_c1, ctrl_c2, ctrl_c3 = st.columns([1.5, 1.2, 1.8])

with ctrl_c1:
    if not st.session_state["is_running"]:
        if st.button("▶️ Start Auto-Run (80s)", type="primary", use_container_width=True):
            st.session_state["active_anomaly"] = random.choice(anomalies_pool)
            st.session_state["current_sec"] = 0
            st.session_state["mission_result"] = None
            st.session_state["run_logs"] = [f"[00:00s] 🟢 Fleet telemetry initialized. Unit #409 departed Chicago DC."]
            st.session_state["is_running"] = True
            st.rerun()
    else:
        if st.button("⏹ Stop Run", type="secondary", use_container_width=True):
            st.session_state["is_running"] = False
            st.rerun()

with ctrl_c2:
    if st.button("🔄 Reset System (0s)", type="secondary", use_container_width=True):
        st.session_state["current_sec"] = 0
        st.session_state["is_running"] = False
        st.session_state["mission_result"] = None
        st.session_state["run_logs"] = ["[00:00s] 🟢 System reset. Unit #409 at Origin (0 meters)."]
        st.rerun()

with ctrl_c3:
    st.markdown(f"""
    <div style="text-align: right; padding-top: 4px;">
        <span style="font-size: 1.2rem; font-weight: 800; color: #0f172a;">⏱️ {cur_sec}s / 80s</span>
        <span style="margin-left: 10px; font-size: 0.85rem; color: #0284c7; font-family: ui-monospace, monospace; font-weight: 700;">
            {cur_pt['meter']:,}m | ({cur_pt['lat']:.5f}, {cur_pt['lon']:.5f})
        </span>
    </div>
    """, unsafe_allow_html=True)

# =========================================================================
# 2. RUN PROGRESS TRACKER (5 PHYSICAL PHASES)
# =========================================================================
p1_cls = "phase-done" if cur_sec >= 25 else ("phase-active" if cur_sec > 0 else "phase-idle")
p2_cls = "phase-alert" if (cur_sec == 25 and not is_resolved) else ("phase-done" if cur_sec > 25 else "phase-idle")
p3_cls = "phase-active" if (26 <= cur_sec <= 45) else ("phase-done" if cur_sec > 45 else "phase-idle")
p4_cls = "phase-active" if (46 <= cur_sec <= 60) else ("phase-done" if cur_sec > 60 else "phase-idle")
p5_cls = "phase-done" if cur_sec >= 79 else ("phase-active" if cur_sec > 60 else "phase-idle")

st.markdown(f"""
<div class="phase-bar">
    <div class="phase-step {p1_cls}">1. Cruise (0–24s)</div>
    <div class="phase-step {p2_cls}">2. Anomaly (25s)</div>
    <div class="phase-step {p3_cls}">3. En Route to Dock (26–45s)</div>
    <div class="phase-step {p4_cls}">4. Servicing (46–60s)</div>
    <div class="phase-step {p5_cls}">5. On-Time Delivery (61–80s)</div>
</div>
""", unsafe_allow_html=True)

# Metric KPI Row
k1, k2, k3, k4 = st.columns(4)

with k1:
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-title">Cargo Sensor Temp</div>
        <div class="kpi-num {'bad' if (has_anomaly and not is_stabilized) else 'good'}">{cur_pt['temp']} °C</div>
        <div style="font-size: 0.75rem; color: #475569; font-weight: 500;">Limit: {governing_sla['thermal_band']}</div>
    </div>
    """, unsafe_allow_html=True)

with k2:
    if has_anomaly and not is_stabilized:
        runway_str = f"{max(8, 68 - (cur_sec - 25))} Mins"
    elif not has_anomaly:
        runway_str = "NOMINAL"
    else:
        runway_str = "PROTECTED"

    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-title">Excursion Runway</div>
        <div class="kpi-num {'bad' if (has_anomaly and not is_stabilized) else 'good'}">{runway_str}</div>
        <div style="font-size: 0.75rem; color: #475569; font-weight: 500;">Max Allowed: {governing_sla['max_cumulative_excursion_mins']} mins</div>
    </div>
    """, unsafe_allow_html=True)

with k3:
    eta_str = "06:45 AM (Late)" if (has_anomaly and not is_resolved) else ("05:54 AM (On Time)" if is_resolved else "05:30 AM (Nominal)")
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-title">Delivery Window</div>
        <div class="kpi-num {'bad' if (has_anomaly and not is_resolved) else 'good'}">{eta_str}</div>
        <div style="font-size: 0.75rem; color: #475569; font-weight: 500;">SLA Hard-Stop: 06:00 AM CT</div>
    </div>
    """, unsafe_allow_html=True)

with k4:
    expo_str = "$470,000" if (has_anomaly and not is_resolved) else ("$0 AT RISK" if not has_anomaly else "$470,000 SAVED")
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-title">Financial Exposure</div>
        <div class="kpi-num {'bad' if (has_anomaly and not is_resolved) else 'good'}">{expo_str}</div>
        <div style="font-size: 0.75rem; color: #475569; font-weight: 500;">Governed by {governing_sla_id}</div>
    </div>
    """, unsafe_allow_html=True)

# Active Resolution Strategy Pill Banner
if has_anomaly:
    st.markdown(f"""
    <div style="background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 6px; padding: 8px 14px; margin: 10px 0 14px 0; display: flex; align-items: center; justify-content: space-between;">
        <span style="font-size: 0.85rem; color: #1e40af; font-weight: 600;">Incident: {anom['name']} (<code>{anom['fault_code']}</code>)</span>
        <span style="font-size: 0.84rem; font-weight: 700; color: #1d4ed8; background: #dbeafe; padding: 4px 10px; border-radius: 4px;">
            Target Strategy: {res_label}
        </span>
    </div>
    """, unsafe_allow_html=True)

# =========================================================================
# 3. OPERATIONAL SECTION HEADERS AS TABS IN A ROW
# =========================================================================
tab_unified, tab_threat, tab_agent, tab_gxp = st.tabs([
    "🖥️ Unified Live Stream & Map",
    "🚨 Threat Ingestion & Physics",
    "🤖 Autonomous Agent Engine",
    "📑 GxP Audit & SLA Contracts"
])

# =========================================================================
# TAB 1: UNIFIED DASHBOARD (SMOOTH MAP + SCROLLING LOG STREAM)
# =========================================================================
with tab_unified:
    map_col, log_col = st.columns([1.15, 1])

    with map_col:
        st.markdown("<h5 style='color: #0f172a; margin-bottom: 6px;'>🗺️ High-Precision Corridor Map (100m Live Tracking)</h5>", unsafe_allow_html=True)

        fig_map = go.Figure()

        # Static Route Track
        fig_map.add_trace(MapTrace(
            lat=[p["lat"] for p in corridor_points],
            lon=[p["lon"] for p in corridor_points],
            mode='lines',
            line=dict(width=3, color=route_color),
            name="Route Track"
        ))

        # Dynamic Vehicle Pin (Smooth with uirevision)
        fig_map.add_trace(MapTrace(
            lat=[cur_pt["lat"]],
            lon=[cur_pt["lon"]],
            mode='markers+text',
            marker=dict(size=18, color=route_color),
            text=[f"Unit #409: {cur_pt['temp']}°C | {cur_pt['meter']}m"],
            textposition="top right",
            name="Vehicle"
        ))

        # Strategic Facilities
        fig_map.add_trace(MapTrace(
            lat=[43.0731, 44.0121],
            lon=[-89.4012, -92.4802],
            mode='markers+text',
            marker=dict(size=12, color=['#d97706', '#0284c7']),
            text=["Madison CryoDock", "Mayo Clinic Rochester"],
            textposition="bottom right",
            name="Facilities"
        ))

        fig_map.update_layout(
            **map_config,
            uirevision="corridor_map",
            margin=dict(l=0, r=0, t=0, b=0),
            height=380,
            showlegend=False
        )
        st.plotly_chart(fig_map, use_container_width=True)

    with log_col:
        st.markdown("<h5 style='color: #0f172a; margin-bottom: 6px;'>📜 Real-Time Autonomous Operations Log Stream</h5>", unsafe_allow_html=True)
        log_html = '<div class="log-box">'
        for entry in reversed(st.session_state["run_logs"]):
            log_html += f'<div class="log-line">{entry}</div>'
        log_html += '</div>'
        st.markdown(log_html, unsafe_allow_html=True)

# =========================================================================
# TAB 2: ANOMALY THREAT PHYSICS
# =========================================================================
with tab_threat:
    st.markdown("<h3 style='color: #0f172a;'>🚨 Threat Ingestion & Excursion Physics</h3>", unsafe_allow_html=True)
    t_c1, t_c2 = st.columns([1, 1.2])

    with t_c1:
        st.markdown(f"""
        **Active Anomaly Profile:**
        - **Incident Title:** `{anom['name']}`
        - **Category:** `{anom['category']}`
        - **Fault Code:** `{anom['fault_code']}`
        - **Selected Resolution Pathway:** **{res_label}**
        - **Thermal Drift Rate:** `+{anom['temp_rate']}°C per hour`
        - **Power Draw:** `{anom['power_w']} Watts`
        - **Governing SLA Schedule:** `{governing_sla['name']}`
        - **Risk Exposure:** `{anom['risk_exposure']}`
        """)
        st.info(f"**Operational Context:** {anom['description']}")

    with t_c2:
        passed_pts = corridor_points[:cur_sec + 1]
        fig_t = go.Figure()
        fig_t.add_trace(go.Scatter(
            x=[p["sec"] for p in passed_pts],
            y=[p["temp"] for p in passed_pts],
            mode="lines+markers",
            line=dict(color=route_color, width=3),
            name="Sensor Temp"
        ))
        fig_t.add_hline(
            y=governing_sla["excursion_ceiling"],
            line_dash="dot",
            line_color="#d97706",
            annotation_text=f"SLA Ceiling ({governing_sla['excursion_ceiling']}°C)",
            annotation_position="bottom right"
        )
        fig_t.update_layout(
            title="Real-Time Thermal Trajectory (Seconds 0 to 80)",
            xaxis_title="Simulation Seconds",
            yaxis_title="Temp (°C)",
            template="plotly_white",
            height=260,
            margin=dict(l=20, r=20, t=35, b=20)
        )
        st.plotly_chart(fig_t, use_container_width=True)

# =========================================================================
# TAB 3: AUTONOMOUS AGENT ENGINE
# =========================================================================
with tab_agent:
    st.markdown("<h3 style='color: #0f172a;'>🤖 Autonomous Agent Reasoning & Function Calling Engine</h3>", unsafe_allow_html=True)
    if not is_resolved:
        st.info(f"Agent in standby monitoring mode. When second 25 triggers `{anom['fault_code']}`, the Gemini model dynamically selects and executes the **{res_label}** playbook.")
    else:
        res = st.session_state["mission_result"]
        st.success(f"✅ Mission Mitigated: {res['steps_executed']} Autonomous Operations Executed via Gemini Engine ({', '.join(res['models_involved'])})")
        for step in res["trace"]:
            st.markdown(f"""
            <div style="background: #ffffff; border-left: 4px solid #0284c7; border: 1px solid #e2e8f0; padding: 10px 14px; margin-bottom: 8px; border-radius: 4px;">
                <span style="font-weight: 700; color: #0f172a;">Step {step['step']}: <code>{step['tool_called']}</code></span>
                <span style="color: #64748b; font-size: 0.8rem; margin-left: 10px;">Model: {step['model_engine']}</span>
            </div>
            """, unsafe_allow_html=True)
            st.json(step["result"])

# =========================================================================
# TAB 4: GXP AUDIT & ALL SLA CONTRACTS
# =========================================================================
with tab_gxp:
    st.markdown("<h3 style='color: #0f172a;'>📑 Enterprise SLA Portfolio & GxP Regulatory Audit</h3>", unsafe_allow_html=True)

    g1, g2 = st.columns([1, 1.2])
    with g1:
        st.markdown("<h4 style='color: #0f172a;'>📜 Available SLA Contract Schedules</h4>", unsafe_allow_html=True)
        for s_id, s_val in slas_db.items():
            with st.expander(f"{s_val['name']} ({s_id})", expanded=(s_id == governing_sla_id)):
                st.markdown(f"""
                - **Band:** `{s_val['thermal_band']}`
                - **Excursion Ceiling:** `{s_val['excursion_ceiling']}°C`
                - **Max Allowed Window:** `{s_val['max_cumulative_excursion_mins']} minutes`
                - **Liability:** `{s_val['financial_liability']}`
                - **Standard:** `{s_val['governing_standard']}`
                """)

    with g2:
        st.markdown("<h4 style='color: #0f172a;'>📑 GxP Deviation Notice & CAPA Report</h4>", unsafe_allow_html=True)
        if is_resolved:
            gxp_report = next((s["result"] for s in res["trace"] if s["tool_called"] == "generate_gxp_deviation_report"), None)
            if gxp_report:
                st.json(gxp_report)
                st.download_button(
                    label="📥 Download Certified GxP Deviation Notice (JSON)",
                    data=json.dumps(gxp_report, indent=2),
                    file_name=f"GxP_Deviation_{res['incident_id']}.json",
                    mime="application/json",
                    use_container_width=True
                )
        else:
            st.info("Regulatory CAPA report compiles automatically when incident is resolved.")

# =========================================================================
# REAL-TIME 80-SECOND SIMULATION TICKER & EVERY-SECOND LOG STREAM
# =========================================================================
if st.session_state.get("is_running", False):
    if cur_sec < 80:
        # At second 25: Trigger anomaly and run Gemini agent
        if cur_sec == 24 and not st.session_state["mission_result"]:
            st.session_state["current_sec"] = 25
            st.session_state["run_logs"].append(
                f"[00:25s] 🚨 ALERT! Ingested: {anom['name']} ({anom['fault_code']}) | SLA At Risk: $470k"
            )
            time.sleep(SIM_STEP_DELAY)
            with st.spinner(f"🚨 Resolving {anom['name']} via Gemini Autonomous Commander..."):
                active_payload = json.loads(json.dumps(base_telemetry))
                active_payload["governing_sla_id"] = governing_sla_id
                active_payload["incident_event"]["sensor_readings"]["compressor_status"] = anom["fault_code"]
                active_payload["incident_event"]["sensor_readings"]["cargo_temperature_celsius"] = 6.4
                
                res = run_cryoguard_mission(active_payload)
                st.session_state["mission_result"] = res
                
                # Safely inspect tool result whether list or dict
                for step in res["trace"]:
                    r_val = step["result"]
                    if isinstance(r_val, dict):
                        status_str = r_val.get("status", r_val.get("deviation_id", "CONFIRMED"))
                    elif isinstance(r_val, list):
                        status_str = f"{len(r_val)} facilities found"
                    else:
                        status_str = "OK"

                    st.session_state["run_logs"].append(
                        f"[00:26s] 🤖 Agent: Executed `{step['tool_called']}` | Result: {status_str}"
                    )
                st.session_state["run_logs"].append(f"[00:27s] 🚀 Resolution Action Dispatched: {res_label}")
                st.session_state["run_logs"].append(f"[00:28s] 🚛 Carrier: Exiting I-90 at MM 142. Detour en route to facility...")
            st.rerun()
        else:
            time.sleep(SIM_STEP_DELAY)
            next_sec = cur_sec + 1
            st.session_state["current_sec"] = next_sec
            
            # Specific narrative milestones
            if next_sec == 35:
                st.session_state["run_logs"].append(f"[00:35s] 🛣️ Detour Transit: Carrier 3.2 miles from facility. Cargo temp ({cur_pt['temp']}°C).")
            elif next_sec == 46:
                st.session_state["run_logs"].append(f"[00:46s] 🏢 Facility Arrival: Unit #409 backed into Bay Door #04. Servicing initiated.")
            elif next_sec == 53:
                st.session_state["run_logs"].append(f"[00:53s] ❄️ Active Cooldown: Cryo replenishment active. Temperature dropping ({cur_pt['temp']}°C).")
            elif next_sec == 60:
                st.session_state["run_logs"].append(f"[00:60s] ✅ Servicing Complete: Thermal envelope restored (3.6°C). Departing bay.")
            elif next_sec == 65:
                st.session_state["run_logs"].append(f"[00:65s] 🛣️ Highway Resumption: Unit #409 merged onto corridor. Full speed to Mayo Clinic.")
            elif next_sec == 80:
                st.session_state["run_logs"].append(f"[00:80s] 🏥 Final Destination: Delivered at Mayo Clinic (05:54 AM CT). Zero SLA penalties incurred.")
            else:
                # Log telemetry EVERY SECOND
                phase_label = cur_pt["status"]
                st.session_state["run_logs"].append(
                    f"[{next_sec:02d}:00s] 📍 GPS ({cur_pt['lat']:.5f}, {cur_pt['lon']:.5f}) | Temp: {cur_pt['temp']}°C | Odometer: {cur_pt['meter']:,}m | {phase_label}"
                )

            st.rerun()
    else:
        st.session_state["is_running"] = False
        st.rerun()
