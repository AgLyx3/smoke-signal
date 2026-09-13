"""LLM layer tests. No network: every Claude call goes to `FakeClient`."""

from __future__ import annotations

import json
from typing import Any

import anthropic
import httpx
import pytest
from anthropic import types as at

from llm import client as llm_client
from llm import templates
from llm.classify import CATEGORIES, FALLBACK, TOOL_NAME, classify_unknown
from llm.facts import allowed_numbers, build_facts, extract_numbers, unsupported_numbers
from llm.narrate import ALERTS_TOOL_NAME, REPORT_TOOL_NAME, narrate, narrate_result, template_response
from models import Classification, NarrateResponse, OpenIssue, VendorFacts
from sample_findings import sample_findings

# ---------------------------------------------------------------- fakes


def tool_message(name: str, payload: dict[str, Any], stop_reason: str = "tool_use") -> at.Message:
    return at.Message(
        id="msg_fake",
        model=llm_client.MODEL,
        role="assistant",
        type="message",
        stop_reason=stop_reason,
        content=[at.ToolUseBlock(id="toolu_fake", type="tool_use", name=name, input=payload)],
        usage=at.Usage(input_tokens=1, output_tokens=1),
    )


def text_message(text: str) -> at.Message:
    return at.Message(
        id="msg_fake",
        model=llm_client.MODEL,
        role="assistant",
        type="message",
        stop_reason="end_turn",
        content=[at.TextBlock(type="text", text=text)],
        usage=at.Usage(input_tokens=1, output_tokens=1),
    )


class _FakeMessages:
    def __init__(self, responses: list[Any]):
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if not self.responses:
            raise AssertionError("fake client ran out of canned responses")
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


class FakeClient:
    def __init__(self, *responses: Any):
        self.messages = _FakeMessages(list(responses))

    @property
    def calls(self) -> list[dict[str, Any]]:
        return self.messages.calls


@pytest.fixture(autouse=True)
def _fresh_budget():
    llm_client.reset_budget()
    yield
    llm_client.reset_budget()


VENDORS = ["Pinecone", "Datadog", "Twilio", "NIMBLEWAY LTD", "Gusto"]


def vendor_facts() -> list[VendorFacts]:
    return [
        VendorFacts(
            vendor=v,
            monthly_amounts={"2026-06": 1000.0, "2026-07": 1100.0, "2026-08": 1250.0},
            cadence="monthly",
            charge_count=3,
            sample_descriptors=[f"{v.upper()}* 123"],
            sample_memos=[],
        )
        for v in VENDORS
    ]


def good_classification_payload() -> dict[str, Any]:
    rows = [
        ("Pinecone", "usage", "Data & tooling", "high"),
        ("Datadog", "usage", "Cloud & infra", "high"),
        ("Twilio", "usage", "Cloud & infra", "high"),
        ("NIMBLEWAY LTD", "fixed", "Fees & other", "low"),
        ("Gusto", "payroll", "People & payroll", "high"),
    ]
    return {
        "classifications": [
            {"vendor": v, "cost_type": t, "category": c, "confidence": conf} for v, t, c, conf in rows
        ]
    }


# ---------------------------------------------------------------- classify


def test_classify_batches_five_vendors_in_one_call_and_parses():
    fake = FakeClient(tool_message(TOOL_NAME, good_classification_payload()))
    out = classify_unknown(vendor_facts(), client=fake)
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["model"] == "claude-sonnet-5"
    assert call["tool_choice"] == {"type": "tool", "name": TOOL_NAME, "disable_parallel_tool_use": True}
    assert call["tools"][0]["strict"] is True
    for v in VENDORS:
        assert v in call["messages"][0]["content"]
    assert set(out) == set(VENDORS)
    assert out["Pinecone"] == Classification(cost_type="usage", category="Data & tooling", confidence="high")
    assert out["Gusto"].cost_type == "payroll"
    assert out["NIMBLEWAY LTD"].confidence == "low"
    assert llm_client.calls_made() == 1


def test_classify_system_prompt_states_taxonomy_and_categories():
    fake = FakeClient(tool_message(TOOL_NAME, good_classification_payload()))
    classify_unknown(vendor_facts(), client=fake)
    system = fake.calls[0]["system"]
    for t in ("usage", "fixed", "headcount", "annual", "payroll"):
        assert f"- {t}:" in system
    for c in CATEGORIES:
        assert c in system


def test_classify_invalid_entries_fall_back_per_vendor_without_raising():
    payload = good_classification_payload()
    payload["classifications"][1]["cost_type"] = "subscription"  # not in CostType
    payload["classifications"][2]["category"] = "Telephony"  # not in the list
    del payload["classifications"][3]  # NIMBLEWAY missing entirely
    fake = FakeClient(tool_message(TOOL_NAME, payload))
    out = classify_unknown(vendor_facts(), client=fake)
    assert out["Pinecone"].cost_type == "usage"
    assert out["Datadog"] == FALLBACK
    assert out["Twilio"] == FALLBACK
    assert out["NIMBLEWAY LTD"] == FALLBACK
    assert out["Gusto"].cost_type == "payroll"


def test_classify_whole_payload_invalid_falls_back_for_all():
    fake = FakeClient(tool_message(TOOL_NAME, {"classifications": "nope"}))
    out = classify_unknown(vendor_facts(), client=fake)
    assert all(c == FALLBACK for c in out.values()) and len(out) == 5


def test_classify_no_tool_block_falls_back():
    fake = FakeClient(text_message("I would rather not."))
    out = classify_unknown(vendor_facts(), client=fake)
    assert all(c == FALLBACK for c in out.values())


def test_classify_api_error_falls_back_without_raising():
    err = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    fake = FakeClient(err)
    out = classify_unknown(vendor_facts(), client=fake)
    assert all(c == FALLBACK for c in out.values())


def test_classify_missing_key_falls_back(monkeypatch):
    monkeypatch.delenv(llm_client.API_KEY_ENV, raising=False)
    out = classify_unknown(vendor_facts())  # no client injected -> get_client() -> MissingAPIKeyError
    assert all(c == FALLBACK for c in out.values())


def test_classify_empty_input_makes_no_call():
    fake = FakeClient()
    assert classify_unknown([], client=fake) == {}
    assert fake.calls == []


# ---------------------------------------------------------------- client / budget


def test_get_client_names_missing_env_var_without_value(monkeypatch):
    monkeypatch.delenv(llm_client.API_KEY_ENV, raising=False)
    with pytest.raises(llm_client.MissingAPIKeyError, match="ANTHROPIC_API_KEY"):
        llm_client.get_client()


def test_get_client_never_echoes_key(monkeypatch):
    monkeypatch.setenv(llm_client.API_KEY_ENV, "sk-test-not-a-real-key")
    c = llm_client.get_client()
    assert isinstance(c, anthropic.Anthropic)
    assert c.timeout == llm_client.TIMEOUT_S
    assert "sk-test-not-a-real-key" not in repr(c)


def test_budget_guard_raises_on_n_plus_one():
    fake = FakeClient(*[tool_message(TOOL_NAME, {"classifications": []}) for _ in range(25)])
    for _ in range(llm_client.MAX_CALLS_PER_PROCESS):
        llm_client.create_message(fake, messages=[])
    assert llm_client.calls_made() == llm_client.MAX_CALLS_PER_PROCESS
    with pytest.raises(llm_client.BudgetExceededError):
        llm_client.create_message(fake, messages=[])
    assert len(fake.calls) == llm_client.MAX_CALLS_PER_PROCESS


# ---------------------------------------------------------------- facts


def test_build_facts_from_sample():
    facts = build_facts(sample_findings())
    w = facts["window"]
    assert w["trailing_monthly_spend"] == 500_000.0
    assert w["prior_monthly_spend"] == 482_000.0
    assert w["change_vs_prior_month"] == 18_000.0
    assert w["change_vs_prior_month_pct"] == pytest.approx(3.73, abs=0.01)
    assert w["headcount_proxy_cardholders"] == 46
    by_id = {f["finding_id"]: f for f in facts["findings"]}
    a = by_id["anthropic-growth_break"]
    assert a["actual_monthly"] == 26_500.0
    assert a["expected_monthly"] == 16_500.0
    assert a["impact_monthly"] == 10_000.0
    assert a["impact_pct_of_spend"] == 2.0
    assert a["trend_growth_pct_per_month"] == 15.0
    assert a["above_expected_pct"] == pytest.approx(60.61, abs=0.01)
    assert a["drivers"] == [{"driver": "volume", "share_pct": 100.0}]
    assert a["confidence"] == "high" and a["n_obs"] == 6
    assert "cardholders" not in a
    p = by_id["pinecone-new_vendor"]
    assert p["ask_cost_type"] is True and p["cost_type_source"] == "llm"
    fig = by_id["figma-price_change"]
    assert fig["price_change_pct"] == 25.0 and fig["last_price"] == 1_500.0
    assert by_id["loom-stopped"]["impact_monthly"] == -480.0


def test_build_facts_marks_open_issue_vendors_ongoing():
    facts = build_facts(sample_findings(), [OpenIssue(id="x", vendor="Anthropic", kind="growth_break", impact_monthly=1)])
    by_id = {f["finding_id"]: f for f in facts["findings"]}
    assert by_id["anthropic-growth_break"]["ongoing_issue"] is True
    assert by_id["figma-price_change"]["ongoing_issue"] is False


# ---------------------------------------------------------------- grounding


def test_extract_numbers_handles_money_forms_and_percents():
    tokens = extract_numbers("+$10.0K/mo · 2.0% of spend; from $1,500 to $1,875.50 (25% up); -$480; 0.1%.")
    values = [(v, k) for _, v, _, k in tokens]
    assert (10_000.0, "money") in values
    assert (1_500.0, "money") in values
    assert (1_875.5, "money") in values
    assert (480.0, "money") in values
    assert (2.0, "pct") in values and (25.0, "pct") in values and (0.1, "pct") in values


def test_grounding_flags_unsupported_and_passes_supported():
    facts = build_facts(sample_findings())
    a = next(f for f in facts["findings"] if f["finding_id"] == "anthropic-growth_break")
    money_set, pct_set = allowed_numbers(a, {"window": facts["window"]})
    ok = "+$10.0K/mo · 2.0% of monthly spend — Anthropic billed $26,500 against $16,500, about 61% above its 15% trend."
    assert unsupported_numbers(ok, money_set, pct_set) == []
    bad = "Anthropic billed $12,345 this month, 7% of spend, up from $16,500."
    assert unsupported_numbers(bad, money_set, pct_set) == ["$12,345", "7%"]


def test_grounding_tolerance_is_rounding_not_slack():
    money_set, pct_set = {26_480.0}, {1.98}
    assert unsupported_numbers("$26.5K and 2.0%", money_set, pct_set) == []
    assert unsupported_numbers("$26,480 and 1.98%", money_set, pct_set) == []
    assert unsupported_numbers("$27.5K", money_set, pct_set) == ["$27.5K"]
    assert unsupported_numbers("2.5%", money_set, pct_set) == ["2.5%"]
    assert unsupported_numbers("$26,000", money_set, pct_set) == ["$26,000"]


def test_grounding_does_not_treat_other_items_numbers_as_supported():
    facts = build_facts(sample_findings())
    fig = next(f for f in facts["findings"] if f["finding_id"] == "figma-price_change")
    money_set, pct_set = allowed_numbers(fig, {"window": facts["window"]})
    assert unsupported_numbers("Figma is like Anthropic's $26,500 jump.", money_set, pct_set) == ["$26,500"]


# ---------------------------------------------------------------- templates


def test_templates_produce_grounded_text_for_every_kind():
    facts = build_facts(sample_findings())
    kinds_seen = set()
    for f in facts["findings"]:
        kinds_seen.add(f["kind"])
        money_set, pct_set = allowed_numbers(f, {"window": facts["window"]})
        a = templates.alert_text(f)
        for part in (a.headline, a.what_moved, a.why):
            assert part.strip()
            assert "!" not in part
            assert unsupported_numbers(part, money_set, pct_set) == [], (f["kind"], part)
        item = templates.report_item(f)
        assert item.text.strip()
        assert unsupported_numbers(item.text, money_set, pct_set) == [], (f["kind"], item.text)
    assert kinds_seen == {"growth_break", "new_vendor", "price_change", "stopped", "renewal"}
    # kinds the sample lacks
    for kind, extra in (("per_head", {"cost_per_head": 41.0}), ("spike", {})):
        f = {**facts["findings"][0], "kind": kind, "drivers": [{"driver": "who", "share_pct": 100.0}], "cardholders": ["A. Ng"], **extra}
        a = templates.alert_text(f)
        assert a.headline and a.what_moved and a.why
        assert "A. Ng" in a.why
        assert templates.report_item(f).text


def test_template_alert_headline_shape():
    facts = build_facts(sample_findings())
    a = templates.alert_text(facts["findings"][0])
    assert a.headline == "+$10.0K/mo · 2.0% of monthly spend — Anthropic is running well above its trend"
    assert "$26,500" in a.what_moved and "$16,500" in a.what_moved
    assert "volume 100.0%" in a.why and "Confidence high" in a.why and "inferred" in a.why
    assert "provider key" in a.why


def test_template_response_report_groups_and_sorts():
    resp = template_response(sample_findings(), "report")
    assert resp.alerts == [] and resp.report is not None
    r = resp.report
    assert "$500,000" in r.intro and "$482,000" in r.intro and "46" in r.intro
    assert [i.finding_id for i in r.needs_attention] == ["anthropic-growth_break", "pinecone-new_vendor"]
    assert list(r.worth_knowing) == ["Software"]
    assert [i.finding_id for i in r.worth_knowing["Software"]] == ["loom-stopped", "figma-price_change", "vanta-renewal"]
    assert "did not arrive" in r.worth_knowing["Software"][0].text


def test_template_response_report_puts_open_issue_vendor_under_needs_attention():
    fs = sample_findings()
    for f in fs.findings:
        f.route = "report"
    open_issues = [OpenIssue(id="i1", vendor="Anthropic", kind="growth_break", impact_monthly=10_000)]
    r = template_response(fs, "report", open_issues).report
    assert [i.finding_id for i in r.needs_attention] == ["anthropic-growth_break"]
    assert "still open" in r.needs_attention[0].text


# ---------------------------------------------------------------- narrate (alerts)


def alerts_payload(**override: dict[str, str]) -> dict[str, Any]:
    base = {
        "anthropic-growth_break": {
            "headline": "+$10.0K/mo · 2.0% of monthly spend — Anthropic is running well above its trend",
            "what_moved": "Anthropic billed $26,500 this month against $16,500 expected from its 15.0% monthly trend. That is $10,000 above trend.",
            "why": "Volume explains 100% of the move. Confidence high on 6 observations. Cost type usage is inferred. We can't see per-model usage without a provider key.",
        },
        "pinecone-new_vendor": {
            "headline": "+$6.5K/mo · 1.3% of monthly spend — Pinecone is now a recurring charge",
            "what_moved": "Pinecone charged $6,500 this month, its second regular charge.",
            "why": "A new recurring charge explains 100% of it. Confidence low. Cost type usage is inferred. We don't know the plan.",
        },
    }
    for k, v in override.items():
        base[k] = {**base[k], **v}
    return {"alerts": [{"finding_id": k, **v} for k, v in base.items()]}


def test_narrate_alerts_uses_claude_text_when_grounded():
    fake = FakeClient(tool_message(ALERTS_TOOL_NAME, alerts_payload()))
    result = narrate_result(sample_findings(), "alerts", client=fake)
    assert len(fake.calls) == 1
    assert result.source == "claude" and result.templated == []
    assert [a.finding_id for a in result.response.alerts] == ["anthropic-growth_break", "pinecone-new_vendor"]
    assert result.response.alerts[0].what_moved.startswith("Anthropic billed $26,500")
    assert result.response.report is None
    user_text = fake.calls[0]["messages"][0]["content"]
    facts_json = json.loads(user_text.split("Facts:\n", 1)[1])
    assert [f["finding_id"] for f in facts_json["findings"]] == ["anthropic-growth_break", "pinecone-new_vendor"]
    assert facts_json["findings"][0]["actual_monthly"] == 26_500.0
    system = fake.calls[0]["system"]
    assert "never recommend" in system and "inferred" in system and "%" in system


def test_narrate_alerts_regenerates_once_then_templates_unsupported_item():
    bad = alerts_payload(**{"anthropic-growth_break": {"what_moved": "Anthropic billed $12,345 this month."}})
    fake = FakeClient(tool_message(ALERTS_TOOL_NAME, bad), tool_message(ALERTS_TOOL_NAME, bad))
    result = narrate_result(sample_findings(), "alerts", client=fake)
    assert len(fake.calls) == 2
    assert "$12,345" in fake.calls[1]["messages"][0]["content"]
    assert result.source == "mixed" and result.templated == ["anthropic-growth_break"]
    a = result.response.alerts[0]
    assert a == templates.alert_text(build_facts(sample_findings())["findings"][0])
    assert result.response.alerts[1].headline.startswith("+$6.5K/mo")


def test_narrate_alerts_second_attempt_can_repair():
    bad = alerts_payload(**{"anthropic-growth_break": {"what_moved": "Anthropic billed $12,345 this month."}})
    fake = FakeClient(tool_message(ALERTS_TOOL_NAME, bad), tool_message(ALERTS_TOOL_NAME, alerts_payload()))
    result = narrate_result(sample_findings(), "alerts", client=fake)
    assert result.source == "claude" and len(fake.calls) == 2


def test_narrate_alerts_invalid_payload_templates_everything():
    fake = FakeClient(text_message("no"), text_message("still no"))
    result = narrate_result(sample_findings(), "alerts", client=fake)
    assert result.source == "template" and len(result.templated) == 2
    assert result.response == template_response(sample_findings(), "alerts")


def test_narrate_alerts_with_no_alert_findings_makes_no_call():
    fs = sample_findings()
    for f in fs.findings:
        f.route = "report"
    fake = FakeClient()
    assert narrate(fs, "alerts", client=fake) == NarrateResponse(alerts=[])
    assert fake.calls == []


def test_narrate_raises_api_errors_to_caller():
    err = anthropic.APITimeoutError(request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    with pytest.raises(anthropic.APIError):
        narrate(sample_findings(), "alerts", client=FakeClient(err))


def test_narrate_raises_missing_key(monkeypatch):
    monkeypatch.delenv(llm_client.API_KEY_ENV, raising=False)
    with pytest.raises(llm_client.MissingAPIKeyError):
        narrate(sample_findings(), "alerts")


# ---------------------------------------------------------------- narrate (report)


def report_payload(intro: str | None = None, **override: str) -> dict[str, Any]:
    texts = {
        "anthropic-growth_break": "Anthropic billed $26,500 against $16,500 expected, $10,000 above trend (2.0% of monthly spend); confidence high.",
        "pinecone-new_vendor": "Pinecone is now recurring at $6,500 a month (1.3% of monthly spend); confidence low, cost type inferred.",
        "figma-price_change": "Figma moved from $1,500 to $1,875, $375 a month more; confidence high.",
        "loom-stopped": "Loom's regular $480 charge did not arrive; confidence medium.",
        "vanta-renewal": "Vanta's annual renewal of $18,000 is coming up; no change to monthly spend.",
    }
    texts.update(override)
    return {
        "intro": intro
        or "Spend from 2026-03-01 to 2026-08-31. Trailing monthly spend is $500,000, up $18,000 (3.7%) from $482,000. 46 distinct cardholders is the headcount proxy.",
        "items": [{"finding_id": k, "text": v} for k, v in texts.items()],
    }


def test_narrate_report_groups_claude_text():
    fake = FakeClient(tool_message(REPORT_TOOL_NAME, report_payload()))
    result = narrate_result(sample_findings(), "report", client=fake)
    assert len(fake.calls) == 1 and result.source == "claude"
    r = result.response.report
    assert r.intro.startswith("Spend from 2026-03-01")
    assert [i.finding_id for i in r.needs_attention] == ["anthropic-growth_break", "pinecone-new_vendor"]
    assert [i.finding_id for i in r.worth_knowing["Software"]] == ["loom-stopped", "figma-price_change", "vanta-renewal"]
    assert r.worth_knowing["Software"][1].text.startswith("Figma moved from $1,500")


def test_narrate_report_templates_ungrounded_intro_and_item():
    p = report_payload(intro="Spend was $9,999,999 this month.", **{"loom-stopped": "Loom saved us $5,000."})
    fake = FakeClient(tool_message(REPORT_TOOL_NAME, p), tool_message(REPORT_TOOL_NAME, p))
    result = narrate_result(sample_findings(), "report", client=fake)
    assert len(fake.calls) == 2
    assert set(result.templated) == {"intro", "loom-stopped"} and result.source == "mixed"
    r = result.response.report
    assert "$500,000" in r.intro
    loom = r.worth_knowing["Software"][0]
    assert loom.finding_id == "loom-stopped" and "did not arrive" in loom.text
    assert r.needs_attention[0].text.startswith("Anthropic billed $26,500")


def test_narrate_report_passes_open_issues_into_facts_and_attention():
    fs = sample_findings()
    for f in fs.findings:
        f.route = "report"
    fake = FakeClient(tool_message(REPORT_TOOL_NAME, report_payload()))
    open_issues = [OpenIssue(id="i1", vendor="Pinecone", kind="new_vendor", impact_monthly=6_500)]
    result = narrate_result(fs, "report", client=fake, open_issues=open_issues)
    facts_json = json.loads(fake.calls[0]["messages"][0]["content"].split("Facts:\n", 1)[1])
    flags = {f["finding_id"]: f["ongoing_issue"] for f in facts_json["findings"]}
    assert flags["pinecone-new_vendor"] is True and flags["anthropic-growth_break"] is False
    assert [i.finding_id for i in result.response.report.needs_attention] == ["pinecone-new_vendor"]


# ---------------------------------------------------------------- route


def test_narrate_route_serves_template_with_header_when_key_missing(monkeypatch):
    from fastapi.testclient import TestClient

    import main

    monkeypatch.delenv(llm_client.API_KEY_ENV, raising=False)
    body = {"findings": sample_findings().model_dump(mode="json"), "mode": "alerts"}
    res = TestClient(main.app).post("/api/narrate", json=body)
    assert res.status_code == 200
    assert res.headers["x-narration"] == "template"
    assert res.json() == template_response(sample_findings(), "alerts").model_dump(mode="json")


def test_narrate_route_reports_claude_header_on_success(monkeypatch):
    from fastapi.testclient import TestClient

    import main
    from llm import narrate as narrate_mod

    fake = FakeClient(tool_message(ALERTS_TOOL_NAME, alerts_payload()))
    monkeypatch.setattr(narrate_mod, "get_client", lambda: fake)
    body = {"findings": sample_findings().model_dump(mode="json"), "mode": "alerts"}
    res = TestClient(main.app).post("/api/narrate", json=body)
    assert res.status_code == 200
    assert res.headers["x-narration"] == "claude"
    assert res.json()["alerts"][0]["what_moved"].startswith("Anthropic billed $26,500")


def test_narrate_route_serves_template_when_api_errors(monkeypatch):
    from fastapi.testclient import TestClient

    import main
    from llm import narrate as narrate_mod

    err = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    monkeypatch.setattr(narrate_mod, "get_client", lambda: FakeClient(err))
    body = {"findings": sample_findings().model_dump(mode="json"), "mode": "report"}
    res = TestClient(main.app).post("/api/narrate", json=body)
    assert res.status_code == 200
    assert res.headers["x-narration"] == "template"
    assert res.json()["report"]["needs_attention"][0]["finding_id"] == "anthropic-growth_break"
