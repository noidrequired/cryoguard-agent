import json
import streamlit as st
import plotly.graph_objects as go
from datetime import datetime
from src.agent import run_cryoguard_mission

st.set_page_config(
    page_title="CryoGuard-AI | SLA Risk & Operations Commander",
    page_icon="🧊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom Styling for Mission Control Look
st.markdown("""
<style>
    .metric-card {
        background-color: #0e1117;
        border: 1px solid #262730;
        border-radius: 8px;
        padding: 14px;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# Load Incident & Facilities Data
@st.cache_data
def load_data():
    with open("data/telemetry_stream.json", "r") as f:
        telemetry = json.load(f)
    with open("data/facilities.json", "r") as f:
        facilities = json.load(f)
    return telemetry, facilities

telemetry_data, facilities_data = load_data()
event = telemetry_data["incident_event"]

# Header
st.title("🧊 CryoGuard-AI: Autonomous Post-Sales Operations Commander")
st.caption("Google Cloud AI Builder Cup 2026 | Enterprise SLA & GxP Cold-Chain Protection")

has_run = "mission_result" in st.session_state

# Top KPI Row
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        label="Internal Cargo Temp",
        value=f"{event['sensor_readings']['cargo_temperature_celsius']} °C",
        delta="+1.4 °C / hr (Rising)" if not has_run else "Stabilized at 3.8 °C",
        delta_color="inverse"
    )
with col2:
    st.metric(
        label="Thermal Budget to Breach",
        value="68 Minutes" if not has_run else "RECOVERED (Protected)",
        delta="- Critical Excursion Imminent" if not has_run else "+ Safe Band Restored",
        delta_color="inverse"
    )
with col3:
    st.metric(
        label="Clinical SLA Delivery Window",
        value="06:00 AM CT",
        delta="Projected: 06:45 AM (Late)" if not has_run else "Mitigated: 05:54 AM (On Time)",
        delta_color="inverse"
    )
with col4:
    st.metric(
        label="Commercial Liability at Risk",
        value="$470,000 USD",
        delta="Exposed to Total Spoilage" if not has_run else "$470,000 Loss Prevented",
        delta_color="off" if not has_run else "normal"
    )

st.divider()

# Main Two-Column Layout
left_col, right_col = st.columns([1, 1.2])

with left_col:
    st.subheader("📡 Live Incident & Telemetry Stream")
    
    st.info(f"""
    **Active Consignment:** `{event['cargo_manifest']['item']}`  
    **Patient ID:** `{event['cargo_manifest']['patient_id']}`  
    **Location:** {event['location']['highway']}  
    **Compressor Status:** ⚠️ `{event['sensor_readings']['compressor_status']}`  
    **Battery/Reefer Status:** Dry Ice Pack Depleted (92%)
    """)

    # Thermal Decay Plotly Chart
    fig = go.Figure()
    
    time_pts = ["01:30 AM", "02:00 AM", "02:14 AM (Fault)", "03:00 AM", "03:22 AM (Breach)", "04:00 AM"]
    temp_unmitigated = [3.8, 4.2, 6.4, 7.5, 8.0, 8.9]
    temp_mitigated = [3.8, 4.2, 6.4, 5.1, 4.0, 3.8]

    fig.add_trace(go.Scatter(
        x=time_pts,
        y=temp_unmitigated,
        mode="lines+markers",
        name="Unmitigated Trajectory",
        line=dict(color="#ff4b4b", width=3, dash="dash")
    ))

    if has_run:
        fig.add_trace(go.Scatter(
            x=time_pts,
            y=temp_mitigated,
            mode="lines+markers",
            name="Autonomous CryoGuard Reroute",
            line=dict(color="#00d26a", width=3)
        ))

    # Add 8.0 C Critical SLA Ceiling Line
    fig.add_hline(
        y=8.0,
        line_dash="dot",
        line_color="#ffbb00",
        annotation_text="Critical Excursion Ceiling (8.0°C)",
        annotation_position="bottom right"
    )

    fig.update_layout(
        title="Thermal Trajectory vs. Regulatory Excursion Limit",
        xaxis_title="Timeline",
        yaxis_title="Internal Temperature (°C)",
        template="plotly_dark",
        height=320,
        margin=dict(l=20, r=20, t=40, b=20)
    )

    st.plotly_chart(fig, use_container_width=True)

    # Mission Launch Button
    if st.button("🚀 Trigger CryoGuard Autonomous Resolution", type="primary", use_container_width=True):
        with st.spinner("CryoGuard-AI is analyzing contracts, querying facilities, and calculating reroute..."):
            result = run_cryoguard_mission(telemetry_data)
            st.session_state["mission_result"] = result
            st.rerun()

with right_col:
    st.subheader("🤖 Autonomous Agent Mission Control")

    if not has_run:
        st.warning("Awaiting operational trigger. Click 'Trigger CryoGuard Autonomous Resolution' on the left to activate the agent reasoning loop.")
        
        with st.expander("📄 View Ingested Quality Agreement (SLA Contract)", expanded=False):
            with open("contracts/biovanguard_quality_agreement.md", "r") as f:
                st.markdown(f.read())
                
        with st.expander("📍 Available Regional Facilities Database", expanded=False):
            st.json(facilities_data)
    else:
        result = st.session_state["mission_result"]
        
        st.success(f"Mission Completed: {result['steps_executed']} Autonomous Operations Executed via Gemini Engine ({', '.join(result['models_involved'])})")

        # Step-by-Step Action Trace
        with st.expander("🔍 Real-Time Agent Tool Calling Trace", expanded=True):
            for step in result["trace"]:
                st.markdown(f"""
                **Step {step['step']}:** `{step['tool_called']}`  
                *Engine:* `{step['model_engine']}`  
                *Input Arguments:* `{step['arguments']}`  
                """)
                st.json(step["result"])
                st.markdown("---")

        # Executive Debrief Tab
        st.subheader("📋 Executive Resolution Debrief")
        st.markdown(result["executive_debrief"])

        # Downloadable GxP Audit Artifact
        gxp_report = next((s["result"] for s in result["trace"] if s["tool_called"] == "generate_gxp_deviation_report"), None)
        if gxp_report:
            st.download_button(
                label="📥 Download Official GxP 21 CFR Part 11 Deviation Report (JSON)",
                data=json.dumps(gxp_report, indent=2),
                file_name=f"GxP_Deviation_{result['incident_id']}.json",
                mime="application/json",
                use_container_width=True
            )
