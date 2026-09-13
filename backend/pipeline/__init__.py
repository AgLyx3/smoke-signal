"""Deterministic detection pipeline: pure functions over pandas. Stats detect; the LLM narrates."""

from pipeline.load import load_stage
from pipeline.run import run_pipeline

__all__ = ["load_stage", "run_pipeline"]
