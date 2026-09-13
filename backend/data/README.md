# Lumen Labs synthetic transactions

Synthetic Rho-schema transactions for the demo company (Series A AI product company, headcount
38 → 46, ~$500K/mo by mid-2026, ~65 % payroll). Two accounts: **Operating Checking** (ACH,
wires, treasury) and **Rho Card** (credit; card transactions). All data is invented.

## Files and stages

| File | Window | Stage semantics |
|---|---|---|
| `history.json` | 2025-09-01 → 2026-08-31 | `history`: what the pipeline sees as of 2026-08-31 |
| `inject-1.json` | 2026-09-01 → 2026-09-05 | `inject-1`: history **+ inject-1**, as of 2026-09-05 (the alerts step) |
| `inject-2.json` | 2026-09-06 → 2026-09-30 | `inject-2`: **all three files**, as of 2026-09-30 (the monthly report step) |

Each file is Rho's list envelope `{"transactions": [...]}`, rows sorted by `initiated_at`. The
three files are one continuous generated period split by `initiated_at`, so a stage is simply the
concatenation of its files. Pending rows (last two days of each window) are never re-emitted as
settled in a later file; the pipeline counts `settled` only.

`accounts.json` (hand-written, not generated) holds one balance snapshot per stage in Rho's
`/accounts` shape (minor units): Operating Checking, Rho Treasury (`investment`) and the card
balance. The cash position and runway framing read it; without it the pipeline simply omits them.

## Regenerate

```
cd backend
uv run python -m data.generate        # rewrites the three JSON files, byte-identical
uv run pytest tests/test_data.py      # reproducibility, planted numbers, schema sanity
```

Everything comes from one `random.Random(20260912)`; the test suite regenerates into a temp dir
and asserts byte equality with the committed files. Change the generator → regenerate → commit
the JSON in the same change.

## Shape

Rows carry the sandbox's 16 fields plus the spec-only optional ones (`memo`, `note`,
`counterparty_logo_url`, `tracking_number`, `lines`). Amounts are signed integers in cents,
debits negative. `posted_at` is null iff `status == "pending"`. Card rows have `card_id`,
`card_name` ("Eng — Priya Natarajan", or a purpose-named virtual card such as
"Eng — API & Infra") and the cardholder; ACH debits pulled by vendors, payroll, repayments and
rewards are system-initiated (`user_id` null). Wires and treasury sweeps are initiated by the
finance lead.

Vendor descriptors vary the way real card and ACH feeds do ("ANTHROPIC* API" / "Anthropic PBC" /
"ANTHROPIC PBC SAN FRANCISCO CA"; "AMAZON WEB SERVICES" / "AWS EMEA"; "GUSTO PAYROLL" / "GUSTO").
Every variant of a taxonomy vendor is an alias in `taxonomy.py`. Everything the taxonomy does not
resolve is an unknown vendor for the LLM classifier: Pinecone, four small recurring tools
(`KNOWN_UNKNOWN`), and ~25 employee-card merchants (coffee, lunch, Amazon, hotels, conferences),
each well under $2K/mo.

## Planted scenarios

Trailing monthly spend is ≈ $485K in Aug 2026 (payroll ≈ $325K), so the default 1 % materiality
line is ≈ $4.9K/mo.

| Scenario | Vendor / rows | Exact dates and amounts | Intended pipeline outcome |
|---|---|---|---|
| Growth break | Anthropic (usage, ~15 %/mo since Dec 2025) | Aug 2026-08-02 **$21,625.54**; Sep 2026-09-02 **$34,600.86** = 1.60× Aug (trend ≈ 1.15× → ≈ $24.9K; impact ≈ +$9.7K ≈ 2 % of spend) | **Alert** in inject-1; ongoing (no re-alert) in inject-2 |
| New vendor | Pinecone, "PINECONE SYSTEMS INC" (not in taxonomy) | 2026-08-04 **$2,487.30**; 2026-09-03 **$6,512.80** (card, Eng — API & Infra) | **Alert + ask cost type** in inject-1 (second regular charge, impact ≈ 1.3 % of spend); ongoing in inject-2 |
| Price creep | Figma (fixed), 22 seats | $990.00/mo on the 1st through 2026-08-01; 2026-09-01 **$1,210.00** ($45 → $55/seat, +22.2 %; impact +$220/mo) | **Report** (price change always listed); below materiality |
| Seats outgrow headcount | Notion (headcount), $16/seat on the 2nd | seats 40 (Sep 2025 – Jun 2026) → **46 Jul, 52 Aug, 58 Sep** ($640 → $736 → $832 → $928); headcount 38 → 46 | **Report** (per-head 16.8 → 20.2 $/head, +20 %) |
| Stopped vendor | Loom (fixed), $1,440.00 on the 6th | 11 charges 2025-09-06 … **2026-07-06**; nothing in Aug or Sep | **Report** (overdue by cadence + grace) |
| Renewal coming up | Vanta (annual) | one charge **2025-10-12, $18,000.00** (ACH); renewal due ≈ 2026-10-12 | **Report** renewal notice in inject-2; never alerts |
| Other annuals | Carta 2026-02-10 $9,200.00; Vouch Insurance 2026-01-15 $14,400.00 (both ACH) | one charge each | Ignore (annual; not due) |
| One-off spike | Offsite, Rachel Stern's card | 2026-04-13 … 04-16: Airbnb $9,800, United 4 × ≈ $2.1K, four restaurants ≈ $9.8K; **$28,362 total**, never repeats | Ignore (spike; context only) |
| Hiring wave | 8 hires 2026-06-01 … 06-20; cardholders 34 → 42 | payroll steps May $269K → Jun $306K → Jul $328K; seat tools step up in Jun/Jul with flat per-seat price | Ignore (headcount-driven, per-head flat) |
| Usage vendors on trend | OpenAI 8 %, AWS 6 %, Modal 10 %, Vercel 4 %, Twilio 3 %, Datadog 5 %, Fireworks 6 %, Google Ads 2 %, PostHog 4 % per month; ±3 % noise (±1.5 % in Sep) | Aug ≈ $8.9K / $37.2K / $4.6K / $2.3K / $1.8K / $4.2K / $0.9K / $8.2K / $0.6K | Ignore |
| Fixed vendors at price | Zoom, Webflow, Ashby, HubSpot, Apollo, LinkedIn, Cloudflare, Supabase, Sentry, WeWork $23,850, Deel $20,500, Pilot $2,500 | identical every month | Ignore |
| Payroll | Gusto, semi-monthly ACH on the 15th and last day (net pay "GUSTO PAYROLL" + taxes "GUSTO"), $6,900/head/mo in 2025, $7,100 from Jan 2026; Gusto fee $40 + $6/head on the 3rd | Aug 2026 ≈ $325K | Context only |
| Legal | Cooley LLP, wire_out + $25 wire_fee (shared `money_movement_id`) | 2025-10-28 $9,850; 2026-01-27 $14,320; 2026-04-29 $8,460; 2026-07-28 $11,740 | Irregular cadence; ignore |

Nothing in inject-2 should alert. Its only report items are the ones above (Loom missing, Notion
per-head, Figma price, Vanta renewal) plus the ongoing Anthropic and Pinecone issues. There are no
prepaid credit purchases anywhere.

## Noise the pipeline must exclude

Monthly `credit_repayment` on the Rho Card (positive) paired with an `internal_transfer` on
checking (negative, same `money_movement_id`) on the 5th; monthly `rewards_accrual` (positive,
1.25 % of card spend); two `treasury_deposit` sweeps ($1.5M 2025-10-20, $750K 2026-04-02); three
customer inflows (`wire_in` $120K 2025-12-18, `ach_credit` $45K 2026-03-27, `wire_in` $200K
2026-07-15); three `card_refund`s (United $420, Amazon $89.40, DoorDash $34.10) that net against
their merchant; three `failed` card declines (2025-12-04, 2026-05-19, 2026-09-18); 3–4 `pending`
swipes in the last two days of each file.
