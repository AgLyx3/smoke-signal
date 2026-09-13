import sys
from pathlib import Path

# main.py and the pipeline import `models` from backend/, so tests run with backend/ importable.
BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
