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
    recalculate_reroute_eta,
    notify_clinical_stakeholders,
    generate_gxp_deviation_report,
)

load_dotenv()

# Prioritized candidate models: User active models first, followed by fallbacks
MODEL_CANDIDATES = [
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
]

# Map tool names to actual Python functions
TOOL_MAP = {
    "get_contract_clauses": get_contract_clauses,
    "find_nearby_cold_storage": find_nearby_cold_storage,
    "reserve_dock_replenishment": reserve_dock_replenishment,
    "recalculate_reroute_eta": recalculate_reroute_eta,
    "notify_clinical_stakeholders": notify_clinical_stakeholders,
    "generate_gxp_deviation_report": generate_gxp_deviation_report,
}

SYSTEM_INSTRUCTION = """
You are CryoGuard-AI, an Autonomous Post-Sales Logistics Operations Commander for high-value life sciences cargo.

Your mission is to mitigate cold-chain excursions, prevent contractual SLA penalties, and ensure patient safety when operational anomalies occur.

OPERATIONAL EXECUTION RULES:
- You MUST invoke tools using function calls to retrieve real data and execute operational actions.
- Do NOT generate simulated answers or write the final summary until you have executed the required tools in sequence:
  1. Check contract clauses (`get_contract_clauses`).
  2. Search for nearby certified cold storage (`find_nearby_cold_storage`).
  3. Reserve an emergency replenishment bay at the nearest suitable depot (`reserve_dock_replenishment`).
  4. Recalculate delivery schedule (`recalculate_reroute_eta`).
  5. Alert the clinical desk (`notify_clinical_stakeholders`).
  6. File the regulatory log (`generate_gxp_deviation_report`).
- Only after all necessary tools have returned their results should you output the final executive debrief.
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
    """
    Attempts generation across prioritized candidate models.
    Falls back gracefully if a model is throttled (429), busy (503), or unavailable.
    """
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
            print(f"⚠️ Model [{model_name}] skipped ({e.__class__.__name__}: {e}). Trying next candidate...")
            last_exception = e

    raise RuntimeError(f"All candidate models failed. Last exception: {last_exception}")

def run_cryoguard_mission(incident_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Executes an autonomous resolution cycle for a cold-chain incident.
    Returns the action trace, tool responses, active model, and final debrief.
    """
    client = get_gemini_client()
    tools_list = list(TOOL_MAP.values())

    event = incident_payload.get("incident_event", {})
    prompt = f"""
EMERGENCY INCIDENT ALERT:
Incident ID: {event.get('event_id')}
Shipment: {event.get('shipment_id')}
Cargo: {event.get('cargo_manifest', {}).get('item')}
Value: ${event.get('cargo_manifest', {}).get('commercial_value_usd'):,} USD
Current Location: {event.get('location', {}).get('highway')} (Lat: {event.get('location', {}).get('latitude')}, Lng: {event.get('location', {}).get('longitude')})
Sensor Status:
- Internal Temp: {event.get('sensor_readings', {}).get('cargo_temperature_celsius')}°C (Threshold ceiling: {event.get('cargo_manifest', {}).get('critical_excursion_ceiling')}°C)
- Temperature Trend: +{event.get('sensor_readings', {}).get('temp_delta_per_hour')}°C per hour
- Compressor Status: {event.get('sensor_readings', {}).get('compressor_status')}
- Dry Ice Status: {event.get('sensor_readings', {}).get('backup_dry_ice_pack_status')}
Schedule:
- SLA Delivery Deadline: {event.get('transit_schedule', {}).get('sla_deadline')}
- Hospital Hard-Stop Surgical Window: {event.get('transit_schedule', {}).get('surgical_hard_stop')}
- Projected Unmitigated ETA: {event.get('transit_schedule', {}).get('projected_unmitigated_eta')}

MANDATORY ACTION:
Call the necessary tools to inspect the SLA contract and search for certified facilities near Lat {event.get('location', {}).get('latitude')}, Lng {event.get('location', {}).get('longitude')} immediately.
"""

    messages = [
        types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
    ]

    action_trace: List[Dict[str, Any]] = []
    models_used: List[str] = []
    max_turns = 10
    final_text = ""

    # Disable automatic function calling so our Python code intercepts and logs every tool call
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

        # Check for function calls
        function_calls = response.function_calls or []

        if not function_calls:
            # Model finished calling tools and returned final text
            text_parts = [part.text for part in model_content.parts if part.text]
            final_text = "\n".join(text_parts)
            break

        # Execute each intercepted function call and build response parts
        tool_response_parts = []
        for call in function_calls:
            fn_name = call.name
            fn_args = dict(call.args) if call.args else {}
            
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

        # Append function responses with role="user"
        messages.append(types.Content(role="user", parts=tool_response_parts))

    return {
        "incident_id": event.get("event_id"),
        "primary_model_used": models_used[0] if models_used else "None",
        "models_involved": models_used,
        "steps_executed": len(action_trace),
        "trace": action_trace,
        "executive_debrief": final_text
    }

if __name__ == "__main__":
    with open("data/telemetry_stream.json", "r") as f:
        data = json.load(f)
    print("Executing CryoGuard autonomous agent test with live tool interception...")
    result = run_cryoguard_mission(data)
    print(f"\n✅ Completed {result['steps_executed']} autonomous actions using engine: {result['models_involved']}!")
    print("\nLive Action Trace:")
    for step in result["trace"]:
        print(f" -> Step {step['step']} [{step['model_engine']}]: {step['tool_called']} | Args: {step['arguments']}")
    print("\n--- Executive Debrief ---")
    print(result["executive_debrief"])
