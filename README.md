# WardWise – AI Assistant for Hospital Ward Rounds

WardWise is a prototype **clinical decision-support assistant** for doctors doing hospital ward rounds.

During a round, a doctor selects a patient and WardWise:

- Summarizes the current inpatient status (reason for admission, key vitals, key labs).
- Highlights important trends and potential risks (e.g., rising creatinine).
- Shows active medications.
- Drafts ward-round notes or discharge summaries with an explicit safety disclaimer.

This project was built as part of **BNB Marathon 2025: Developers (Bengaluru)** using **Google Cloud Run**, **Firestore**, **BigQuery**, **Cloud Storage**, and a **Gemma 3 LLM** backend.

> ⚠️ **Disclaimer**  
> WardWise is a **prototype** and uses fully synthetic demo data.  
> It is **not** a medical device and must not be used for real patient care.

---

## High-Level Architecture

WardWise follows the “AI app on Cloud Run” reference pattern:

- **Cloud Run – `wardwise-backend`**
  - FastAPI + Google Agent Development Kit (ADK) service.
  - Exposes REST APIs (e.g. `/wardwise/patients/{patient_id}/overview`).
  - Implements WardWise tools:
    - `get_patient_snapshot` – fetch demo patient data from Firestore.
    - `search_protocols` – retrieve protocol snippets from Cloud Storage.
    - `log_event` – write anonymized usage events to BigQuery.
  - Calls the Gemma LLM backend for summarization and note drafting.

- **Cloud Run – Gemma GPU LLM backend**
  - Deployed from the Lab 3 codelab.
  - Hosts a Gemma 3 model via an Ollama-like HTTP `/generate` API.
  - Receives JSON prompts from `wardwise-backend` and returns text responses.

- **Datastores**
  - **Firestore (Native mode)**  
    - Collections:
      - `patients` – basic demographics, ward/bed, primary diagnosis.
      - `observations` – vitals and labs over time.
      - `medications` – active medications per patient.
      - (optionally) `sessions`, `notes` for chat and documentation.
  - **BigQuery**  
    - Dataset: `wardwise_analytics`  
    - Table: `events` (event_time, user_id, patient_id, event_type, latency_ms).
  - **Cloud Storage**  
    - Bucket: `wardwise-protocols-<project-id>`  
    - Folder `protocols/` containing simple text “protocol” docs (e.g. heart failure, sepsis).

- **Development & Ops**
  - Built and deployed from **Google Cloud Shell Editor**.
  - Python dependency management with **uv**.
  - Uses ADK Dev UI (`/dev-ui/`) for debugging and prompt experimentation.

---

## Features

- **Ward-round overview API**
  - `GET /wardwise/patients/{patient_id}/overview`
  - Fetches a structured patient snapshot from Firestore:
    - Demographics, ward/bed, primary diagnosis.
    - Latest vitals and labs (e.g. BP, HR, Creatinine).
    - Active medications.
  - Calls the Gemma GPU backend to generate a concise ward-round summary.
  - Returns:
    - `snapshot` – structured JSON.
    - `ai_summary` – natural-language summary.
    - `disclaimer` – fixed safety disclaimer.

- **Tools layer (for WardWise agent)**
  - `get_patient_snapshot(patient_id)`  
    Build a compact JSON snapshot by querying Firestore.
  - `search_protocols(query)`  
    Read protocol text files from Cloud Storage and return matching snippets.
  - `log_event(event_type, user_id, patient_id, latency_ms)`  
    Insert a row into `wardwise_analytics.events` in BigQuery.

- **Synthetic demo data**
  - `scripts/seed_demo_data.py` populates Firestore with:
    - Patient `pat-001` admitted with acute decompensated heart failure.
    - Vital signs and creatinine trend over the last 24–48 hours.
    - Medications (e.g. IV Furosemide, PO Ramipril).

- **ADK Dev UI**
  - Accessible at `/dev-ui/` on the `wardwise-backend` Cloud Run URL.
  - Used to:
    - Inspect the `wardwise_agent`.
    - Prototype doctor-style queries over the patient snapshot JSON.
    - Experiment with summarization, risk analysis, and note drafting.

---

## Tech Stack

- **Runtime**
  - Python 3
  - FastAPI
  - Google Agent Development Kit (ADK)
  - uv (for dependency management and running the app)
  - Uvicorn

- **Google Cloud**
  - Cloud Run (wardwise-backend, Gemma GPU backend)
  - Firestore (Native mode)
  - BigQuery
  - Cloud Storage
  - Cloud Shell Editor

- **AI**
  - Gemma 3 LLM hosted behind an Ollama-style backend on Cloud Run GPU

---

## Repository Structure

Roughly:

```text
.
├── adk-agent/
│   ├── server.py                      # FastAPI + ADK app entrypoint
│   ├── pyproject.toml                 # Python project + dependencies
│   ├── production_agent/
│   │   ├── agent.py                   # WardWise ADK agent definition
│   │   ├── wardwise_tools.py          # Firestore / GCS / BigQuery tools
│   ├── scripts/
│   │   └── seed_demo_data.py          # Seed synthetic Firestore data
│   └── Dockerfile                     # Container for wardwise-backend
│
├── ollama-backend/                    # Gemma GPU LLM backend (from Lab 3)
│   └── ...                            # Dockerfile and deployment scripts
│
└── README.md                          # This file


⸻

Prerequisites
	•	GCP project with billing enabled.
	•	Google Cloud SDK already configured (Cloud Shell has this pre-installed).
	•	Permissions to:
	•	Deploy Cloud Run services.
	•	Create Firestore, BigQuery datasets/tables, and Storage buckets.

⸻

Setup & Deployment

All commands below assume you are in Google Cloud Shell.

1. Clone this repository

git clone <your-repo-url>
cd <repo-root>/adk-agent

Make sure your GCP project is set:

gcloud config set project YOUR_PROJECT_ID

Set region (example: asia-south1):

export REGION=asia-south1

2. Enable required APIs

gcloud services enable \
  run.googleapis.com \
  firestore.googleapis.com \
  bigquery.googleapis.com \
  storage.googleapis.com \
  cloudbuild.googleapis.com

3. Create Firestore database (Native)

gcloud firestore databases create \
  --database="(default)" \
  --location=$REGION \
  --type=firestore-native

4. Create BigQuery dataset and events table

bq --location=$REGION mk wardwise_analytics

bq mk --table wardwise_analytics.events \
  event_time:TIMESTAMP,user_id:STRING,patient_id:STRING,event_type:STRING,latency_ms:INT64

5. Create Cloud Storage bucket for protocols

PROJECT_ID=$(gcloud config get-value project)
BUCKET="wardwise-protocols-$PROJECT_ID"

gsutil mb -l $REGION gs://$BUCKET

# Optional: upload simple protocol docs
mkdir -p protocols
echo "Heart Failure Management Protocol (Demo)..." > protocols/heart_failure_management.txt
echo "Sepsis Bundle Protocol (Demo)..." > protocols/sepsis_bundle.txt

gsutil cp protocols/* gs://$BUCKET/protocols/

6. Install Python dependencies (local dev)

From adk-agent/:

uv sync

7. Seed Firestore with demo data

cd adk-agent
uv run python scripts/seed_demo_data.py

This creates pat-001 and related documents in Firestore.

8. Deploy the Gemma GPU backend (LLM service)

Follow the instructions from the original Lab 3 codelab to deploy the GPU-backed Gemma service. You should end up with a Cloud Run URL like:

https://ollama-gemma3-270m-gpu-xxxxxx-<region>.run.app

Export it:

export OLLAMA_API_BASE="https://ollama-gemma3-270m-gpu-xxxxxx-<region>.run.app"
export GEMMA_MODEL_NAME="gemma3:270m"

9. Build and deploy wardwise-backend to Cloud Run

From adk-agent/:

gcloud builds submit \
  --tag gcr.io/$(gcloud config get-value project)/wardwise-backend .

Then deploy:

gcloud run deploy wardwise-backend \
  --image gcr.io/$(gcloud config get-value project)/wardwise-backend \
  --region $REGION \
  --platform managed \
  --allow-unauthenticated \
  --memory=1Gi \
  --cpu=1 \
  --set-env-vars GEMMA_MODEL_NAME=$GEMMA_MODEL_NAME,OLLAMA_API_BASE=$OLLAMA_API_BASE

Grab the service URL:

WARDWISE_URL=$(gcloud run services describe wardwise-backend \
  --region $REGION \
  --format="value(status.url)")
echo $WARDWISE_URL


⸻

Usage

1. WardWise Overview API

Call the overview endpoint for the demo patient pat-001:

curl "$WARDWISE_URL/wardwise/patients/pat-001/overview"

Example response (simplified):

{
  "patient_id": "pat-001",
  "snapshot": {
    "patient_id": "pat-001",
    "name": "John Doe",
    "ward": "Cardiology",
    "bed_number": "B12",
    "primary_diag": "Acute decompensated heart failure",
    "observations": [
      { "label": "Blood Pressure", "value": "150/90", "unit": "mmHg", ... },
      { "label": "Heart Rate", "value": "96", "unit": "bpm", ... },
      { "label": "Serum Creatinine", "value": "1.8", "unit": "mg/dL", ... }
    ],
    "medications": [
      { "name": "Furosemide", "dose": "40 mg IV BD" },
      { "name": "Ramipril", "dose": "5 mg PO OD" }
    ]
  },
  "ai_summary": "65-year-old male admitted with acute decompensated heart failure...",
  "disclaimer": "This is a prototype clinical decision-support aid; do not use as a substitute for professional medical judgment."
}

This is the main API you can use in a UI or demo.

2. FastAPI Docs

Open the automatic docs:

https://<WARDWISE_URL>/docs

You can try GET /wardwise/patients/{patient_id}/overview interactively from the browser.

3. ADK Dev UI

Access the ADK Dev UI at:

https://<WARDWISE_URL>/dev-ui/

Use it to:
	•	Inspect the wardwise_agent.
	•	Paste a snapshot JSON into the first message.
	•	Ask doctor-style questions such as:
	•	“Summarize this patient for ward round in 4–5 lines.”
	•	“What trends in creatinine and vitals are concerning?”
	•	“Draft a SOAP note for today’s visit.”

⸻

Safety & Limitations
	•	Uses synthetic, de-identified demo data only.
	•	Designed strictly as a clinical decision-support prototype:
	•	Prompts and summaries explicitly avoid making final diagnoses or prescribing.
	•	Every summary includes a disclaimer.
	•	Not evaluated or approved for real-world clinical use.

⸻

Possible Future Enhancements
	•	Add more realistic EHR-like schemas and multiple demo patients.
	•	Implement /notes/draft and /notes/{note_id} APIs for progress/discharge notes.
	•	Integrate authentication and basic role-based access control.
	•	Implement richer analytics dashboards using BigQuery + Looker Studio.
	•	Swap/balance between Gemma and Gemini models for different tasks (e.g. code vs clinical summarization).

⸻

Credits
	•	Built by Shashwat Pattanayak for BNB Marathon 2025: Developers – Bengaluru.
	•	Based on the “Prototype to Production – Deploy Your ADK Agent to Cloud Run with GPU” codelab and extended into the WardWise healthcare use case.

