import json
import math
import random
import time
from datetime import datetime, timedelta
import streamlit as st
import plotly.graph_objects as go
from src.agent import run_cryoguard_mission, evaluate_facility_compatibility
from src.routing import get_driving_route, resample_waypoints

# Map Engine Adapter
if hasattr(go, "Scattermap"):
    MapTrace = go.Scattermap
    IS_SCATTERMAP = True
elif hasattr(go, "Scattermapbox"):
    MapTrace = go.Scattermapbox
    IS_SCATTERMAP = False
else:
    MapTrace = getattr(go, "Scattermapbox", go.Scatter)
    IS_SCATTERMAP = False

def apply_map_camera(fig, style_name, camera_bounds, height=480, uirevision=None):
    layout_dict = {
        "margin": dict(l=0, r=0, t=0, b=0),
        "height": height,
        "showlegend": False,
    }
    if uirevision:
        layout_dict["uirevision"] = uirevision
        
    if IS_SCATTERMAP:
        layout_dict["map"] = dict(
            style=style_name,
            center=camera_bounds["center"],
            zoom=camera_bounds["zoom"]
        )
    else:
        layout_dict["mapbox"] = dict(
            style=style_name,
            center=camera_bounds["center"],
            zoom=camera_bounds["zoom"]
        )
    fig.update_layout(**layout_dict)

def get_hub_display_color(hub_dict: dict) -> str:
    caps = hub_dict.get("capabilities", [])
    if "ULTRA_LOW_CRYOGENIC" in caps or "LIQUID_NITROGEN_RECHARGE" in caps:
        return "#a855f7"  # Purple: Ultra-Low Cryo
    elif "COMPRESSOR_MECHANICAL_REPAIR" in caps:
        return "#f97316"  # Orange: HVAC Repair Bay
    elif "REFRIGERATED_2TO8" in caps:
        return "#10b981"  # Green: 2C to 8C Chiller
    elif "DRY_ICE_TOPPING" in caps:
        return "#38bdf8"  # Cyan: Dry Ice Relay
    return "#64748b"      # Gray: Ambient

SIM_STEP_DELAY = 0.5

st.set_page_config(
    page_title="CryoGuard AI™ | Operations Commander",
    page_icon="🧊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

def format_tool_status(result_obj) -> str:
    if isinstance(result_obj, dict):
        return result_obj.get("status", result_obj.get("deviation_id", "CONFIRMED"))
    elif isinstance(result_obj, list):
        return f"{len(result_obj)} candidate facilities evaluated"
    elif isinstance(result_obj, str):
        return result_obj
    return "COMPLETED"

def compute_map_bounds(waypoints):
    if not waypoints:
        return dict(center=dict(lat=39.8283, lon=-98.5795), zoom=3.8)
    
    lats = [p["lat"] for p in waypoints]
    lons = [p["lon"] for p in waypoints]
    
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)
    
    center_lat = (min_lat + max_lat) / 2.0
    center_lon = (min_lon + max_lon) / 2.0
    
    lat_span = max_lat - min_lat
    lon_span = max_lon - min_lon
    span = max(lat_span, lon_span * 0.75)
    
    if span > 8.0:
        zoom = 5.2
    elif span > 4.5:
        zoom = 6.0
    elif span > 2.0:
        zoom = 6.8
    elif span > 1.0:
        zoom = 7.6
    else:
        zoom = 8.6
        
    return dict(center=dict(lat=round(center_lat, 4), lon=round(center_lon, 4)), zoom=zoom)

# CSS Styling
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
        padding: 14px 22px;
        margin-bottom: 12px;
    }
    .config-card {
        background: #111827 !important;
        border: 1.5px solid #1f2937 !important;
        border-radius: 8px;
        padding: 12px 18px;
        margin-bottom: 12px;
    }
    .stSelectbox label {
        color: #94a3b8 !important;
        font-weight: 700 !important;
        font-size: 0.78rem !important;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    div[data-baseweb="select"] > div {
        background-color: #1e293b !important;
        border: 1px solid #334155 !important;
        color: #f8fafc !important;
        border-radius: 6px !important;
        height: 40px !important;
    }
    div[data-baseweb="select"] * {
        color: #f8fafc !important;
    }
    .stButton > button {
        border-radius: 6px !important;
        font-weight: 700 !important;
        font-size: 0.85rem !important;
        height: 40px !important;
    }
    .stButton > button[kind="primary"] {
        background-color: #0284c7 !important;
        color: #ffffff !important;
        border: 1px solid #38bdf8 !important;
        box-shadow: 0 0 10px rgba(2, 132, 199, 0.4);
    }
    .stButton > button[kind="secondary"], 
    .stButton > button:not([kind="primary"]) {
        background-color: #1e293b !important;
        color: #f8fafc !important;
        border: 1.5px solid #334155 !important;
    }

    .phase-bar {
        display: flex;
        gap: 6px;
        margin: 6px 0 12px 0;
    }
    .phase-step {
        flex: 1;
        padding: 7px 6px;
        border-radius: 6px;
        font-size: 0.74rem;
        font-weight: 700;
        text-align: center;
        border: 1px solid #1f2937;
    }
    .phase-idle { background: #111827 !important; color: #64748b !important; }
    .phase-active { background: #0369a1 !important; color: #ffffff !important; border-color: #38bdf8 !important; }
    .phase-done { background: #14532d !important; color: #4ade80 !important; border-color: #22c55e !important; }
    .phase-alert { background: #7f1d1d !important; color: #fca5a5 !important; border-color: #ef4444 !important; }

    .kpi-card {
        background-color: #111827 !important;
        border: 1px solid #1f2937 !important;
        border-radius: 8px;
        padding: 12px 14px;
        text-align: left;
    }
    .kpi-title {
        color: #94a3b8 !important;
        font-size: 0.72rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .kpi-num {
        font-size: 1.35rem;
        font-weight: 800;
        margin: 2px 0;
    }
    .bad { color: #f87171 !important; }
    .good { color: #4ade80 !important; }
    .warn { color: #fbbf24 !important; }

    .ai-status-banner {
        background: #0f231c !important;
        border: 1px solid #059669 !important;
        border-radius: 6px;
        padding: 8px 14px;
        margin-bottom: 12px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }

    .deliberation-card {
        background: #111827 !important;
        border: 1px solid #1f2937 !important;
        border-left: 5px solid #059669 !important;
        border-radius: 6px;
        padding: 16px 20px;
        margin-bottom: 14px;
    }
    .stage-pill {
        display: inline-block;
        font-weight: 800;
        font-size: 0.72rem;
        padding: 3px 10px;
        border-radius: 4px;
        margin-bottom: 8px;
        letter-spacing: 0.6px;
    }
    .pill-threat { background: #7f1d1d; color: #fecaca; border: 1px solid #ef4444; }
    .pill-contract { background: #1e3a8a; color: #bfdbfe; border: 1px solid #3b82f6; }
    .pill-tradeoff { background: #78350f; color: #fde68a; border: 1px solid #f59e0b; }
    .pill-action { background: #065f46; color: #a7f3d0; border: 1px solid #10b981; }

    .tool-step-card {
        background: #111827 !important;
        border: 1px solid #1f2937 !important;
        border-left: 4px solid #38bdf8 !important;
        border-radius: 6px;
        padding: 12px 16px;
        margin-bottom: 10px;
    }

    .gxp-cert-box {
        background: #0c1322 !important;
        border: 2px solid #0284c7 !important;
        border-radius: 8px;
        padding: 20px 24px;
        margin-bottom: 16px;
    }

    .log-box {
        background-color: #020617 !important;
        border: 1.5px solid #1e293b !important;
        border-radius: 8px;
        padding: 14px;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        font-size: 0.80rem;
        height: 480px;
        overflow-y: auto;
        color: #e2e8f0 !important;
    }
    .log-line {
        padding: 3px 0;
        border-bottom: 1px solid #0f172a;
        line-height: 1.45;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
        border-bottom: 2px solid #1e293b;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #111827 !important;
        border-radius: 6px 6px 0 0 !important;
        padding: 8px 14px !important;
        border: 1px solid #1e293b !important;
        border-bottom: none !important;
    }
    .stTabs [data-baseweb="tab"] p {
        color: #94a3b8 !important;
        font-weight: 600 !important;
        font-size: 0.85rem !important;
    }
    .stTabs [aria-selected="true"] {
        background-color: #1e293b !important;
        border-top: 3px solid #38bdf8 !important;
    }
    .stTabs [aria-selected="true"] p {
        color: #38bdf8 !important;
        font-weight: 800 !important;
    }
</style>
""", unsafe_allow_html=True)

# Load Databases
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

# State Management
if "has_run_started" not in st.session_state:
    st.session_state["has_run_started"] = False
if "is_running" not in st.session_state:
    st.session_state["is_running"] = False
if "mission_clock" not in st.session_state:
    st.session_state["mission_clock"] = 0
if "sim_state" not in st.session_state:
    st.session_state["sim_state"] = "STANDBY"
if "anomaly_count" not in st.session_state:
    st.session_state["anomaly_count"] = 0
if "mission_start_time" not in st.session_state:
    st.session_state["mission_start_time"] = None
if "current_sim_time" not in st.session_state:
    st.session_state["current_sim_time"] = None
if "sla_deadline_time" not in st.session_state:
    st.session_state["sla_deadline_time"] = None
if "current_eta_time" not in st.session_state:
    st.session_state["current_eta_time"] = None
if "total_corridor_miles" not in st.session_state:
    st.session_state["total_corridor_miles"] = 0.0
if "miles_traversed" not in st.session_state:
    st.session_state["miles_traversed"] = 0.0

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
if "map_style_choice" not in st.session_state:
    st.session_state["map_style_choice"] = "open-street-map"

if "main_highway_pts" not in st.session_state:
    st.session_state["main_highway_pts"] = []
if "detour_road_pts" not in st.session_state:
    st.session_state["detour_road_pts"] = []
if "active_leg_pts" not in st.session_state:
    st.session_state["active_leg_pts"] = []
if "leg_idx" not in st.session_state:
    st.session_state["leg_idx"] = 0
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

active_corr_label = st.session_state["active_route"]["corridor_name"] if st.session_state["has_run_started"] else "SYSTEM STANDBY (AWAITING MISSION LAUNCH)"

# Top Mission Control Header
st.markdown(f"""
<div class="main-header">
    <div style="display: flex; justify-content: space-between; align-items: center;">
        <div>
            <h2 style="margin: 0; color: #f8fafc; font-weight: 800; font-size: 1.55rem;">🧊 CryoGuard AI™ | Operations Commander</h2>
            <span style="color: #94a3b8; font-size: 0.86rem; font-weight: 500;">Multi-Customer Cold Chain Telematics & Autonomous SLA Risk Defense</span>
        </div>
        <div style="text-align: right;">
            <span style="background: #1e293b; border: 1px solid #38bdf8; color: #38bdf8; padding: 6px 14px; border-radius: 20px; font-size: 0.80rem; font-weight: 700;">
                {active_corr_label}
            </span>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# Configuration Panel
with st.container():
    st.markdown('<div class="config-card">', unsafe_allow_html=True)
    c1, c2, c3, c4, c5, c6 = st.columns([1.3, 1.2, 1.1, 1.2, 0.9, 0.9])

    with c1:
        cust_opts = {"AUTO": "🎲 Auto (Random Sponsor)"}
        for c in customers_pool:
            cust_opts[c["customer_id"]] = f"{c['customer_name']} ({c['drug_product'][:18]}...)"
        sel_cust = st.selectbox(
            "Customer Sponsor & Cargo:",
            options=list(cust_opts.keys()),
            format_func=lambda k: cust_opts[k],
            index=list(cust_opts.keys()).index(st.session_state["selected_customer_id"]),
            disabled=st.session_state["is_running"]
        )
        st.session_state["selected_customer_id"] = sel_cust

    with c2:
        anomaly_opts = {"AUTO": "🎲 Auto (Dynamic Fault)"}
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
            "AUTO": "🎲 Auto (Triage Pivot)",
            "NONE": "Nominal Protocol",
            "POWER_OUTAGE": "⚡ Substation Outage",
            "DETOUR_BLOCKED": "🚧 Ramp Blocked",
            "SURGERY_MOVED_UP": "🏥 Surgery -45m"
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
        map_themes = {
            "open-street-map": "🛣️ Highway Navigator",
            "carto-darkmatter": "🌌 Cyberpunk Darkroom",
            "carto-positron": "🗺️ Carto Clean Logistics"
        }
        sel_theme = st.selectbox(
            "Map Layer Style:",
            options=list(map_themes.keys()),
            format_func=lambda k: map_themes[k],
            index=list(map_themes.keys()).index(st.session_state["map_style_choice"])
        )
        st.session_state["map_style_choice"] = sel_theme

    with c5:
        st.write("")
        st.write("")
        if not st.session_state["is_running"]:
            if st.button("▶ Launch", type="primary", use_container_width=True):
                chosen_route = random.choice(routes_pool)
                if st.session_state["selected_customer_id"] == "AUTO":
                    chosen_cust = random.choice(customers_pool)
                else:
                    chosen_cust = next(c for c in customers_pool if c["customer_id"] == st.session_state["selected_customer_id"])

                o = chosen_route["origin"]
                dest = chosen_route["destination"]
                c_id = chosen_route.get("route_id")
                road_route = get_driving_route(o["lat"], o["lon"], dest["lat"], dest["lon"], corridor_id=c_id)
                
                highway_waypoints = road_route["waypoints"]
                total_miles = float(road_route.get("distance_miles", 180.0))
                sampled_driving_pts = resample_waypoints(highway_waypoints, target_count=max(60, int(total_miles)))

                now_dt = datetime.now()
                nom_transit_seconds = total_miles / 1.0  # 1.0 mile/second
                tight_sla_buffer_sec = 55.0  # Tight contractual buffer
                sla_deadline = now_dt + timedelta(seconds=nom_transit_seconds + tight_sla_buffer_sec)
                initial_eta = now_dt + timedelta(seconds=nom_transit_seconds)

                st.session_state["mission_start_time"] = now_dt
                st.session_state["current_sim_time"] = now_dt
                st.session_state["sla_deadline_time"] = sla_deadline
                st.session_state["current_eta_time"] = initial_eta
                st.session_state["total_corridor_miles"] = total_miles
                st.session_state["miles_traversed"] = 0.0
                st.session_state["anomaly_count"] = 0

                st.session_state["active_customer"] = chosen_cust
                st.session_state["active_route"] = chosen_route
                st.session_state["main_highway_pts"] = highway_waypoints
                st.session_state["detour_road_pts"] = []
                st.session_state["active_leg_pts"] = sampled_driving_pts
                st.session_state["leg_idx"] = 0
                st.session_state["active_anomaly"] = None
                st.session_state["chosen_hub"] = None
                st.session_state["active_curveball"] = "NONE"
                st.session_state["anomaly_trigger_sec"] = random.randint(16, 24)
                
                st.session_state["cur_lat"] = sampled_driving_pts[0]["lat"]
                st.session_state["cur_lon"] = sampled_driving_pts[0]["lon"]
                st.session_state["cur_temp"] = 3.5
                st.session_state["cur_meter"] = 0
                
                st.session_state["mission_clock"] = 0
                st.session_state["sim_state"] = "NOMINAL"
                st.session_state["mission_result"] = None
                st.session_state["passed_points"] = [{"sec": 0, "temp": 3.5, "lat": st.session_state["cur_lat"], "lon": st.session_state["cur_lon"]}]
                st.session_state["has_run_started"] = True
                
                dep_str = now_dt.strftime("%H:%M:%S")
                st.session_state["run_logs"] = [
                    f"[{dep_str}] 🟢 Unit #409 departed {chosen_route['origin']['name']}.",
                    f"[{dep_str}] 🛣️ Corridor Distance: {total_miles:.1f} mi (Nominal Transit: {nom_transit_seconds:.0f}s @ 1.0 mi/s).",
                    f"[{dep_str}] ⏱️ Contract SLA Deadline: {sla_deadline.strftime('%H:%M:%S')} (Tight Buffer: +55s max).",
                    f"[{dep_str}] 🏢 Sponsor: {chosen_cust['customer_name']} | Asset: {chosen_cust['drug_product']} (${chosen_cust['valuation_usd']:,} USD)"
                ]
                st.session_state["is_running"] = True
                st.rerun()
        else:
            if st.button("⏹ Stop", type="secondary", use_container_width=True):
                st.session_state["is_running"] = False
                st.rerun()

    with c6:
        st.write("")
        st.write("")
        if st.button("🔄 Reset", type="secondary", use_container_width=True):
            st.session_state["has_run_started"] = False
            st.session_state["is_running"] = False
            st.session_state["mission_clock"] = 0
            st.session_state["anomaly_count"] = 0
            st.session_state["sim_state"] = "STANDBY"
            st.session_state["active_customer"] = None
            st.session_state["active_route"] = None
            st.session_state["chosen_hub"] = None
            st.session_state["active_anomaly"] = None
            st.session_state["active_curveball"] = "NONE"
            st.session_state["mission_result"] = None
            st.session_state["main_highway_pts"] = []
            st.session_state["detour_road_pts"] = []
            st.session_state["active_leg_pts"] = []
            st.session_state["passed_points"] = []
            st.session_state["run_logs"] = []
            st.session_state["mission_start_time"] = None
            st.session_state["current_sim_time"] = None
            st.session_state["sla_deadline_time"] = None
            st.session_state["current_eta_time"] = None
            st.session_state["total_corridor_miles"] = 0.0
            st.session_state["miles_traversed"] = 0.0
            st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

# Live Mission Clock Bar
bar_c1, bar_c2 = st.columns([2, 1.2])
with bar_c1:
    if st.session_state["has_run_started"]:
        sim_time_str = st.session_state["current_sim_time"].strftime("%H:%M:%S") if st.session_state.get("current_sim_time") else "--:--:--"
        dep_time_str = st.session_state["mission_start_time"].strftime("%H:%M:%S") if st.session_state.get("mission_start_time") else "--:--:--"
        eta_str = st.session_state["current_eta_time"].strftime("%H:%M:%S") if st.session_state.get("current_eta_time") else "--:--:--"
        cust_badge = st.session_state['active_customer']['customer_name']
        cur_mi = st.session_state.get("miles_traversed", 0.0)
        tot_mi = st.session_state.get("total_corridor_miles", 0.0)
        
        st.markdown(f"""
        <div style="padding: 2px 0 6px 0; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap;">
            <div>
                <span style="font-size: 1.25rem; font-weight: 800; color: #38bdf8;">🕒 Live Clock: {sim_time_str}</span>
                <span style="margin-left: 10px; font-size: 0.84rem; color: #94a3b8;">(Dep: <b>{dep_time_str}</b> | ETA: <b>{eta_str}</b>)</span>
            </div>
            <div style="font-family: ui-monospace, monospace; font-weight: 700; font-size: 0.88rem; color: #a7f3d0;">
                🛣️ {cur_mi:.1f} / {tot_mi:.1f} mi (1.0 mi/s) | GPS ({st.session_state['cur_lat']:.4f}, {st.session_state['cur_lon']:.4f})
            </div>
            <div style="background: #1e293b; color: #94a3b8; font-size: 0.8rem; padding: 4px 10px; border-radius: 4px;">
                Client: <b>{cust_badge}</b>
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown('<div style="padding-top: 4px;"><span style="color: #64748b; font-weight: 600;">Mission Standby — Select customer parameters and click Launch</span></div>', unsafe_allow_html=True)

with bar_c2:
    if st.session_state["has_run_started"] and st.session_state["is_running"]:
        if st.session_state["sim_state"] in ["EN_ROUTE_HUB", "SERVICING", "NOMINAL", "FINAL_LEG"]:
            if st.button("⚡ Inject Surprise Disruption!", type="primary", use_container_width=True):
                st.session_state["active_curveball"] = "POWER_OUTAGE"
                st.session_state["anomaly_count"] = st.session_state.get("anomaly_count", 0) + 1
                cur_t = st.session_state["current_sim_time"].strftime("%H:%M:%S") if st.session_state.get("current_sim_time") else "T+NOW"
                st.session_state["run_logs"].append(f"[{cur_t}] ⚠️ SURPRISE DISRUPTION: Target Facility Substation Trip! Emergency re-plan triggered.")
                
                route_info = st.session_state["active_route"]
                cust = st.session_state["active_customer"]
                sla_key = st.session_state.get("active_anomaly", {}).get("sla_governed", "SLA-COLD-2TO8") if st.session_state["active_anomaly"] else "SLA-COLD-2TO8"
                
                cand_hubs = route_info.get("candidate_hubs", [])
                alt_hubs = [h for h in cand_hubs if h["facility_id"] != (st.session_state["chosen_hub"]["facility_id"] if st.session_state["chosen_hub"] else "")]
                
                cust["current_temp"] = st.session_state["cur_temp"]
                cust["excursion_ceiling"] = 8.0
                decision = evaluate_facility_compatibility(
                    cust, {"fault_code": "POWER_OUTAGE_TRIP"}, alt_hubs,
                    st.session_state["cur_lat"], st.session_state["cur_lon"],
                    route_info["origin"], route_info["destination"],
                    current_sim_time=st.session_state.get("current_sim_time"),
                    sla_deadline=st.session_state.get("sla_deadline_time")
                )
                new_hub = decision["best_hub"] if decision["best_hub"] else (alt_hubs[0] if alt_hubs else cand_hubs[0])
                st.session_state["chosen_hub"] = new_hub
                
                detour_meta = get_driving_route(st.session_state["cur_lat"], st.session_state["cur_lon"], new_hub["lat"], new_hub["lon"])
                st.session_state["detour_road_pts"] = detour_meta["waypoints"]
                st.session_state["active_leg_pts"] = resample_waypoints(detour_meta["waypoints"], target_count=max(15, int(detour_meta.get("distance_miles", 20))))
                st.session_state["leg_idx"] = 0
                st.session_state["service_countdown"] = 14
                st.session_state["sim_state"] = "EN_ROUTE_HUB"
                st.session_state["run_logs"].append(f"[{cur_t}] 🔄 Agent Re-route: Diverting to Secondary Cold Hub -> {new_hub['name']} ({detour_meta['distance_miles']} mi).")
                st.rerun()

# Phase Bar
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

# 4 KPI Cards
k1, k2, k3, k4 = st.columns(4)

if not st.session_state["has_run_started"]:
    for k, title, val in [(k1, "Cargo Sensor Temp", "-- °C"), (k2, "Excursion Runway", "-- Mins"), (k3, "Delivery ETA & SLA Target", "--:--:--"), (k4, "Financial Exposure", "$0")]:
        with k:
            st.markdown(f'<div class="kpi-card"><div class="kpi-title">{title}</div><div class="kpi-num" style="color: #64748b;">{val}</div><div style="font-size: 0.75rem; color: #64748b;">Standby</div></div>', unsafe_allow_html=True)
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
        st.markdown(f'<div class="kpi-card"><div class="kpi-title">Cargo Sensor Temp</div><div class="kpi-num {"bad" if is_hot else "good"}">{cur_temp:.1f} °C</div><div style="font-size: 0.75rem; color: #94a3b8;">Band: {band_spec}</div></div>', unsafe_allow_html=True)
    with k2:
        runway_val = f"{max(4, int((ceiling_temp - cur_temp) / 0.04))} Mins" if is_hot else "NOMINAL"
        st.markdown(f'<div class="kpi-card"><div class="kpi-title">Excursion Runway</div><div class="kpi-num {"bad" if is_hot else "good"}">{runway_val}</div><div style="font-size: 0.75rem; color: #94a3b8;">Ceiling: {ceiling_temp}°C</div></div>', unsafe_allow_html=True)
    with k3:
        eta_dt = st.session_state.get("current_eta_time")
        sla_dt = st.session_state.get("sla_deadline_time")
        if eta_dt and sla_dt:
            is_breached = eta_dt > sla_dt
            diff_sec = abs((eta_dt - sla_dt).total_seconds())
            diff_mins = int(diff_sec // 60)
            diff_s = int(diff_sec % 60)
            
            eta_display = eta_dt.strftime("%H:%M:%S")
            sla_display = sla_dt.strftime("%H:%M:%S")
            
            if is_breached:
                eta_val = f"{eta_display} (BREACH)"
                eta_col = "bad"
                sub_label = f"⚠️ Exceeds SLA by +{diff_mins}m {diff_s}s (Cutoff: {sla_display})"
            elif diff_sec < 15.0:
                eta_val = f"{eta_display} (BORDERLINE)"
                eta_col = "warn"
                sub_label = f"⚠️ Tight buffer: only +{diff_s}s slack (Cutoff: {sla_display})"
            else:
                eta_val = f"{eta_display} (ON TIME)"
                eta_col = "good"
                sub_label = f"✅ Buffer: +{diff_mins}m {diff_s}s slack (Cutoff: {sla_display})"
        else:
            eta_val = "--:--:--"
            eta_col = "good"
            sub_label = "SLA Target Active"
        st.markdown(f'<div class="kpi-card"><div class="kpi-title">Delivery ETA & SLA Target</div><div class="kpi-num {eta_col}">{eta_val}</div><div style="font-size: 0.75rem; color: #94a3b8;">{sub_label}</div></div>', unsafe_allow_html=True)
    with k4:
        if is_hot:
            expo_str = f"${sla_exposure_usd:,}"
            expo_col = "bad"
            expo_sub = f"Liability: {cust.get('customer_name')[:20]}"
        elif st.session_state["sim_state"] == "DELIVERED":
            if st.session_state["is_partial_breach"] or (eta_dt and sla_dt and eta_dt > sla_dt):
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

        st.markdown(f'<div class="kpi-card"><div class="kpi-title">Financial Protection</div><div class="kpi-num {expo_col}">{expo_str}</div><div style="font-size: 0.75rem; color: #94a3b8;">{expo_sub}</div></div>', unsafe_allow_html=True)

# Compact AI Status Banner
if st.session_state["has_run_started"] and st.session_state["mission_result"]:
    res = st.session_state["mission_result"]
    st.markdown(f"""
    <div class="ai-status-banner">
        <div>
            <span style="font-weight: 800; color: #6ee7b7; font-size: 0.85rem;">🧠 Gemini Autonomous Triage Verified</span>
            <span style="color: #94a3b8; font-size: 0.82rem; margin-left: 10px;">Engine: <b>{', '.join(res['models_involved'])}</b> | 4 Decision Stages Audited</span>
        </div>
        <div>
            <span style="background: #065f46; color: #ecfdf5; font-size: 0.75rem; font-weight: 700; padding: 3px 10px; border-radius: 12px;">
                Review Full Reasoning in "AI Cognitive Feed" Tab ➔
            </span>
        </div>
    </div>
    """, unsafe_allow_html=True)

# Tabs Container
tab_unified, tab_deliberation, tab_agent, tab_contract, tab_threat, tab_gxp = st.tabs([
    "🖥️ Live Telematics & Log Stream",
    "🧠 AI Cognitive Deliberation Feed",
    "🤖 Agent Tool Trace & Execution",
    "📑 Customer Contract & Quality Agreement",
    "🚨 Threat Physics & Thermal Curve",
    "📜 Certified GxP / FDA 21 CFR Part 11 Audit Log"
])

# Tab 1: The Only Map
with tab_unified:
    map_col, log_col = st.columns([1.25, 1.0])

    with map_col:
        st.markdown("<h5 style='margin-bottom: 6px;'>🗺️ Closed-Loop Telematics Map (Interstate Network View)</h5>", unsafe_allow_html=True)
        
        fig_map = go.Figure()
        active_map_style = st.session_state["map_style_choice"]

        if not st.session_state["has_run_started"]:
            fig_map.add_trace(MapTrace(
                lat=[39.8283], lon=[-98.5795], mode='markers+text',
                marker=dict(size=10, color='#64748b'), text=["System in Standby"]
            ))
            apply_map_camera(fig_map, active_map_style, dict(center=dict(lat=39.8, lon=-98.5), zoom=3.5), height=480)
        else:
            route_info = st.session_state["active_route"]
            chosen_hub = st.session_state["chosen_hub"]
            passed_pts = st.session_state["passed_points"]
            main_pts = st.session_state["main_highway_pts"]
            detour_pts = st.session_state["detour_road_pts"]

            if main_pts:
                fig_map.add_trace(MapTrace(
                    lat=[p["lat"] for p in main_pts],
                    lon=[p["lon"] for p in main_pts],
                    mode='lines',
                    line=dict(width=7, color="rgba(56, 189, 248, 0.35)"),
                    hoverinfo="none",
                    name="Interstate Glow"
                ))
                fig_map.add_trace(MapTrace(
                    lat=[p["lat"] for p in main_pts],
                    lon=[p["lon"] for p in main_pts],
                    mode='lines',
                    line=dict(width=3.5, color="#0284c7"),
                    name="Interstate Highway Corridor"
                ))

            if detour_pts:
                fig_map.add_trace(MapTrace(
                    lat=[p["lat"] for p in detour_pts],
                    lon=[p["lon"] for p in detour_pts],
                    mode='lines',
                    line=dict(width=4, color="#f59e0b"),
                    name="Off-Ramp Detour Route"
                ))

            if passed_pts:
                fig_map.add_trace(MapTrace(
                    lat=[p["lat"] for p in passed_pts],
                    lon=[p["lon"] for p in passed_pts],
                    mode='lines',
                    line=dict(width=4.5, color="#ef4444" if cur_temp > 6.0 else "#10b981"),
                    name="Traversed Path"
                ))

            fig_map.add_trace(MapTrace(
                lat=[st.session_state["cur_lat"]],
                lon=[st.session_state["cur_lon"]],
                mode='markers+text',
                marker=dict(size=20, color="#ef4444" if cur_temp > 6.0 else "#38bdf8"),
                text=[f"🚛 Unit #409 ({cur_temp:.1f}°C)"],
                textposition="top right",
                name="Carrier"
            ))

            fac_lats = []
            fac_lons = []
            fac_texts = []
            fac_colors = []

            # Origin
            orig_hub = route_info["origin"]
            orig_color = "#fbbf24" if (chosen_hub and chosen_hub.get("facility_id") == orig_hub.get("facility_id")) else get_hub_display_color(orig_hub)
            fac_lats.append(orig_hub["lat"])
            fac_lons.append(orig_hub["lon"])
            fac_texts.append(f"🏭 ORIGIN: {orig_hub['name'][:22]}")
            fac_colors.append(orig_color)

            # Destination
            dest_hub = route_info["destination"]
            dest_color = "#fbbf24" if (chosen_hub and chosen_hub.get("facility_id") == dest_hub.get("facility_id")) else get_hub_display_color(dest_hub)
            fac_lats.append(dest_hub["lat"])
            fac_lons.append(dest_hub["lon"])
            fac_texts.append(f"🏥 DESTINATION: {dest_hub['name'][:22]}")
            fac_colors.append(dest_color)

            # Intermediate and Off-Route Hubs
            for h in route_info.get("candidate_hubs", []):
                is_selected = chosen_hub and h.get("facility_id") == chosen_hub.get("facility_id")
                fac_lats.append(h["lat"])
                fac_lons.append(h["lon"])
                services_summary = "/".join([c[:4] for c in h.get("capabilities", [])])
                
                if is_selected:
                    fac_texts.append(f"⭐ ACTIVE TARGET: {h['name'][:24]}")
                    fac_colors.append("#fbbf24")
                else:
                    is_offroute = "OFFROUTE" in h.get("facility_id", "") or "Off-Route" in h.get("name", "")
                    prefix = "🌐 OFF-ROUTE" if is_offroute else "🏢 HUB"
                    fac_texts.append(f"{prefix}: {h['name'][:20]} [{services_summary}]")
                    fac_colors.append(get_hub_display_color(h))

            fig_map.add_trace(MapTrace(
                lat=fac_lats, lon=fac_lons, mode='markers+text',
                marker=dict(size=14, color=fac_colors),
                text=fac_texts, textposition="bottom right", name="Facilities"
            ))

            camera_bounds = compute_map_bounds(main_pts)
            apply_map_camera(fig_map, active_map_style, camera_bounds, height=480, uirevision="cryoguard_mission_view")

        map_col.plotly_chart(fig_map, use_container_width=True, key="unique_app_telematics_map")

        # Color Legend
        st.markdown("""
        <div style="display: flex; gap: 14px; flex-wrap: wrap; margin-top: 8px; padding: 8px 12px; background: #0f172a; border-radius: 6px; font-size: 0.76rem; border: 1px solid #1e293b;">
            <span style="display: inline-flex; align-items: center;"><span style="width: 10px; height: 10px; background: #a855f7; border-radius: 50%; display: inline-block; margin-right: 6px;"></span>🟣 Ultra-Low Cryo (LN2)</span>
            <span style="display: inline-flex; align-items: center;"><span style="width: 10px; height: 10px; background: #f97316; border-radius: 50%; display: inline-block; margin-right: 6px;"></span>🟠 HVAC Mechanical Bay</span>
            <span style="display: inline-flex; align-items: center;"><span style="width: 10px; height: 10px; background: #10b981; border-radius: 50%; display: inline-block; margin-right: 6px;"></span>🟢 2°C to 8°C Chiller</span>
            <span style="display: inline-flex; align-items: center;"><span style="width: 10px; height: 10px; background: #38bdf8; border-radius: 50%; display: inline-block; margin-right: 6px;"></span>🔵 Dry Ice Relay Post</span>
            <span style="display: inline-flex; align-items: center;"><span style="width: 10px; height: 10px; background: #64748b; border-radius: 50%; display: inline-block; margin-right: 6px;"></span>⚪ Ambient / CRT Depot</span>
            <span style="display: inline-flex; align-items: center;"><span style="width: 10px; height: 10px; background: #fbbf24; border-radius: 50%; display: inline-block; margin-right: 6px;"></span>⭐ Active Recovery Target</span>
        </div>
        """, unsafe_allow_html=True)

    with log_col:
        st.markdown("<h5 style='margin-bottom: 6px;'>📜 Real-Time Autonomous Operations Log Stream</h5>", unsafe_allow_html=True)
        if not st.session_state["has_run_started"]:
            log_html = '<div class="log-box"><div class="log-line">[--:--:--] ⚪ System in standby. Select customer parameters and click "Launch".</div></div>'
        else:
            log_html = '<div class="log-box">'
            for entry in reversed(st.session_state["run_logs"]):
                log_html += f'<div class="log-line">{entry}</div>'
            log_html += '</div>'
        log_col.markdown(log_html, unsafe_allow_html=True)

# Tab 2: Cognitive Deliberation Feed
with tab_deliberation:
    st.markdown("### 🧠 Gemini Live Cognitive Deliberation Feed")
    if not st.session_state["has_run_started"] or not st.session_state["mission_result"]:
        st.info("The agent's multi-turn inner monologue will populate here as soon as an anomaly triggers.")
    else:
        res = st.session_state["mission_result"]
        thoughts = list(res.get("cognitive_monologue", []))
        
        st.markdown(f"""
        <div style="background: #111827; border: 1px solid #1f2937; border-radius: 8px; padding: 12px 18px; margin-bottom: 14px; display: flex; justify-content: space-between;">
            <span style="color: #6ee7b7; font-weight: 800; font-size: 0.95rem;">Model Engine: {', '.join(res['models_involved'])}</span>
            <span style="color: #94a3b8; font-size: 0.85rem;">Autonomous Decision Loop (Multi-Turn Quality Agreement Triage)</span>
        </div>
        """, unsafe_allow_html=True)

        for thought in thoughts:
            sub_sections = thought.split(chr(10) + chr(10))
            for sub in sub_sections:
                if not sub.strip():
                    continue
                pill_html = ""
                content = sub
                if "[THREAT ANALYSIS]:" in sub:
                    pill_html = '<span class="stage-pill pill-threat">STAGE 1: PHYSICAL TELEMETRY & THREAT ASSESSMENT</span>'
                    content = sub.replace("[THREAT ANALYSIS]:", "").strip()
                elif "[CONTRACT AUDIT]:" in sub:
                    pill_html = '<span class="stage-pill pill-contract">STAGE 2: SPONSOR QUALITY AGREEMENT (Q-AGR) AUDIT</span>'
                    content = sub.replace("[CONTRACT AUDIT]:", "").strip()
                elif "[FACILITY TRADE-OFF]:" in sub:
                    pill_html = '<span class="stage-pill pill-tradeoff">STAGE 3: MULTI-CRITERIA FACILITY TRADE-OFF MATRIX</span>'
                    content = sub.replace("[FACILITY TRADE-OFF]:", "").strip()
                elif "[DISPATCH ACTION]:" in sub:
                    pill_html = '<span class="stage-pill pill-action">STAGE 4: AUTONOMOUS OPERATIONAL DISPATCH ORDERS</span>'
                    content = sub.replace("[DISPATCH ACTION]:", "").strip()

                st.markdown(f"""
                <div class="deliberation-card">
                    <div>{pill_html}</div>
                    <div style="font-size: 0.90rem; line-height: 1.55; color: #f1f5f9; margin-top: 6px;">{content}</div>
                </div>
                """, unsafe_allow_html=True)

# Tab 3: Tool Execution Trace
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
            r = step["result"]
            r_summary = format_tool_status(r)
            st.markdown(f"""
            <div class="tool-step-card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                    <span style="font-weight: 800; font-size: 0.92rem; color: #38bdf8;">Step {step['step']}: <code>{step['tool_called']}</code></span>
                    <span style="background: #1e293b; color: #a7f3d0; font-size: 0.76rem; padding: 2px 8px; border-radius: 4px; font-weight: 700;">{r_summary}</span>
                </div>
                <div style="font-size: 0.82rem; color: #94a3b8; margin-bottom: 6px;">Engine: <b>{step['model_engine']}</b> | Arguments: <code>{json.dumps(step['arguments'])}</code></div>
            </div>
            """, unsafe_allow_html=True)
            with st.expander(f"🔍 Inspect Full Return Payload ({step['tool_called']})"):
                st.json(r)

# Tab 4: Markdown Contract View
with tab_contract:
    st.markdown("### 📑 Customer Contract & Governing Quality Agreement")
    if not st.session_state["has_run_started"]:
        st.info("System in standby. Sponsor Quality Agreement will render upon mission launch.")
    else:
        cust = st.session_state["active_customer"]
        cid = cust["customer_id"]
        sla_key = cust.get("governing_sla_id", "SLA-COLD-2TO8")
        contract_file = f"contracts/{cid}_{sla_key}.md"
        
        try:
            with open(contract_file, "r", encoding="utf-8") as f:
                contract_md = f.read()
            st.markdown(contract_md)
        except Exception:
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

# Tab 5: Threat Physics
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

# Tab 6: GxP Audit
with tab_gxp:
    st.markdown("### 📜 Certified GxP / FDA 21 CFR Part 11 Regulatory Audit Log")
    if not st.session_state["has_run_started"] or not st.session_state["mission_result"]:
        st.info("Regulatory CAPA deviation log will compile dynamically upon incident resolution.")
    else:
        res = st.session_state["mission_result"]
        cust = st.session_state["active_customer"]
        gxp_report = next((s["result"] for s in res["trace"] if s["tool_called"] == "generate_gxp_deviation_report"), None)
        
        if gxp_report:
            dev_id = gxp_report.get("deviation_id", "DEV-2026-9041")
            st.markdown(f"""
            <div class="gxp-cert-box">
                <div style="display: flex; justify-content: space-between; border-bottom: 1px solid #1e293b; padding-bottom: 12px; margin-bottom: 14px;">
                    <div>
                        <h4 style="margin: 0; color: #38bdf8;">CERTIFIED GXP DEVIATION NOTICE & CAPA DISPOSITION</h4>
                        <span style="font-size: 0.80rem; color: #94a3b8;">Document ID: <b>{dev_id}</b> | Standard: <b>FDA 21 CFR Part 11 & cGMP Annex 15</b></span>
                    </div>
                    <div style="text-align: right;">
                        <span style="background: #14532d; color: #4ade80; padding: 4px 10px; border-radius: 4px; font-weight: 700; font-size: 0.80rem;">VERIFIED SAFE / RELEASED</span>
                    </div>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px; font-size: 0.85rem; margin-bottom: 14px;">
                    <div><b>Commercial Sponsor:</b> {cust.get('customer_name')}</div>
                    <div><b>Therapeutic Asset:</b> {cust.get('drug_product')} (Lot: {cust.get('batch_lot')})</div>
                    <div><b>Root Cause:</b> {gxp_report.get('root_cause_summary')}</div>
                    <div><b>Capital Loss Prevented:</b> ${gxp_report.get('financial_loss_prevented_usd', 470000):,} USD</div>
                    <div><b>Quality Assurance Disposition:</b> {gxp_report.get('batch_disposition')}</div>
                    <div><b>Product Quality Impact:</b> {gxp_report.get('product_quality_impact')}</div>
                </div>
                <div style="background: #090d16; border: 1px solid #1e293b; border-radius: 6px; padding: 10px 14px; font-size: 0.78rem; font-family: monospace; color: #94a3b8;">
                    <b>21 CFR Part 11 Digital Signature Hash:</b> SHA256:{abs(hash(dev_id))}a981c900e4bf88912<br>
                    <b>Signer Authority:</b> Autonomous CryoGuard GxP Compliance Daemon | Status: CERTIFIED INTACT
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            st.download_button(
                label="📥 Download Certified GxP Deviation Notice (JSON)",
                data=json.dumps(gxp_report, indent=2),
                file_name=f"GxP_Deviation_{res['incident_id']}.json",
                mime="application/json"
            )

# Simulation Engine Loop (1 mi/s constant speed)
if st.session_state.get("is_running", False) and st.session_state.get("has_run_started", False):
    time.sleep(SIM_STEP_DELAY)
    
    st.session_state["mission_clock"] += 1
    clock = st.session_state["mission_clock"]
    
    if st.session_state.get("current_sim_time"):
        st.session_state["current_sim_time"] += timedelta(seconds=1)
    else:
        st.session_state["current_sim_time"] = datetime.now()
        
    cur_time_str = st.session_state["current_sim_time"].strftime("%H:%M:%S")

    s_state = st.session_state["sim_state"]
    route_info = st.session_state["active_route"]
    cust = st.session_state["active_customer"]
    f_sec = st.session_state["anomaly_trigger_sec"]
    
    leg_pts = st.session_state["active_leg_pts"]
    pt_idx = st.session_state["leg_idx"]
    
    # Speed is exactly 1.0 mile per tick
    st.session_state["miles_traversed"] = round(st.session_state.get("miles_traversed", 0.0) + 1.0, 1)
    
    # Recalculate dynamic ETA based on remaining road distance + pending dock hold
    rem_miles = max(0.0, st.session_state.get("total_corridor_miles", 180.0) - st.session_state["miles_traversed"])
    servicing_hold = st.session_state.get("service_countdown", 0) if s_state in ["EN_ROUTE_HUB", "SERVICING"] else 0
    st.session_state["current_eta_time"] = st.session_state["current_sim_time"] + timedelta(seconds=rem_miles + servicing_hold)

    if pt_idx < len(leg_pts) - 1:
        st.session_state["leg_idx"] += 1
        next_pt = leg_pts[st.session_state["leg_idx"]]
        st.session_state["cur_lat"] = next_pt["lat"]
        st.session_state["cur_lon"] = next_pt["lon"]
        st.session_state["cur_meter"] += 1609

    if s_state == "NOMINAL":
        st.session_state["cur_temp"] = round(3.5 + random.uniform(-0.03, 0.03), 2)
        st.session_state["run_logs"].append(
            f"[{cur_time_str}] 📍 GPS ({st.session_state['cur_lat']:.4f}, {st.session_state['cur_lon']:.4f}) | Temp: {st.session_state['cur_temp']}°C | {st.session_state['miles_traversed']:.1f} mi"
        )
        
        if clock >= f_sec:
            st.session_state["sim_state"] = "FAULT_DETECTED"
            st.session_state["cur_temp"] = 6.4
            st.session_state["anomaly_count"] = st.session_state.get("anomaly_count", 0) + 1
            
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
            risk_usd = cust.get("valuation_usd", 470000)
            
            st.session_state["run_logs"].append(
                f"[{cur_time_str}] 🚨 SENSOR FAULT DETECTED: {active_anom['name']} ({active_anom['fault_code']})!"
            )
            st.session_state["run_logs"].append(
                f"[{cur_time_str}] 📑 Contract Audit: Triggered {cust['contract_title']} (Valuation: ${risk_usd:,} USD)"
            )
            
            # Kinematic Multi-Criteria Triage Evaluation
            c_lat, c_lon = st.session_state["cur_lat"], st.session_state["cur_lon"]
            cand_hubs = route_info.get("candidate_hubs", [])
            origin_pt = route_info["origin"]
            dest_pt = route_info["destination"]
            
            cust["current_temp"] = 6.4
            cust["excursion_ceiling"] = 8.0
            decision = evaluate_facility_compatibility(
                cust, active_anom, cand_hubs, c_lat, c_lon, origin_pt, dest_pt,
                current_sim_time=st.session_state.get("current_sim_time"),
                sla_deadline=st.session_state.get("sla_deadline_time")
            )
            
            strategy = decision["strategy"]
            if strategy == "DIVERT_SPECIALTY_HUB" and decision["best_hub"]:
                chosen_hub = decision["best_hub"]
                st.session_state["chosen_hub"] = chosen_hub
                st.session_state["run_logs"].append(
                    f"[{cur_time_str}] 🏢 Triage Decision: Selected {chosen_hub['name']} based on capability, runway, and SLA margins."
                )
            elif strategy == "ABORT_RETURN_TO_ORIGIN":
                chosen_hub = dict(origin_pt)
                st.session_state["chosen_hub"] = chosen_hub
                st.session_state["run_logs"].append(
                    f"[{cur_time_str}] ⚠️ STRATEGIC ABORT: No viable forward hub supports required cryo service. Returning to origin!"
                )
            else:
                chosen_hub = dict(dest_pt)
                st.session_state["chosen_hub"] = chosen_hub
                st.session_state["is_partial_breach"] = True
                st.session_state["run_logs"].append(
                    f"[{cur_time_str}] ⚠️ EXPEDITE PUSH: Continuing to destination under SLA delay penalty. Inbound emergency bay alerted."
                )

            # Invoke agent function calling mission trace
            active_payload = json.loads(json.dumps(base_telemetry))
            active_payload["customer_data"] = cust
            active_payload["governing_sla_id"] = sla_key
            active_payload["candidate_hubs"] = cand_hubs
            active_payload["curveball_condition"] = chosen_cb
            active_payload["incident_event"]["location"]["latitude"] = c_lat
            active_payload["incident_event"]["location"]["longitude"] = c_lon
            active_payload["incident_event"]["sensor_readings"]["compressor_status"] = active_anom["fault_code"]
            active_payload["incident_event"]["sensor_readings"]["cargo_temperature_celsius"] = 6.4
            
            res = run_cryoguard_mission(active_payload, is_replan=False)
            st.session_state["mission_result"] = res
            
            # Fetch detour route and set active driving leg
            detour_meta = get_driving_route(c_lat, c_lon, chosen_hub["lat"], chosen_hub["lon"])
            detour_waypoints = detour_meta["waypoints"]
            
            st.session_state["detour_road_pts"] = detour_waypoints
            # 1.0 mi/s resampling
            detour_mi = max(12, int(detour_meta.get("distance_miles", 20)))
            st.session_state["active_leg_pts"] = resample_waypoints(detour_waypoints, target_count=detour_mi)
            st.session_state["leg_idx"] = 0
            st.session_state["service_countdown"] = 14
            st.session_state["sim_state"] = "EN_ROUTE_HUB"
            
            for s in res["trace"]:
                st_str = format_tool_status(s.get("result"))
                st.session_state["run_logs"].append(
                    f"[{cur_time_str}] 🤖 Agent: Executed `{s['tool_called']}` ➔ {st_str}"
                )
            st.session_state["run_logs"].append(
                f"[{cur_time_str}] 🚀 Detour Route Calculated: Taking arterial branch to {chosen_hub['name']} ({detour_meta['distance_miles']} mi)."
            )

    elif s_state == "EN_ROUTE_HUB":
        st.session_state["cur_temp"] = round(min(7.45, st.session_state["cur_temp"] + 0.06), 2)
        st.session_state["run_logs"].append(
            f"[{cur_time_str}] 🛣️ Detour Transit: Branching toward {st.session_state['chosen_hub']['name']}. Temp: {st.session_state['cur_temp']}°C."
        )
        
        if pt_idx >= len(leg_pts) - 1:
            st.session_state["sim_state"] = "SERVICING"
            st.session_state["run_logs"].append(
                f"[{cur_time_str}] 🏢 Bay Arrival: Docked at {st.session_state['chosen_hub']['name']} Door #04. Servicing initiated."
            )

    elif s_state == "SERVICING":
        st.session_state["service_countdown"] -= 1
        st.session_state["cur_temp"] = round(max(3.6, st.session_state["cur_temp"] - 0.28), 2)
        
        st.session_state["run_logs"].append(
            f"[{cur_time_str}] ❄️ Servicing Active: Cryo charging in progress. Temp: {st.session_state['cur_temp']}°C. (Hold: {st.session_state['service_countdown']}s)"
        )
        
        if st.session_state["service_countdown"] <= 0:
            st.session_state["sim_state"] = "FINAL_LEG"
            
            dest = route_info["destination"]
            hub = st.session_state["chosen_hub"]
            final_meta = get_driving_route(hub["lat"], hub["lon"], dest["lat"], dest["lon"], corridor_id=route_info.get("route_id"))
            
            st.session_state["cur_lat"] = hub["lat"]
            st.session_state["cur_lon"] = hub["lon"]
            st.session_state["detour_road_pts"] = []
            st.session_state["main_highway_pts"] = final_meta["waypoints"]
            
            rem_drive_miles = max(15, int(final_meta.get("distance_miles", 50)))
            st.session_state["active_leg_pts"] = resample_waypoints(final_meta["waypoints"], target_count=rem_drive_miles)
            st.session_state["leg_idx"] = 0
            
            st.session_state["run_logs"].append(
                f"[{cur_time_str}] ✅ Servicing Complete: Thermal envelope restored (3.6°C). Re-entering interstate to {cust['consignee_facility']} ({rem_drive_miles} mi @ 1.0 mi/s)."
            )

    elif s_state == "FINAL_LEG":
        st.session_state["cur_temp"] = round(3.6 + random.uniform(-0.02, 0.02), 2)
        st.session_state["run_logs"].append(
            f"[{cur_time_str}] 🛣️ Final Mile Approach: {st.session_state['miles_traversed']:.1f} mi traversed. Stabilized at {st.session_state['cur_temp']}°C."
        )
        
        if pt_idx >= len(leg_pts) - 1:
            st.session_state["sim_state"] = "DELIVERED"
            st.session_state["is_running"] = False
            saved_total = cust.get("valuation_usd", 470000)
            
            st.session_state["run_logs"].append(
                f"[{cur_time_str}] 🏥 Delivery Complete: Reached {cust['consignee_facility']}. Zero batch spoilage! Preserved ${saved_total:,} USD under {cust['contract_title']}."
            )

    st.session_state["passed_points"].append({
        "sec": clock,
        "temp": st.session_state["cur_temp"],
        "lat": st.session_state["cur_lat"],
        "lon": st.session_state["cur_lon"]
    })

    st.rerun()
