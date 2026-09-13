"""The records endpoint serves the raw Rho-shaped rows the pipeline reads, filtered and paged."""

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_records_default_page_is_newest_first_and_raw_shape():
    r = client.get("/api/transactions", params={"stage": "history"})
    assert r.status_code == 200
    body = r.json()
    assert body["stage"] == "history" and body["as_of"] == "2026-08-31"
    assert body["total"] == 2484 and body["matched"] == 2484 and len(body["transactions"]) == 100
    assert body["by_beat"] == {"history": 2484}
    first = body["transactions"][0]
    assert first["_beat"] == "history"
    assert {"id", "amount", "counterparty_name", "transaction_type", "status", "initiated_at"} <= set(first)
    assert isinstance(first["amount"], dict) and isinstance(first["amount"]["amount"], int)  # raw minor units, untouched
    dates = [t["initiated_at"] for t in body["transactions"]]
    assert dates == sorted(dates, reverse=True)


def test_records_filter_by_query_and_type_and_paging():
    r = client.get("/api/transactions", params={"stage": "inject-2", "q": "anthropic", "type": "ach_debit", "limit": 2})
    body = r.json()
    assert body["total"] == 2484 + 51 + 181
    assert body["matched"] == 4 and len(body["transactions"]) == 2  # 4 ACH invoices; the other 6 Anthropic rows are card
    assert all("anthropic" in t["counterparty_name"].lower() and t["transaction_type"] == "ach_debit" for t in body["transactions"])
    page2 = client.get("/api/transactions", params={"stage": "inject-2", "q": "anthropic", "type": "ach_debit", "limit": 2, "offset": 2}).json()
    assert len(page2["transactions"]) == 2 and {t["id"] for t in page2["transactions"]}.isdisjoint({t["id"] for t in body["transactions"]})
    assert client.get("/api/transactions", params={"stage": "inject-2", "q": "anthropic"}).json()["matched"] == 10


def test_records_beat_filter_shows_what_a_step_added():
    body = client.get("/api/transactions", params={"stage": "inject-2", "beat": "inject-1", "limit": 500}).json()
    assert body["by_beat"] == {"history": 2484, "inject-1": 51, "inject-2": 181}
    assert body["matched"] == 51 and all(t["_beat"] == "inject-1" for t in body["transactions"])
    assert all(t["initiated_at"] >= "2026-09-01" for t in body["transactions"])
    assert any("anthropic" in t["counterparty_name"].lower() for t in body["transactions"])  # the Sep 2 invoice arrives in this beat


def test_records_filter_by_account_and_accounts_snapshot():
    body = client.get("/api/transactions", params={"stage": "history", "account": "checking", "limit": 3}).json()
    assert body["matched"] > 100 and all(t["account_type"] == "checking" for t in body["transactions"])
    acct = client.get("/api/accounts", params={"stage": "inject-2"}).json()
    assert acct["as_of"] == "2026-09-30"
    by_type = {a["account_type"]: a["balance"]["amount"] for a in acct["accounts"]}
    assert by_type["checking"] == 190_500_000 and by_type["investment"] == 742_300_000 and by_type["credit"] < 0


def test_records_reject_bad_stage_and_cap_limit():
    assert client.get("/api/transactions", params={"stage": "nope"}).status_code == 422
    body = client.get("/api/transactions", params={"stage": "history", "limit": 5000}).json()
    assert len(body["transactions"]) == 500
