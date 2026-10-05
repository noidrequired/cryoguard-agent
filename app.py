import json
import random
import time
import streamlit as st
import plotly.graph_objects as go
from src.agent import run_cryoguard_mission

st.set_page_config(
    page_title="CryoGuard AI™ | Autonomous Operations & SLA Defense",
    page_icon="🧊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom Enterprise SaaS CSS
st.markdown("""
<style>
    .top-controls {
        background: #0f172a;
        border: 1px solid #1e293b;
        border-radius: 8px;
        padding: 12px 18px;
        margin-bottom: 12px;
    }
    .phase-bar {
        display: flex;
        gap: 8px;
        margin: 10px 0 16px 0;
    }
    .phase-step {
        flex: 1;
        padding: 8px 12px;
        border-radius: 6px;
        font-size: 0.8rem;
        font-weight: 700;
        text-align: center;
        border: 1px solid #334155;
    }
    .phase-idle { background: #1e293b; color: #64748b; }
    .phase-active { background: #0284c7; color: #ffffff; border-color: #38bdf8; }
    .phase-done { background: #15803d; color: #ffffff; border-color: #4ade80; }
    .phase-alert { background: #991b1b; color: #fee2e2; border-color: #f87171; }
    .log-box {
        background-color: #0b0f19;
        border: 1px solid #1e293b;
        border-radius: 6px;
        padding: 12px;
        font-family: monospace;
        font-size: 0.82rem;
        height: 380px;
        overflow-y: auto;
    }
    .log-line {
        padding: 3px 0;
        border-bottom: 1px solid #161e2e;
    }
    .kpi-card {
        background-color: #1e293b;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 10px 14px;
        text-align: left;
    }
    .kpi-title {
        color: #94a3b8;
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
    }
    .kpi-num {
        font-size: 1.45rem;
        font-weight: 700;
        margin: 2px 0;
    }
    .bad { color: #f87171; }
    .good { color: #4ade80; }
    .warn { color: #fbbf24; }
</style>
""", unsafe_allow_html=True)

# Adaptive Plotly Map Trace Compatibility
if hasattr(go, "Scattermap"):
    MapTrace = go.Scattermap
    map_config = dict(
        map_style="carto-darkmatter",
        map=dict(center=dict(lat=43.25, lon=-90.5), zoom=6.2)
    )
else:
    MapTrace = getattr(go, "Scattermapbox", go.Scatter)
    map_config = dict(
        mapbox_style="carto-darkmatter",
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

# 60 Waypoints along Corridor (100 meters per step / 1 second per step)
def generate_60s_corridor():
    points = []
    start_lat, start_lon = 42.85000, -89.15000
    madison_lat, madison_lon = 43.07310, -89.40120
    rochester_lat, rochester_lon = 44.01210, -92.48020

    # 0 to 24 (Nominal)
    for i in range(25):
        ratio = i / 25.0
        lat = round(start_lat + (42.98100 - start_lat) * ratio, 5)
        lon = round(start_lon + (-89.30210 - start_lon) * ratio, 5)
        points.append({
            "sec": i,
            "meter": i * 100,
            "lat": lat,
            "lon": lon,
            "temp": round(3.5 + (i * 0.01) + (random.uniform(-0.03, 0.03)), 2),
            "status": "NOMINAL"
        })

    # 25 (Fault Point: I-90 MM 142)
    points.append({
        "sec": 25,
        "meter": 2500,
        "lat": 42.98100,
        "lon": -89.30210,
        "temp": 6.40,
        "status": "ANOMALY_TRIGGERED"
    })

    # 26 to 40 (Diversion to Madison Cold Dock)
    for i in range(26, 41):
        ratio = (i - 25) / 15.0
        lat = round(42.98100 + (madison_lat - 42.98100) * ratio, 5)
        lon = round(-89.30210 + (madison_lon - -89.30210) * ratio, 5)
        temp_val = 6.4 + ((i - 25) * 0.10) if i <= 32 else max(3.8, 7.1 - ((i - 32) * 0.40))
        points.append({
            "sec": i,
            "meter": i * 100,
            "lat": lat,
            "lon": lon,
            "temp": round(temp_val, 2),
            "status": "DIVERTING_TO_DOCK" if i <= 35 else "STABILIZING_AT_BAY"
        })

    # 41 to 59 (Resumed Highway Transit to Mayo Clinic Rochester)
    for i in range(41, 60):
        ratio = (i - 40) / 19.0
        lat = round(madison_lat + (rochester_lat - madison_lat) * ratio, 5)
        lon = round(madison_lon + (rochester_lon - madison_lon) * ratio, 5)
        points.append({
            "sec": i,
            "meter": i * 100,
            "lat": lat,
            "lon": lon,
            "temp": round(3.60 + random.uniform(-0.03, 0.03), 2),
            "status": "CRUISING_STABILIZED" if i < 59 else "DELIVERED_ON_TIME"
        })

    return points

corridor_points = generate_60s_corridor()

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
    st.session_state["run_logs"] = ["[00:00s] 🟢 Fleet telemetry initialized. Unit #409 in transit on I-90."]

cur_sec = st.session_state["current_sec"]
cur_pt = corridor_points[min(cur_sec, len(corridor_points) - 1)]
has_anomaly = cur_sec >= 25
is_resolved = st.session_state["mission_result"] is not None

# Define route_color globally to prevent scope errors
route_color = "#f87171" if (has_anomaly and not is_resolved) else ("#4ade80" if is_resolved else "#38bdf8")

# Governing SLA lookup
anom = st.session_state["active_anomaly"]
governing_sla_id = anom.get("sla_governed", "SLA-COLD-2TO8")
governing_sla = slas_db.get(governing_sla_id, slas_db["SLA-COLD-2TO8"])

# =========================================================================
# 1. TOP HEADER & PROMINENT CONTROLS
# =========================================================================
st.markdown("""
<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
    <div>
        <h2 style="margin: 0; color: #f8fafc; font-weight: 800;">🧊 CryoGuard AI™ | Autonomous Operations Commander</h2>
        <span style="color: #94a3b8; font-size: 0.88rem;">Autonomous Cross-System SLA Risk Defense & Life Sciences Preservation</span>
    </div>
    <div style="text-align: right;">
        <span style="background: #1e293b; border: 1px solid #38bdf8; color: #38bdf8; padding: 6px 14px; border-radius: 20px; font-size: 0.8rem; font-weight: 700;">
            CORRIDOR: CHICAGO ➔ ROCHESTER
        </span>
    </div>
</div>
""", unsafe_allow_html=True)

# Top Control Bar (Start / Stop / Reset)
ctrl_c1, ctrl_c2, ctrl_c3, ctrl_c4 = st.columns([1.5, 1.2, 1.0, 1.5])

with ctrl_c1:
    if not st.session_state["is_running"]:
        if st.button("▶️ Start Auto-Run (60s)", type="primary", use_container_width=True):
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
    if st.button("🔄 Reset System (0s)", use_container_width=True):
        st.session_state["current_sec"] = 0
        st.session_state["is_running"] = False
        st.session_state["mission_result"] = None
        st.session_state["run_logs"] = ["[00:00s] 🟢 System reset. Unit #409 at Origin (0 meters)."]
        st.rerun()

with ctrl_c3:
    sim_speed = st.selectbox("Speed:", [0.3, 0.5, 0.8, 1.0], index=1, format_func=lambda s: f"{s}s/step")

with ctrl_c4:
    st.markdown(f"""
    <div style="text-align: right; padding-top: 4px;">
        <span style="font-size: 1.1rem; font-weight: 800; color: #f8fafc;">⏱️ {cur_sec}s / 60s</span><br>
        <span style="font-size: 0.8rem; color: #38bdf8; font-family: monospace;">{cur_pt['meter']:,}m | ({cur_pt['lat']:.5f}, {cur_pt['lon']:.5f})</span>
    </div>
    """, unsafe_allow_html=True)

# =========================================================================
# 2. RUN PROGRESS TRACKER (PHASES)
# =========================================================================
p1_cls = "phase-done" if cur_sec >= 24 else ("phase-active" if cur_sec > 0 else "phase-idle")
p2_cls = "phase-alert" if (has_anomaly and not is_resolved) else ("phase-done" if cur_sec > 25 else "phase-idle")
p3_cls = "phase-active" if (has_anomaly and not is_resolved) else ("phase-done" if is_resolved else "phase-idle")
p4_cls = "phase-done" if cur_sec >= 58 else ("phase-active" if (is_resolved and cur_sec > 40) else "phase-idle")

st.markdown(f"""
<div class="phase-bar">
    <div class="phase-step {p1_cls}">1. Nominal Cruise (0–24s)</div>
    <div class="phase-step {p2_cls}">2. Anomaly Ingested (25s)</div>
    <div class="phase-step {p3_cls}">3. Agent Self-Healing (26–40s)</div>
    <div class="phase-step {p4_cls}">4. Delivered & Secured (41–60s)</div>
</div>
""", unsafe_allow_html=True)

# Metric KPI Row
k1, k2, k3, k4 = st.columns(4)

with k1:
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-title">Cargo Sensor Temp</div>
        <div class="kpi-num {'bad' if (has_anomaly and not is_resolved) else 'good'}">{cur_pt['temp']} °C</div>
        <div style="font-size: 0.75rem; color: #94a3b8;">Limit: {governing_sla['thermal_band']}</div>
    </div>
    """, unsafe_allow_html=True)

with k2:
    runway_str = "68 Mins" if (has_anomaly and not is_resolved) else ("NOMINAL" if not has_anomaly else "PROTECTED")
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-title">Excursion Runway</div>
        <div class="kpi-num {'bad' if (has_anomaly and not is_resolved) else 'good'}">{runway_str}</div>
        <div style="font-size: 0.75rem; color: #94a3b8;">Max Allowed: {governing_sla['max_cumulative_excursion_mins']} mins</div>
    </div>
    """, unsafe_allow_html=True)

with k3:
    eta_str = "06:45 AM (Late)" if (has_anomaly and not is_resolved) else ("05:54 AM (On Time)" if is_resolved else "05:30 AM (Nominal)")
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-title">Delivery Window</div>
        <div class="kpi-num {'bad' if (has_anomaly and not is_resolved) else 'good'}">{eta_str}</div>
        <div style="font-size: 0.75rem; color: #94a3b8;">SLA Hard-Stop: 06:00 AM CT</div>
    </div>
    """, unsafe_allow_html=True)

with k4:
    expo_str = "$470,000" if (has_anomaly and not is_resolved) else ("$0 AT RISK" if not has_anomaly else "$470,000 SAVED")
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-title">Financial Exposure</div>
        <div class="kpi-num {'bad' if (has_anomaly and not is_resolved) else 'good'}">{expo_str}</div>
        <div style="font-size: 0.75rem; color: #94a3b8;">Governed by {governing_sla_id}</div>
    </div>
    """, unsafe_allow_html=True)

# =========================================================================
# 6. OPERATIONAL SECTION HEADERS AS TABS IN A ROW
# =========================================================================
tab_unified, tab_threat, tab_agent, tab_gxp = st.tabs([
    "🖥️ Unified Live Stream & Map",
    "🚨 Anomaly Threat Physics",
    "🤖 Autonomous Agent Engine",
    "📑 GxP Audit & SLA Contracts"
])

# =========================================================================
# 7. UNIFIED DASHBOARD: LIVE STREAM LOGS + MAP VIEW
# =========================================================================
with tab_unified:
    map_col, log_col = st.columns([1.15, 1])

    with map_col:
        st.markdown("##### 🗺️ High-Precision Corridor Map (100m Live Tracking)")

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
            marker=dict(size=12, color=['#fbbf24', '#38bdf8']),
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
        st.markdown("##### 📜 Real-Time Autonomous Operations Log Stream")
        
        # Display scrolling logs
        log_html = '<div class="log-box">'
        for entry in reversed(st.session_state["run_logs"]):
            log_html += f'<div class="log-line">{entry}</div>'
        log_html += '</div>'
        st.markdown(log_html, unsafe_allow_html=True)

# =========================================================================
# TAB 2: ANOMALY THREAT PHYSICS
# =========================================================================
with tab_threat:
    st.markdown("### 🚨 Threat Ingestion & Excursion Physics")
    t_c1, t_c2 = st.columns([1, 1.2])

    with t_c1:
        st.markdown(f"""
        **Active Anomaly Profile:**
        - **Incident Title:** `{anom['name']}`
        - **Category:** `{anom['category']}`
        - **Fault Code:** `{anom['fault_code']}`
        - **Thermal Drift Rate:** `+{anom['temp_rate']}°C per hour`
        - **Power Draw:** `{anom['power_w']} Watts`
        - **Governing SLA Schedule:** `{governing_sla['name']}`
        - **Risk Exposure:** `{anom['risk_exposure']}`
        """)
        st.info(f"**Anomaly Description:** {anom['description']}")

    with t_c2:
        # Plotly Thermal Curve
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
            line_color="#fbbf24",
            annotation_text=f"SLA Ceiling ({governing_sla['excursion_ceiling']}°C)",
            annotation_position="bottom right"
        )
        fig_t.update_layout(
            title="Real-Time Thermal Drift (Seconds 0 to 60)",
            xaxis_title="Simulation Seconds",
            yaxis_title="Temp (°C)",
            template="plotly_dark",
            height=260,
            margin=dict(l=20, r=20, t=35, b=20)
        )
        st.plotly_chart(fig_t, use_container_width=True)

# =========================================================================
# TAB 3: AUTONOMOUS AGENT ENGINE
# =========================================================================
with tab_agent:
    st.markdown("### 🤖 Autonomous Agent Reasoning & Function Calling")
    if not is_resolved:
        st.info("Agent is standing by. When second 25 triggers, the Gemini reasoning loop executes all 6 function calls here.")
    else:
        res = st.session_state["mission_result"]
        st.success(f"✅ Mission Mitigated: {res['steps_executed']} Autonomous Operations Executed via Gemini Engine ({', '.join(res['models_involved'])})")
        for step in res["trace"]:
            st.markdown(f"""
            <div style="background: #0f172a; border-left: 3px solid #38bdf8; padding: 8px 12px; margin-bottom: 6px; border-radius: 4px;">
                <span style="font-weight: 700; color: #f8fafc;">Step {step['step']}: <code>{step['tool_called']}</code></span>
                <span style="color: #94a3b8; font-size: 0.8rem; margin-left: 10px;">Model: {step['model_engine']}</span>
            </div>
            """, unsafe_allow_html=True)
            st.json(step["result"])

# =========================================================================
# TAB 4: GXP AUDIT & ALL SLA CONTRACTS
# =========================================================================
with tab_gxp:
    st.markdown("### 📑 Enterprise SLA Portfolio & GxP Regulatory Audit")

    g1, g2 = st.columns([1, 1.2])
    with g1:
        st.markdown("#### 📜 Available SLA Contract Schedules")
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
        st.markdown("#### 📑 GxP Deviation Notice & CAPA Report")
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
# REAL-TIME 60-SECOND SIMULATION TICKER & POST-AGENT RESUMPTION
# =========================================================================
if st.session_state.get("is_running", False):
    if cur_sec < 59:
        # At second 25: Trigger anomaly and run Gemini agent
        if cur_sec == 24 and not st.session_state["mission_result"]:
            st.session_state["current_sec"] = 25
            st.session_state["run_logs"].append(
                f"[00:25s] 🚨 ALERT! Anomaly Ingested: {anom['name']} ({anom['fault_code']}) | Temp: 6.4°C | SLA At Risk: $470k"
            )
            time.sleep(sim_speed)
            with st.spinner(f"🚨 Resolving {anom['name']} via Gemini Autonomous Commander..."):
                active_payload = json.loads(json.dumps(base_telemetry))
                active_payload["incident_event"]["sensor_readings"]["compressor_status"] = anom["fault_code"]
                active_payload["incident_event"]["sensor_readings"]["cargo_temperature_celsius"] = 6.4
                res = run_cryoguard_mission(active_payload)
                st.session_state["mission_result"] = res
                
                # Append tool actions into live log stream
                st.session_state["run_logs"].append(f"[00:26s] 🤖 Agent: Extracted {governing_sla_id} clauses (Ceiling: {governing_sla['excursion_ceiling']}°C)")
                st.session_state["run_logs"].append(f"[00:27s] 🤖 Agent: Discovered Madison CryoDock (8.1 mi away)")
                st.session_state["run_logs"].append(f"[00:28s] 🤖 Agent: Locked Bay Door #04 for emergency servicing")
                st.session_state["run_logs"].append(f"[00:29s] 🤖 Agent: Recalculated ETA: 05:54 AM CT (6 mins ahead of SLA)")
                st.session_state["run_logs"].append(f"[00:30s] 🤖 Agent: Dispatched HL7 alert to Mayo Clinic Surgical Desk")
                st.session_state["run_logs"].append(f"[00:31s] 🤖 Agent: Filed FDA 21 CFR Part 11 CAPA Notice. $470k protected.")
                st.session_state["run_logs"].append(f"[00:32s] 🚛 Carrier: Executing diversion to Madison CryoDock...")
            st.rerun()
        else:
            time.sleep(sim_speed)
            next_sec = cur_sec + 1
            st.session_state["current_sec"] = next_sec
            
            # Post-agent milestone logging
            if next_sec == 36:
                st.session_state["run_logs"].append(f"[00:36s] ❄️ Dock: Carrier arrived at Madison Bay Door #04. Dry ice replenished.")
            elif next_sec == 41:
                st.session_state["run_logs"].append(f"[00:41s] 🚛 Carrier: Temperature stabilized at 3.6°C. Resuming route toward Mayo Clinic.")
            elif next_sec == 59:
                st.session_state["run_logs"].append(f"[00:59s] 🏥 Destination: Delivered at Mayo Clinic on time (05:54 AM CT). Zero SLA penalties incurred.")
            elif next_sec % 5 == 0 and next_sec > 25:
                st.session_state["run_logs"].append(
                    f"[{next_sec:02d}:00s] 📍 GPS ({cur_pt['lat']:.5f}, {cur_pt['lon']:.5f}) | Temp: {cur_pt['temp']}°C | Odometer: {cur_pt['meter']:,}m | {cur_pt['status']}"
                )
            elif next_sec % 5 == 0 and next_sec < 25:
                st.session_state["run_logs"].append(
                    f"[{next_sec:02d}:00s] 📍 GPS ({cur_pt['lat']:.5f}, {cur_pt['lon']:.5f}) | Temp: {cur_pt['temp']}°C | Odometer: {cur_pt['meter']:,}m | NOMINAL"
                )

            st.rerun()
    else:
        st.session_state["is_running"] = False
        st.rerun()
