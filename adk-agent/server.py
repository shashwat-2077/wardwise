import os
from typing import Literal
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from google.adk.cli.fast_api import get_fast_api_app
from pydantic import BaseModel

from production_agent.agent import root_agent
from production_agent.wardwise_tools import get_patient_snapshot, log_event

# Load environment variables from .env file
load_dotenv()

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))

# App arguments for ADK - using in-memory session service for simplicity
app_args = {"agents_dir": AGENT_DIR, "web": True}

# Create FastAPI app with ADK integration
app: FastAPI = get_fast_api_app(**app_args)

# Update app metadata
app.title = "Production ADK Agents - Lab 3"
app.description = "Dual-agent setup: Gemma (conversational) and Llama (with tools for weather and tips)"
app.version = "1.0.0"

OLLAMA_API_BASE = os.getenv("OLLAMA_API_BASE")  # e.g. https://ollama-gemma3-270m-gpu-...a.run.app
GEMMA_MODEL_NAME = os.getenv("GEMMA_MODEL_NAME", "gemma3:270m")


async def call_llm_with_snapshot(prompt: str) -> str:
    """
    Call the GPU Gemma backend (ollama-backend) with a simple prompt and return the text.
    This mirrors what the lab already does, but we control the prompt directly.
    """
    if not OLLAMA_API_BASE:
        raise RuntimeError("OLLAMA_API_BASE env var is not set.")

    # The standard Ollama API endpoint is /api/generate
    url = f"{OLLAMA_API_BASE}/api/generate"
    # Match the schema used in the lab's backend
    payload = {
        "model": GEMMA_MODEL_NAME,
        "prompt": prompt,
        "stream": False,  # We want a single response, not a stream
        "options": {
            "num_predict": 512,
            "temperature": 0.2,
        }
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()

    # The Ollama API returns the full text in the 'response' key
    # when stream=False.
    text = data.get("response")
    if not text:
        raise ValueError(f"Could not find 'response' in Ollama output: {data}")
    return text

class WardWiseSummaryRequest(BaseModel):
    patient_id: str


class WardWiseSummaryResponse(BaseModel):
    patient_id: str
    snapshot_status: str
    snapshot_message: str
    ai_summary: str

class Feedback(BaseModel):
    """Represents user feedback for a conversation."""

    score: int | float
    text: str | None = ""
    invocation_id: str
    log_type: Literal["feedback"] = "feedback"
    service_name: Literal["production-adk-agent"] = "production-adk-agent"
    user_id: str = ""


@app.get("/wardwise/patients/{patient_id}/overview")
async def wardwise_patient_overview(patient_id: str):
    """
    WardWise-style endpoint: fetches patient snapshot from Firestore and asks
    the Gemma LLM to summarize for a ward round.
    """
    # 1) Call our tool directly (bypass ADK's tool-calling)
    snapshot_result = get_patient_snapshot(patient_id)
    if snapshot_result.get("status") != "success":
        raise HTTPException(status_code=404, detail=snapshot_result.get("error_message", "Patient not found"))

    # The get_patient_snapshot tool returns a dictionary with 'patient',
    # 'observations', and 'medications' keys. We need to assemble them.
    snapshot = {
        "patient": snapshot_result.get("patient", {}),
        "observations": snapshot_result.get("observations", []),
        "medications": snapshot_result.get("medications", []),
    }

    # 2) Build a clear prompt for the LLM
    prompt = f"""
You are WardWise, an AI assistant supporting doctors during ward rounds.

You are given structured data for an inpatient in JSON form.

PATIENT SNAPSHOT (JSON):
{snapshot}

Your tasks:
1. Generate a concise 3–5 line ward round summary.
2. Highlight key lab values and vital signs that matter today.
3. Mention current important medications (by name and dose).
4. Call out any obvious risk flags (e.g. rising creatinine, high BP).

Rules:
- Use ONLY the information in the JSON.
- Do NOT invent new diagnoses or medications.
- End with this disclaimer exactly:
  "This is a prototype clinical decision-support aid; do not use as a substitute for professional medical judgment."
"""

    # 3) Ask Gemma for the summary
    try:
        summary = await call_llm_with_snapshot(prompt)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM backend error: {e}")

    # 4) Return a clean JSON response
    return {
        "patient_id": patient_id,
        "snapshot": snapshot,
        "ai_summary": summary,
        "disclaimer": "This is a prototype clinical decision-support aid; do not use as a substitute for professional medical judgment.",
    }
    
@app.post("/wardwise/summary", response_model=WardWiseSummaryResponse)
async def wardwise_summary(req: WardWiseSummaryRequest) -> WardWiseSummaryResponse:
    # 1. Use our Python tool directly to get snapshot
    snapshot = get_patient_snapshot(req.patient_id)

    # Basic error handling
    status = snapshot.get("status", "error")
    message = snapshot.get("message", "")

    # 2. Build a concise context string for the model
    # (For now this expects the dummy snapshot; later it will be real Firestore data)
    patient = snapshot.get("patient", {})
    encounters = snapshot.get("encounters", [])
    observations = snapshot.get("observations", [])
    medications = snapshot.get("medications", [])

    context_str = f"""
PATIENT SNAPSHOT (JSON):
Patient: {patient}
Encounters: {encounters}
Observations (labs/vitals): {observations}
Medications: {medications}
"""

    # 3. Call the WardWise agent with this context + instruction
    user_message = f"""
You are doing a ward round summary for patient {req.patient_id}.

Here is the structured snapshot from the EHR:
{context_str}

Please:
- Summarize the current status in 3–6 sentences.
- Highlight key data points (vitals, labs, meds).
- List 2–4 "Risks to consider" as bullet points.
- List 2–4 "Suggestions for the team to review" as bullet points.
Remember the safety rules and disclaimer.
"""

    # Use the ADK agent runner to get a response
    # (root_agent.run_sync is simplest if available; if not, use root_agent.run)
    response = root_agent.run_sync(user_message)

    # ADK returns an object; get the text content (depends on version)
    # In most cases, response.output_text() or response.messages[-1].content works.
    try:
        ai_text = response.output_text()
    except AttributeError:
        # Fallback if API is slightly different
        ai_text = str(response)

    # 4. Optionally log an event (not required yet)
    _ = log_event(event_type="summary_generated", patient_id=req.patient_id)

    return WardWiseSummaryResponse(
        patient_id=req.patient_id,
        snapshot_status=status,
        snapshot_message=message,
        ai_summary=ai_text,
    )

@app.post("/feedback")
def collect_feedback(feedback: Feedback) -> dict[str, str]:
    """Collect and log user feedback.

    This endpoint allows users to provide feedback on their interactions
    with the agent, which can be used for monitoring and improvement.

    Args:
        feedback: The feedback data including score, text, and metadata

    Returns:
        Success message confirming feedback was received
    """
    # In a production environment, you would typically log this to
    # Cloud Logging, store in a database, or send to analytics service
    print(f"Received feedback: {feedback}")
    
    return {"status": "success", "message": "Feedback received successfully"}


@app.get("/health")
def health_check() -> dict[str, str]:
    """Health check endpoint for monitoring and load balancing.

    This endpoint is used by Cloud Run and load balancers to verify
    that the service is healthy and ready to receive traffic.

    Returns:
        Health status and service information
    """
    return {
        "status": "healthy", 
        "service": "production-adk-agent",
        "version": "1.0.0"
    }


@app.get("/")
def root() -> dict[str, str]:
    """Root endpoint with service information.

    Returns:
        Basic information about the service
    """
    return {
        "service": "WardWise ADK Agent",
        "description": "AI assistant for hospital ward rounds built on ADK + Cloud Run + Gemma",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health"
    }


# Main execution for local development
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")