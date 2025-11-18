from datetime import datetime, timedelta, timezone

from google.cloud import firestore


def main():
    db = firestore.Client()

    # --- 1) Patient: pat-001 ---
    patient_id = "pat-001"

    admitted_at = datetime.now(timezone.utc) - timedelta(days=2)

    db.collection("patients").document(patient_id).set(
        {
            "name": "John Doe",
            "dob": "1960-01-01",
            "gender": "male",
            "primary_diag": "Acute decompensated heart failure",
            "ward": "Cardiology",
            "bed_number": "B12",
            "admitted_at": admitted_at,
        }
    )

    # --- 2) Observations (labs/vitals) ---
    # We'll create a few recent observations for this patient.
    now = datetime.now(timezone.utc)

    observations = [
        {
            "patient_id": patient_id,
            "label": "Blood Pressure",
            "code": "BP",
            "value": "150/90",
            "unit": "mmHg",
            "recorded_at": now - timedelta(hours=1),
        },
        {
            "patient_id": patient_id,
            "label": "Heart Rate",
            "code": "HR",
            "value": "96",
            "unit": "bpm",
            "recorded_at": now - timedelta(hours=1),
        },
        {
            "patient_id": patient_id,
            "label": "Serum Creatinine",
            "code": "CREAT",
            "value": "1.8",
            "unit": "mg/dL",
            "recorded_at": now - timedelta(hours=2),
        },
        {
            "patient_id": patient_id,
            "label": "Serum Creatinine",
            "code": "CREAT",
            "value": "1.2",
            "unit": "mg/dL",
            "recorded_at": now - timedelta(days=1),
        },
    ]

    for obs in observations:
        db.collection("observations").add(obs)

    # --- 3) Medications ---
    meds = [
        {
            "patient_id": patient_id,
            "name": "Furosemide",
            "dose": "40 mg IV BD",
            "route": "IV",
            "start_time": admitted_at,
            "end_time": None,
        },
        {
            "patient_id": patient_id,
            "name": "Ramipril",
            "dose": "5 mg OD",
            "route": "PO",
            "start_time": admitted_at - timedelta(days=1),
            "end_time": None,
        },
    ]

    for med in meds:
        db.collection("medications").add(med)

    print("Seeded demo data for patient pat-001.")


if __name__ == "__main__":
    main()