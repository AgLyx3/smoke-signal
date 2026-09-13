"""Thread answers: the evidence pack holds only this vendor's data, and the answer is grounded
in it or falls back to the template."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import anthropic.types as at
import httpx
import anthropic

import taxonomy
from llm import client as llm_client
from llm.ask import TOOL_NAME, allowed_from_evidence, answer_question, template_answer
from models import DEFAULT_CONFIG, AskTurn
from pipeline import load_stage, run_pipeline
from pipeline.evidence import build_evidence, prepare_spend

DATA = Path(__file__).resolve().parents[1] / "data"


def _tool_message(payload: dict[str, Any]) -> at.Message:
    return at.Message(
        id="msg_test",
        type="message",
        role="assistant",
        model="claude-sonnet-5",
        content=[at.ToolUseBlock(type="tool_use", id="tu_1", name=TOOL_NAME, input=payload)],
        stop_reason="tool_use",
        stop_sequence=None,
        usage=at.Usage(input_tokens=1, output_tokens=1),
    )


class FakeMessages:
    def __init__(self, *responses: Any) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        assert self.responses, "fake client ran out of canned responses"
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


class FakeClient:
    def __init__(self, *responses: Any) -> None:
        self.messages = FakeMessages(*responses)


def _anthropic_evidence():
    llm_client.reset_budget()
    df, as_of = load_stage("inject-1", DATA)
    findings = run_pipeline(df, as_of, DEFAULT_CONFIG, [], [], taxonomy=taxonomy, stage="inject-1")
    finding = next(f for f in findings.findings if f.vendor == "Anthropic")
    return build_evidence(prepare_spend(df, as_of, taxonomy), findings, finding, DEFAULT_CONFIG, as_of), finding


def test_evidence_pack_holds_only_this_vendor_and_the_right_months():
    ev, finding = _anthropic_evidence()
    assert ev["finding"]["finding_id"] == finding.id
    assert ev["reporting"]["evaluated_month"] == "2026-09"
    assert [m["month"] for m in ev["vendor_monthly_series"]][-2:] == ["2026-08", "2026-09"]
    sep = ev["charges_evaluated_month"]
    aug = ev["charges_prior_month"]
    assert len(sep) == 1 and sep[0]["amount"] == 34600.86 and sep[0]["date"] == "2026-09-02"
    assert len(aug) == 1 and aug[0]["amount"] == 21625.54
    assert all("anthropic" in c["descriptor"].lower() for c in sep + aug)
    assert ev["thresholds"]["alert_pct_of_monthly_spend"] == 1.0
    assert ev["thresholds"]["alert_dollars_per_month"] > 4000
    assert any("provider key" in s for s in ev["not_visible"])


def test_evidence_pack_lists_cardholders_for_card_vendors():
    llm_client.reset_budget()
    df, as_of = load_stage("inject-1", DATA)
    findings = run_pipeline(df, as_of, DEFAULT_CONFIG, [], [], taxonomy=taxonomy, stage="inject-1")
    finding = next(f for f in findings.findings if f.vendor == "Pinecone Systems")
    ev = build_evidence(prepare_spend(df, as_of, taxonomy), findings, finding, DEFAULT_CONFIG, as_of)
    holders = ev["cardholder_totals_evaluated_month"]
    assert len(holders) == 1 and abs(next(iter(holders.values())) - 6512.80) < 0.01
    assert ev["charges_evaluated_month"][0]["cardholder"] == next(iter(holders))


def test_grounded_answer_is_returned_as_is():
    ev, _ = _anthropic_evidence()
    fake = FakeClient(_tool_message({"answer": "Anthropic billed $34,600.86 on 2026-09-02 against $25,022.39 expected."}))
    r = answer_question(ev, "why?", [], client=fake)
    assert r.source == "claude" and r.answer.startswith("Anthropic billed $34,600.86")
    assert len(fake.messages.calls) == 1
    assert "Evidence pack" in fake.messages.calls[0]["messages"][0]["content"]


def test_ungrounded_answer_regenerates_once_then_templates():
    ev, _ = _anthropic_evidence()
    fake = FakeClient(
        _tool_message({"answer": "Anthropic will cost $99,999 next month, 88% more."}),
        _tool_message({"answer": "Roughly $123,456 in total."}),
    )
    r = answer_question(ev, "how much?", [], client=fake)
    assert r.source == "template" and "Anthropic" in r.answer and "$34,600.86" in r.answer
    assert len(fake.messages.calls) == 2
    assert "not in the evidence pack" in fake.messages.calls[1]["messages"][0]["content"]


def test_thread_history_is_passed_and_api_errors_fall_back():
    ev, _ = _anthropic_evidence()
    err = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    fake = FakeClient(err)
    r = answer_question(ev, "and who?", [AskTurn(role="user", text="why?"), AskTurn(role="bot", text="Because.")], client=fake)
    assert r.source == "template"
    assert "Thread so far:\nuser: why?\nbot: Because." in fake.messages.calls[0]["messages"][0]["content"]


def test_template_answer_quotes_only_evidence_numbers():
    ev, _ = _anthropic_evidence()
    money_set, pct_set = allowed_from_evidence(ev)
    from llm.facts import unsupported_numbers

    assert unsupported_numbers(template_answer(ev, "anything"), money_set, pct_set) == []
