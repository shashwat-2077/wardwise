import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from production_agent.wardwise_tools import log_event


def main():
    result = log_event("summary_generated", patient_id="pat-001")
    print(result)


if __name__ == "__main__":
    main()