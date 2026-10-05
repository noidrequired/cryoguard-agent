import json
import os
from typing import Dict, Any, List, Tuple
from dotenv import load_dotenv
from google import genai
from google.genai import types

from src.tools import (
    get_contract_clauses,
    find_nearby_cold_storage,
    reserve_dock_replenishment,
    dispatch_hotshot_courier_relay,
    deploy_mobile_tech_intercept,
    execute_sterile_seal_inspection,
    recharge_cryogenic_dewar,
    recalculate_reroute_eta,
    notify_clinical_stakeholders,
    generate_gxp_deviation_report,
)

load_dotenv()

MODEL_CANDIDATES = [
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
]

TOOL_MAP = {
    "get_contract_clauses": get_contract_clauses,
    "find_nearby_cold_storage": find_nearby_cold_storage,
    "reserve_dock_replenishment": reserve_dock_replenishment,
    "dispatch_hotshot_courier_relay": dispatch_hotshot_courier_relay,
    "deploy_mobile_tech_intercept": deploy_mobile_tech_intercept,
    "execute_sterile_seal_inspection": execute_sterile_seal_inspection,
    "recharge_cryogenic_dewar": recharge_cryogenic_dewar,
    "recalculate_reroute_eta": recalculate_reroute_eta,
    "notify_clinical_stakeholders": notify_clinical_stakeholders,
    "generate_gxp_deviation_report": generate_gxp_deviation_report,
}

SYSTEM_INSTRUCTION = """
You are CryoGuard-AI, an Autonomous Post-Sales Logistics Operations Commander for high-value life sciences cargo.

Your mission is to mitigate operational anomalies, prevent contractual SLA penalties, and protect patient surgical viable windows.

COGNITIVE REASONING REQUIREMENT:
Before executing any tool, you MUST output a brief, transparent analytical thought explaining:
1. The exact constraint or risk you are evaluating.
2. Why you are choosing this tool over alternatives.
3. If an unexpected operational curveball occurs (e.g., a candidate facility has an outage), explain your pivot and trade-off explicitly.

EXECUTION PIPELINE:
- Inspect SLA contract terms (`get_contract_clauses`).
- Evaluate candidate facilities or mitigation options (`find_nearby_cold_storage`, `dispatch_hotshot_courier_relay`, `deploy_mobile_tech_intercept`, etc.).
- Reserve the optimal operational asset.
- Recalculate ETA against surgical deadline (`recalculate_reroute_eta`).
- Transmit emergency clinical notice (`notify_clinical_stakeholders`).
- File regulatory CAPA deviation notice (`generate_gxp_deviation_report`).

After completing all tool executions, provide:
1. A concise, authoritative Executive Debrief.
2. A realistic Driver Radio Dispatch transmission.
3. An HL7 Clinical Advisory notice.
"""

def get_gemini_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key.startswith("PASTE_"):
        raise ValueError("Valid GEMINI_API_KEY not found. Please check your .env file.")
    return genai.Client(api_key=api_key)

def generate_with_fallback(
    client: genai.Client,
    contents: List[Any],
    config: types.GenerateContentConfig,
    candidates: List[str] = MODEL_CANDIDATES
) -> Tuple[Any, str]:
    last_exception = None
    for model_name in candidates:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=config,
            )
            return response, model_name
        except Exception as e:
            last_exception = e

    raise RuntimeError(f"All candidate models failed. Last exception: {last_exception}")

def run_cryoguard_mission(incident_payload: Dict[str, Any]) -> Dict[str, Any]:
    client = get_gemini_client()
    tools_list = list(TOOL_MAP.values())

    event = incident_payload.get("incident_event", {})
    sla_id = incident_payload.get("governing_sla_id", "SLA-COLD-2TO8")
    candidate_hubs = incident_payload.get("candidate_hubs", [])
    curveball = incident_payload.get("curveball_condition", None)
    
    prompt = f"""
EMERGENCY TELEMETRY INCIDENT INGESTION:
Incident ID: {event.get('event_id')}
Shipment: {event.get('shipment_id')}
Cargo: {event.get('cargo_manifest', {}).get('item')}
Governing SLA Schedule: {sla_id}
Active Highway: {event.get('location', {}).get('highway')} (Lat: {event.get('location', {}).get('latitude')}, Lng: {event.get('location', {}).get('longitude')})
Sensor Telemetry:
- Fault Code: {event.get('sensor_readings', {}).get('compressor_status')}
- Cargo Temp: {event.get('sensor_readings', {}).get('cargo_temperature_celsius')}°C
- Schedule SLA Deadline: {event.get('transit_schedule', {}).get('sla_deadline')}

Operational Corridor Candidate Facilities:
{json.dumps(candidate_hubs, indent=2)}

ACTIVE CORRIDOR ANOMALY / CURVEBALL:
{curveball if curveball else "None (Standard anomaly mitigation protocol)"}

Execute autonomous reasoning loop, evaluate constraints, and deploy the optimal recovery strategy.
"""

    messages = [
        types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
    ]

    action_trace: List[Dict[str, Any]] = []
    cognitive_monologue: List[str] = []
    models_used: List[str] = []
    max_turns = 10
    final_text = ""

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        tools=tools_list,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        temperature=0.1,
    )

    for turn in range(max_turns):
        response, active_model = generate_with_fallback(
            client=client,
            contents=messages,
            config=config,
            candidates=MODEL_CANDIDATES,
        )
        if active_model not in models_used:
            models_used.append(active_model)

        candidate = response.candidates[0]
        model_content = candidate.content
        messages.append(model_content)

        # Capture any inner chain-of-thought text emitted before/alongside function calls
        turn_text_parts = [part.text for part in model_content.parts if part.text]
        if turn_text_parts:
            thought = " ".join(turn_text_parts).strip()
            if thought:
                cognitive_monologue.append(thought)

        function_calls = response.function_calls or []
        if not function_calls:
            final_text = "\n".join(turn_text_parts)
            break

        tool_response_parts = []
        for call in function_calls:
            fn_name = call.name
            fn_args = dict(call.args) if call.args else {}
            
            # Inject corridor hubs and curveball into candidate lookup if applicable
            if fn_name == "find_nearby_cold_storage":
                fn_args.setdefault("candidate_hubs", candidate_hubs)
                fn_args.setdefault("curveball_condition", curveball)

            tool_fn = TOOL_MAP.get(fn_name)
            if tool_fn:
                try:
                    tool_result = tool_fn(**fn_args)
                except Exception as e:
                    tool_result = {"error": str(e)}
            else:
                tool_result = {"error": f"Unknown tool {fn_name}"}

            action_trace.append({
                "step": len(action_trace) + 1,
                "model_engine": active_model,
                "tool_called": fn_name,
                "arguments": fn_args,
                "result": tool_result
            })

            tool_response_parts.append(
                types.Part.from_function_response(
                    name=fn_name,
                    response={"result": tool_result}
                )
            )

        messages.append(types.Content(role="user", parts=tool_response_parts))

    return {
        "incident_id": event.get("event_id"),
        "primary_model_used": models_used[0] if models_used else "None",
        "models_involved": models_used,
        "steps_executed": len(action_trace),
        "cognitive_monologue": cognitive_monologue,
        "trace": action_trace,
        "executive_debrief": final_text
    }
