import json
import sys
from pathlib import Path

# Make sure Python can find the production_agent package
sys.path.append(str(Path(__file__).parent.parent))

from production_agent.wardwise_tools import get_patient_snapshot


def main():
    patient_id = "pat-001"
    snapshot = get_patient_snapshot(patient_id)
    print(json.dumps(snapshot, indent=2, default=str))


if __name__ == "__main__":
    main()