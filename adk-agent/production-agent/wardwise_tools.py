import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from google.cloud import firestore, bigquery, storage
from pydantic import BaseModel


# ---------- Pydantic models (tool outputs) ----------

class Observation(BaseModel):
    label: str
    code: str
    value: str
    unit: Optional[str] = None
    recorded_at: Optional[str] = None  # ISO string


class Medication(BaseModel):
    name: str
    dose: str
    route: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None


class PatientSnapshot(BaseModel):
    patient_id: str
    name: str
    ward: Optional[str] = None
    bed_number: Optional[str] = None
    primary_diag: Optional[str] = None
    admitted_at: Optional[str] = None

    observations: List[Observation] = []
    medications: List[Medication] = []


class ProtocolSnippet(BaseModel):
    title: str
    snippet: str
    uri: str


# ---------- Helper: global clients ----------

_firestore_client: Optional[firestore.Client] = None
_bigquery_client: Optional[bigquery.Client] = None
_storage_client: Optional[storage.Client] = None


def get_firestore_client() -> firestore.Client:
    global _firestore_client
    if _firestore_client is None:
        _firestore_client = firestore.Client()
    return _firestore_client


def get_bigquery_client() -> bigquery.Client:
    global _bigquery_client
    if _bigquery_client is None:
        _bigquery_client = bigquery.Client()
    return _bigquery_client


def get_storage_client() -> storage.Client:
    global _storage_client
    if _storage_client is None:
        _storage_client = storage.Client()
    return _storage_client


# ---------- Tool 1: get_patient_snapshot ----------

def get_patient_snapshot(patient_id: str) -> Dict[str, Any]:
    """
    Fetch a summarized snapshot of a demo patient from Firestore.

    Args:
        patient_id: The patient identifier (e.g. "pat-001").

    Returns:
        A dictionary containing a PatientSnapshot-like structure with:
        - basic patient info
        - a few recent observations
        - a few active medications

    This tool is used by the WardWise agent to prepare ward-round summaries.
    """
    print(f"[WardWise] get_patient_snapshot called with patient_id={patient_id}")
    db = get_firestore_client()

    # 1) Patient core document
    patient_ref = db.collection("patients").document(patient_id)
    patient_doc = patient_ref.get()

    if not patient_doc.exists:
        print(f"[WardWise] Patient {patient_id} not found in Firestore.")
        return {
            "status": "error",
            "message": f"Patient {patient_id} not found in Firestore.",
        }

    p = patient_doc.to_dict() or {}

    # 2) Recent observations for this patient
    obs_query = (
        db.collection("observations")
        .where(filter=firestore.FieldFilter("patient_id", "==", patient_id))
        .order_by("recorded_at", direction=firestore.Query.DESCENDING)
        .limit(5)
    )
    obs_docs = list(obs_query.stream())

    observations: List[Observation] = []
    for doc in obs_docs:
        o = doc.to_dict() or {}
        recorded_at = o.get("recorded_at")
        if hasattr(recorded_at, "isoformat"):
            recorded_at = recorded_at.isoformat()

        observations.append(
            Observation(
                label=o.get("label") or o.get("code") or "Observation",
                code=o.get("code", ""),
                value=str(o.get("value", "")),
                unit=o.get("unit"),
                recorded_at=recorded_at,
            )
        )

    # 3) Active medications
    meds_query = (
        db.collection("medications")
        .where(filter=firestore.FieldFilter("patient_id", "==", patient_id))
        .limit(10)
    )
    meds_docs = list(meds_query.stream())

    medications: List[Medication] = []
    for doc in meds_docs:
        m = doc.to_dict() or {}

        start_time = m.get("start_time")
        if hasattr(start_time, "isoformat"):
            start_time = start_time.isoformat()

        end_time = m.get("end_time")
        if hasattr(end_time, "isoformat"):
            end_time = end_time.isoformat()

        medications.append(
            Medication(
                name=m.get("name", "Medication"),
                dose=m.get("dose", ""),
                route=m.get("route"),
                start_time=start_time,
                end_time=end_time,
            )
        )

    print(f"[WardWise] Built snapshot for {patient_id} with "
          f"{len(observations)} observations and {len(medications)} medications.")


    return {
        "status": "success",
        "message": f"Snapshot retrieved for patient {patient_id}",
        "patient": {
            "patient_id": patient_id,
            "name": p.get("name", "Demo Patient"),
            "ward": p.get("ward"),
            "bed_number": p.get("bed_number"),
            "primary_diag": p.get("primary_diag"),
            "admitted_at": str(p.get("admitted_at", "")),
        },
        "observations": [obs.model_dump() for obs in observations],
        "medications": [med.model_dump() for med in medications],
    }


# ---------- Tool 2: search_protocols ----------

def search_protocols(query: str, max_results: int = 3) -> Dict[str, Any]:
    """
    Search demo hospital protocol documents stored in Cloud Storage.

    Args:
        query: Short natural language query, e.g. "heart failure" or "sepsis".
        max_results: Maximum number of matching protocol snippets to return.

    Returns:
        A dict with:
        - status: "success" or "error"
        - protocols: list of ProtocolSnippet dicts
    """
    bucket_name = os.getenv("WARDWISE_PROTOCOLS_BUCKET")
    if not bucket_name:
        return {
            "status": "error",
            "error_message": "WARDWISE_PROTOCOLS_BUCKET env var is not set.",
        }

    client = get_storage_client()

    # We expect objects under protocols/ in this bucket
    blobs = client.list_blobs(bucket_name, prefix="protocols/")

    lowercase_query = query.lower()
    matches: List[ProtocolSnippet] = []

    for blob in blobs:
        if len(matches) >= max_results:
            break

        try:
            # Our demo files are small text-based docs
            contents = blob.download_as_text()
        except Exception:
            # If something goes wrong, skip this blob
            continue

        if lowercase_query in contents.lower():
            snippet = contents[:400].replace("\n", " ")
            matches.append(
                ProtocolSnippet(
                    title=os.path.basename(blob.name),
                    snippet=snippet,
                    uri=f"gs://{bucket_name}/{blob.name}",
                )
            )

    return {
        "status": "success",
        "protocols": [p.model_dump() for p in matches],
    }


# ---------- Tool 3: log_event ----------

def log_event(
    event_type: str,
    user_id: Optional[str] = None,
    patient_id: Optional[str] = None,
    latency_ms: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Log a simple WardWise analytics event into BigQuery.

    Args:
        event_type: Short label, e.g. "summary_generated", "note_drafted".
        user_id: Optional logical user identifier, e.g. "dr-demo".
        patient_id: Optional patient identifier (demo only).
        latency_ms: Optional latency in milliseconds for the operation.

    Returns:
        A dict indicating success or error from BigQuery insertion.
    """
    dataset = os.getenv("WARDWISE_BQ_DATASET", "wardwise_analytics")
    table = os.getenv("WARDWISE_BQ_TABLE", "events")

    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        return {
            "status": "error",
            "error_message": "GOOGLE_CLOUD_PROJECT env var is not set.",
        }

    table_id = f"{project_id}.{dataset}.{table}"

    client = get_bigquery_client()
    now = datetime.now(timezone.utc)

    rows_to_insert = [
        {
            "event_time": now.isoformat(),
            "user_id": user_id or "unknown",
            "patient_id": patient_id or "",
            "event_type": event_type,
            "latency_ms": latency_ms or 0,
        }
    ]

    errors = client.insert_rows_json(table_id, rows_to_insert)
    if errors:
        return {
            "status": "error",
            "error_message": f"BigQuery insert errors: {errors}",
        }

    return {
        "status": "success",
        "table": table_id,
    }

def echo_tool(message: str) -> str:
    """Simple test tool: returns the message back and prints to logs."""
    print(f"[echo_tool] called with message={message!r}")
    return f"ECHO: {message}"