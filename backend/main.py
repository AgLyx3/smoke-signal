import logging
from pathlib import Path

import anthropic
import pandas as pd
from fastapi import FastAPI, HTTPException, Response

import taxonomy
from llm.ask import answer_question
from llm.classify import classify_unknown
from llm.client import BudgetExceededError, MissingAPIKeyError
from llm.narrate import narrate_result, template_response
from models import (
    DEFAULT_CONFIG,
    AskRequest,
    AskResponse,
    Config,
    Findings,
    NarrateRequest,
    NarrateResponse,
    RunRequest,
)
from pipeline import load_stage, run_pipeline
from pipeline.evidence import build_evidence, prepare_spend

log = logging.getLogger("cost_signals")
DATA_DIR = Path(__file__).parent / "data"

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
    try:
        df, as_of = load_stage(req.stage, DATA_DIR)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    # Stats decide everything; Claude only labels vendors the taxonomy does not know, and the
    # hook returns {} on any failure so those vendors stay at their default and still get asked.
    return run_pipeline(
        df,
        as_of,
        req.config or DEFAULT_CONFIG,
        req.overrides,
        req.open_issues,
        taxonomy=taxonomy,
        classify_unknown=classify_unknown,
        stage=req.stage,
    )


@app.post("/api/narrate", response_model=NarrateResponse)
def narrate(req: NarrateRequest, response: Response) -> NarrateResponse:
    try:
        result = narrate_result(req.findings, req.mode, open_issues=req.open_issues)
    except (anthropic.APIError, MissingAPIKeyError, BudgetExceededError) as e:
        log.warning("narrate: %s: %s; serving templates", type(e).__name__, e)
        response.headers["X-Narration"] = "template"
        return template_response(req.findings, req.mode, req.open_issues)
    response.headers["X-Narration"] = result.source
    return result.response


@app.post("/api/ask", response_model=AskResponse)
def ask(req: AskRequest, response: Response) -> AskResponse:
    """A clarifying question under one finding, answered from that finding's evidence pack."""
    try:
        df, as_of = load_stage(req.stage, DATA_DIR)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    config = req.config or DEFAULT_CONFIG
    findings = run_pipeline(
        df, as_of, config, req.overrides, req.open_issues, taxonomy=taxonomy, classify_unknown=classify_unknown, stage=req.stage
    )
    finding = next((f for f in findings.findings if f.id == req.finding_id), None)
    if finding is None:
        raise HTTPException(status_code=404, detail=f"finding {req.finding_id!r} is not produced at the current settings")
    evidence = build_evidence(prepare_spend(df, as_of, taxonomy), findings, finding, config, as_of)
    result = answer_question(evidence, req.question, req.thread)
    response.headers["X-Narration"] = result.source
    used = [k for k in ("vendor_monthly_series", "charges_evaluated_month", "charges_prior_month", "cardholder_totals_evaluated_month") if evidence.get(k)]
    return AskResponse(answer=result.answer, source=result.source, evidence_used=used)
