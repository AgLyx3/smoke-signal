import sys
from pathlib import Path

# `main.py` and the packages import flat from backend/, so tests do too.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
