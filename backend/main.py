from datetime import date

import pandas as pd
from fastapi import FastAPI, Response

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
    from pathlib import Path

    from fastapi import HTTPException

    from pipeline import load_stage, run_pipeline

    try:
        import taxonomy  # backend/taxonomy.py, from the data worktree
    except ImportError:
        taxonomy = None  # pipeline falls back to an empty taxonomy: every vendor is unknown
    try:
        df, as_of = load_stage(req.stage, Path(__file__).parent / "data")
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    # classify_unknown: the llm worktree's batched Claude classifier plugs in here.
    return run_pipeline(
        df,
        as_of,
        req.config or DEFAULT_CONFIG,
        req.overrides,
        req.open_issues,
        taxonomy=taxonomy,
        classify_unknown=None,
        stage=req.stage,
    )


@app.post("/api/narrate", response_model=NarrateResponse)
def narrate(req: NarrateRequest, response: Response) -> NarrateResponse:
    # Imports kept local so this hunk touches nothing another worktree edits.
    import logging

    import anthropic

    from llm.client import BudgetExceededError, MissingAPIKeyError
    from llm.narrate import narrate_result, template_response

    try:
        result = narrate_result(req.findings, req.mode, open_issues=req.open_issues)
    except (anthropic.APIError, MissingAPIKeyError, BudgetExceededError) as e:
        logging.getLogger("cost_signals.llm").warning("narrate: %s: %s; serving templates", type(e).__name__, e)
        response.headers["X-Narration"] = "template"
        return template_response(req.findings, req.mode, req.open_issues)
    response.headers["X-Narration"] = result.source
    return result.response
