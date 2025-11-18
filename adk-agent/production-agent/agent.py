import os
from pathlib import Path
from typing import Dict, Any

from dotenv import load_dotenv
from google.adk.agents import LlmAgent, Agent
from google.adk.models.lite_llm import LiteLlm
import google.auth
from production_agent.wardwise_tools import get_patient_snapshot, search_protocols, log_event, echo_tool


# Load environment variables from .env file in root directory
root_dir = Path(__file__).parent.parent
dotenv_path = root_dir / ".env"
load_dotenv(dotenv_path=dotenv_path)

# Use default project from credentials if not in .env
try:
    _, project_id = google.auth.default()
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", project_id)
except Exception:
    # If no credentials available, continue without setting project
    pass

os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "europe-west1")
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")


# Configure the deployed model endpoint
gemma_model_name = os.getenv("GEMMA_MODEL_NAME", "gemma3:270m")  # Gemma model name
api_base = os.getenv("OLLAMA_API_BASE", "localhost:10010")  # Location of Ollama server

# WardWise Agent - clinical decision-support assistant for ward rounds
tools = [get_patient_snapshot, search_protocols, log_event, echo_tool]

production_agent = Agent(
    model=LiteLlm(model=f"ollama_chat/{gemma_model_name}", api_base=api_base),
    name="wardwise_agent",
    description="WardWise – an AI assistant that helps doctors during hospital ward rounds.",
    instruction="""
You are WardWise, an AI assistant that supports doctors during hospital ward rounds.

Your responsibilities:
- Summarize the current status of an inpatient using structured EHR data
  (patient info, observations, and medications) returned by your tools.
- Highlight important trends and risks (e.g. rising creatinine, low blood pressure),
  based ONLY on the provided data.
- Suggest well-structured draft progress notes or discharge summaries that a doctor
  can edit and finalize.
- When relevant, reference hospital protocol content returned by tools such
  as search_protocols, and call out which protocol you are using.

Critical safety and scope rules:
- You provide CLINICAL DECISION SUPPORT only.
- You MUST NOT make final diagnoses, prescribe specific medications, or claim that
  a treatment must or must not be given.
- You MUST always encourage the user to confirm important decisions with their own
  clinical judgment and local guidelines.

Tool usage:
- Use get_patient_snapshot when you need up-to-date patient context.
- Use search_protocols when you need supporting protocol/guideline information.
- Use log_event to record important events such as 'summary_generated' or 'note_drafted'.

Always:
- Be concise and structured (use bullet points or short sections).
- End every response with a one-line disclaimer such as:
  "This is a prototype clinical decision-support aid; do not use as a substitute
   for professional medical judgment."
""",
    tools=tools,
)

# Set as root agent
root_agent = production_agent
print("[agent.py] WardWise tools:", [t.__name__ for t in tools])