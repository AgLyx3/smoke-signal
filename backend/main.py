from datetime import date

import pandas as pd
from fastapi import FastAPI

from models import (
    DEFAULT_CONFIG,
    Config,
    Findings,
    NarrateRequest,
    NarrateResponse,
    RunRequest,
)

# Vercel Services does not strip the /api prefix, so every route carries it.
app = FastAPI(title="Cost Signals API", version="0.1.0")


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "pandas": pd.__version__}


@app.get("/api/config/default", response_model=Config)
def default_config() -> Config:
    return DEFAULT_CONFIG


@app.post("/api/run", response_model=Findings)
def run(req: RunRequest) -> Findings:
    # Scaffold stub; the pipeline worktree replaces this.
    return Findings(
        stage=req.stage,
        window_start=date(2026, 3, 1),
        window_end=date(2026, 8, 31),
        trailing_monthly_spend=0.0,
        headcount_proxy=0,
        findings=[],
        vendors=[],
        category_totals={},
    )


@app.post("/api/narrate", response_model=NarrateResponse)
def narrate(req: NarrateRequest) -> NarrateResponse:
    # Scaffold stub; the llm worktree replaces this.
    return NarrateResponse()
