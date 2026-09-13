"""Deterministic generator for the Lumen Labs demo dataset.

    cd backend && uv run python -m data.generate

Writes history.json (2025-09-01 → 2026-08-31), inject-1.json (2026-09-01 → 2026-09-05) and
inject-2.json (2026-09-06 → 2026-09-30) next to this file, each in Rho's list envelope
`{"transactions": [...]}`. One `random.Random(SEED)` drives every draw, including uuids, so the
output is byte-for-byte reproducible; the test suite regenerates and compares.

The whole period is generated in one pass and split by `initiated_at`, so every vendor series
is continuous across the three stages. Planted scenarios are listed in README.md."""

from __future__ import annotations

import calendar
import json
import random
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

SEED = 20260912
OUT_DIR = Path(__file__).resolve().parent

PERIOD_START = date(2025, 9, 1)
PERIOD_END = date(2026, 9, 30)
STAGES: dict[str, tuple[date, date]] = {
    "history": (date(2025, 9, 1), date(2026, 8, 31)),
    "inject-1": (date(2026, 9, 1), date(2026, 9, 5)),
    "inject-2": (date(2026, 9, 6), date(2026, 9, 30)),
}

CHECKING = {"name": "Operating Checking", "type": "checking"}
CARD = {"name": "Rho Card", "type": "credit"}

# Planted numbers (dollars unless noted). The tests assert these.
ANTHROPIC_AUG_USD = 22_000
ANTHROPIC_GROWTH = 1.15
ANTHROPIC_SEP_MULTIPLIER = 1.60
PINECONE_AUG_USD = 2_487.30
PINECONE_SEP_USD = 6_512.80
PINECONE_DATES = (date(2026, 8, 4), date(2026, 9, 3))
FIGMA_SEATS = 22
FIGMA_PRICE_OLD = 45.00
FIGMA_PRICE_NEW = 55.00
FIGMA_PRICE_CHANGE_FROM = date(2026, 9, 1)
NOTION_PRICE = 16.00
NOTION_SEATS = {(2026, 7): 46, (2026, 8): 52, (2026, 9): 58}  # 40 before July
NOTION_SEATS_BASE = 40
LOOM_USD = 1_440.00
LOOM_LAST_CHARGE = date(2026, 7, 6)
VANTA = (date(2025, 10, 12), 18_000.00)
CARTA = (date(2026, 2, 10), 9_200.00)
VOUCH = (date(2026, 1, 15), 14_400.00)
OFFSITE_DAYS = (date(2026, 4, 13), date(2026, 4, 16))
USAGE_NOISE_HISTORY = 0.03
USAGE_NOISE_INJECT = 0.015

HEADCOUNT_BASE = 38
NON_CARDHOLDERS = 4
PAYROLL_PER_HEAD_2025 = 6_900.00
PAYROLL_PER_HEAD_2026 = 7_100.00
NET_PAY_SHARE = 0.72


@dataclass(frozen=True)
class Person:
    name: str
    team: str
    start: date | None  # None = employed before the period
    user_id: str
    card_id: str

    @property
    def card_name(self) -> str:
        return f"{self.team} — {self.name}"

    def swipes_from(self) -> date:
        return PERIOD_START if self.start is None else self.start + timedelta(days=self._ramp_days)

    @property
    def _ramp_days(self) -> int:
        return 7 + (sum(map(ord, self.name)) % 15)  # 1–3 weeks, stable per person


ORIGINAL_STAFF: list[tuple[str, str]] = [
    ("Priya Natarajan", "Eng"), ("Marcus Chen", "Eng"), ("Elena Petrova", "Eng"), ("Daniel Okafor", "Eng"),
    ("Sofia Reyes", "Eng"), ("Tomasz Nowak", "Eng"), ("Aisha Rahman", "Eng"), ("Kenji Watanabe", "Eng"),
    ("Laura Bianchi", "Eng"), ("Samuel Adeyemi", "Eng"), ("Hannah Goldberg", "Eng"), ("Rafael Souza", "Eng"),
    ("Mei Lin", "Eng"), ("Owen Fitzgerald", "Eng"), ("Zara Hussain", "Eng"), ("Victor Ng", "Eng"),
    ("Olivia Brennan", "GTM"), ("Nathan Cole", "GTM"), ("Isabella Moreno", "GTM"), ("Ethan Park", "GTM"),
    ("Grace Kim", "GTM"), ("Liam O'Connor", "GTM"), ("Maya Patel", "GTM"), ("Julian Weber", "GTM"),
    ("Nora Haddad", "GTM"), ("Caleb Turner", "GTM"),
    ("Rachel Stern", "Ops"), ("David Osei", "Ops"), ("Emily Tran", "Ops"), ("Lucas Ferreira", "Ops"),
    ("Fatima Al-Sayed", "Ops"), ("Benjamin Hart", "Ops"), ("Yuki Tanaka", "Ops"), ("Camila Rojas", "Ops"),
]
JUNE_HIRES: list[tuple[str, str, date]] = [
    ("Ingrid Larsen", "Eng", date(2026, 6, 1)),
    ("Amara Diallo", "GTM", date(2026, 6, 1)),
    ("Jamal Whitfield", "Eng", date(2026, 6, 8)),
    ("Sebastian Ruiz", "GTM", date(2026, 6, 8)),
    ("Chloe Dubois", "Eng", date(2026, 6, 15)),
    ("Arjun Mehta", "Eng", date(2026, 6, 15)),
    ("Andrew Blake", "Ops", date(2026, 6, 20)),
    ("Leila Nasser", "Ops", date(2026, 6, 20)),
]
assert len(ORIGINAL_STAFF) == HEADCOUNT_BASE - NON_CARDHOLDERS
FINANCE_LEAD = "Rachel Stern"
ENG_LEAD = "Marcus Chen"
GTM_LEAD = "Olivia Brennan"

# Employee card merchants (all unknown to the taxonomy except the travel/rideshare ones).
# (descriptor, min $, max $, weight)
COMMON_MERCHANTS = [
    ("UBER *TRIP", 12, 65, 6), ("LYFT *RIDE", 10, 55, 4), ("DOORDASH*ORDER", 18, 70, 4),
    ("SWEETGREEN", 13, 24, 4), ("BLUE BOTTLE COFFEE", 5, 18, 3), ("CHIPOTLE 1234", 11, 22, 3),
    ("STARBUCKS STORE 05421", 4, 14, 3), ("PHILZ COFFEE", 5, 16, 2), ("AMZN MKTP US", 12, 240, 3),
    ("STAPLES", 20, 160, 1), ("SHAKE SHACK", 12, 30, 1),
]
TEAM_MERCHANTS = {
    "Eng": [("JETBRAINS", 8.90, 24.90, 2), ("O'REILLY MEDIA", 49, 49, 1), ("UDEMY", 12.99, 19.99, 1),
            ("APPLE.COM/US", 29, 199, 1), ("NAMECHEAP", 9, 40, 1)],
    "GTM": [("UNITED 0162345678901", 220, 680, 2), ("DELTA AIR 0062345678901", 200, 650, 1),
            ("MARRIOTT", 180, 420, 1), ("HILTON HOTELS", 160, 380, 1), ("EVENTBRITE", 45, 650, 1)],
    "Ops": [("FEDEX OFFICE", 15, 120, 2), ("USPS PO", 8, 60, 1), ("INSTACART", 60, 240, 2),
            ("COSTCO WHSE", 80, 350, 1), ("THE HOME DEPOT", 20, 180, 1)],
}

# Usage vendors: (vendor key, August-2026 anchor $, monthly growth, charge day, tx type, descriptors,
#                 first charge month (year, month), card)
# Descriptors rotate through the list in blocks so several variants appear per vendor.
USAGE_VENDORS = [
    ("anthropic", ANTHROPIC_AUG_USD, ANTHROPIC_GROWTH, 2, ["card_debit", "card_debit", "ach_debit", "ach_debit"],
     ["ANTHROPIC* API", "ANTHROPIC* API", "Anthropic PBC", "ANTHROPIC PBC SAN FRANCISCO CA"], (2025, 12), "eng"),
    ("openai", 9_000, 1.08, 1, ["card_debit"], ["OPENAI", "OPENAI *API", "OpenAI, LLC"], (2025, 9), "eng"),
    ("aws", 38_000, 1.06, 3, ["ach_debit", "ach_debit", "card_debit"],
     ["AMAZON WEB SERVICES", "Amazon Web Services, Inc.", "AWS EMEA"], (2025, 9), "eng"),
    ("modal", 4_500, 1.10, 4, ["card_debit"], ["MODAL LABS", "MODAL LABS INC", "MODAL LABS SAN FRANCISCO CA"], (2025, 9), "eng"),
    ("vercel", 2_400, 1.04, 5, ["card_debit"], ["VERCEL INC", "VERCEL*"], (2025, 9), "eng"),
    ("twilio", 1_800, 1.03, 7, ["card_debit"], ["TWILIO", "TWILIO INC"], (2025, 9), "eng"),
    ("datadog", 4_200, 1.05, 8, ["ach_debit"], ["DATADOG", "DATADOG INC"], (2025, 9), "eng"),
    ("fireworks", 900, 1.06, 9, ["card_debit"], ["FIREWORKS AI", "FIREWORKS.AI"], (2025, 9), "eng"),
    ("googleads", 8_000, 1.02, 1, ["card_debit"], ["GOOGLE *ADS", "GOOGLE ADS"], (2025, 9), "gtm"),
    ("posthog", 600, 1.04, 10, ["card_debit"], ["POSTHOG INC", "POSTHOG"], (2025, 9), "eng"),
]
USAGE_INVOICE_PREFIX = {
    "anthropic": "INV", "openai": "OAI", "aws": "AWS", "modal": "MDL", "vercel": "VRC", "twilio": "TWL",
    "datadog": "DD", "fireworks": "FW", "googleads": "GADS", "posthog": "PH",
}

# Fixed vendors: (descriptor list, $ per month, charge day, tx type, card or None, memo label)
FIXED_VENDORS = [
    (["ZOOM.US 888-799-9666", "ZOOM.US"], 239.85, 12, "card_debit", "ops", "Zoom Workplace Pro"),
    (["WEBFLOW INC", "WEBFLOW"], 212.00, 15, "card_debit", "ops", "Webflow CMS site plan"),
    (["ASHBY", "ASHBYHQ"], 1_250.00, 1, "card_debit", "ops", "Ashby ATS"),
    (["HUBSPOT INC", "HUBSPOT"], 1_600.00, 20, "ach_debit", None, "HubSpot Sales Hub"),
    (["APOLLO.IO", "APOLLO IO"], 594.00, 11, "card_debit", "gtm", "Apollo.io Professional"),
    (["LINKEDIN*SALES NAV", "LINKEDIN"], 1_199.88, 18, "card_debit", "gtm", "LinkedIn Sales Navigator"),
    (["CLOUDFLARE", "CLOUDFLARE INC"], 200.00, 22, "card_debit", "eng", "Cloudflare Pro"),
    (["SUPABASE", "SUPABASE INC"], 599.00, 24, "card_debit", "eng", "Supabase Team"),
    (["SENTRY", "FUNCTIONAL SOFTWARE INC"], 480.00, 26, "card_debit", "eng", "Sentry Business"),
    (["WEWORK COMMONS LLC", "WEWORK"], 23_850.00, 1, "ach_debit", None, "Office membership"),
    (["DEEL INC", "DEEL"], 20_500.00, 25, "ach_debit", None, "Contractor payments (2)"),
    (["PILOT.COM", "PILOT BOOKKEEPING"], 2_500.00, 5, "ach_debit", None, "Bookkeeping"),
]
# Small recurring tools absent from the taxonomy (KNOWN_UNKNOWN); all far below materiality.
UNKNOWN_FIXED = [
    ("CURSOR AI POWERED IDE", 640.00, 14, "eng", (2026, 2)),
    ("GRAMMARLY", 150.00, 16, "ops", (2025, 9)),
    ("CALENDLY", 96.00, 19, "gtm", (2025, 9)),
    ("CANVA* SUBSCRIPTION", 119.99, 21, "gtm", (2025, 11)),
]
# Seat tools: (descriptors, $ per seat, charge day, tx type, card, seat basis)
SEAT_VENDORS = [
    (["SLACK TECHNOLOGIES", "SLACK", "SALESFORCE SLACK"], 12.50, 1, "card_debit", "ops", "all"),
    (["GOOGLE *WORKSPACE", "GOOGLE WORKSPACE"], 14.00, 1, "card_debit", "ops", "all"),
    (["1PASSWORD", "AGILEBITS INC"], 7.99, 9, "card_debit", "ops", "all"),
    (["GITHUB, INC.", "GITHUB", "GITHUB INC"], 21.00, 4, "card_debit", "eng", "eng"),
    (["LINEAR ORBIT INC", "LINEAR"], 10.00, 13, "card_debit", "eng", "eng_ops"),
]


def cents(usd: float) -> int:
    return int(round(usd * 100))


def month_iter(start: date, end: date):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def month_end(y: int, m: int) -> date:
    return date(y, m, calendar.monthrange(y, m)[1])


def month_index(y: int, m: int) -> int:
    return y * 12 + m


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class Generator:
    def __init__(self, seed: int = SEED) -> None:
        self.rng = random.Random(seed)
        self.rows: list[dict] = []
        self.accounts = {
            "checking": {"id": self.uuid(), **CHECKING},
            "card": {"id": self.uuid(), **CARD},
        }
        self.people = [Person(n, t, None, self.uuid(), self.uuid()) for n, t in ORIGINAL_STAFF] + [
            Person(n, t, s, self.uuid(), self.uuid()) for n, t, s in JUNE_HIRES
        ]
        by_name = {p.name: p for p in self.people}
        self.virtual_cards = {
            "eng": {"owner": by_name[ENG_LEAD], "card_id": self.uuid(), "card_name": "Eng — API & Infra"},
            "ops": {"owner": by_name[FINANCE_LEAD], "card_id": self.uuid(), "card_name": "Ops — SaaS & Subscriptions"},
            "gtm": {"owner": by_name[GTM_LEAD], "card_id": self.uuid(), "card_name": "GTM — Tools"},
        }
        self.finance = by_name[FINANCE_LEAD]
        self.invoice_seq: dict[str, int] = {}

    # ---- primitives -------------------------------------------------------------------------

    def uuid(self) -> str:
        return str(uuid.UUID(int=self.rng.getrandbits(128), version=4))

    def stamp(self, d: date, h0: int = 8, h1: int = 19) -> datetime:
        return datetime(d.year, d.month, d.day, self.rng.randint(h0, h1), self.rng.randint(0, 59), self.rng.randint(0, 59))

    def noise(self, width: float) -> float:
        return 1 + self.rng.uniform(-width, width)

    def headcount_on(self, d: date) -> int:
        return HEADCOUNT_BASE + sum(1 for p in self.people if p.start is not None and p.start <= d)

    def team_count(self, d: date, teams: tuple[str, ...]) -> int:
        return sum(1 for p in self.people if p.team in teams and (p.start is None or p.start <= d))

    def row(
        self,
        *,
        account: str,
        amount_cents: int,
        counterparty: str,
        tx_type: str,
        initiated: datetime,
        settle_days: int = 0,
        status: str = "settled",
        card: dict | None = None,
        person: Person | None = None,
        memo: str | None = None,
        money_movement_id: str | None = None,
    ) -> dict:
        acct = self.accounts[account]
        if card is not None:
            card_id, card_name, user = card["card_id"], card["card_name"], card["owner"]
        elif person is not None and account == "card":
            card_id, card_name, user = person.card_id, person.card_name, person
        else:
            card_id, card_name, user = None, None, person
        if status == "pending":
            posted = None
        else:
            posted_dt = initiated + timedelta(days=settle_days)
            if settle_days:
                posted_dt = posted_dt.replace(hour=self.rng.randint(2, 5), minute=self.rng.randint(0, 59))
            else:
                posted_dt = posted_dt + timedelta(minutes=self.rng.randint(5, 180))
            posted = iso(posted_dt)
        r = {
            "id": self.uuid(),
            "money_movement_id": money_movement_id or self.uuid(),
            "account_id": acct["id"],
            "account_name": acct["name"],
            "account_type": acct["type"],
            "amount": {"amount": amount_cents, "currency": "USD"},
            "counterparty_name": counterparty,
            "counterparty_logo_url": None,
            "card_id": card_id,
            "card_name": card_name,
            "user_id": user.user_id if user else None,
            "user_full_name": user.name if user else None,
            "initiated_at": iso(initiated),
            "posted_at": posted,
            "transaction_type": tx_type,
            "status": status,
            "memo": memo,
            "note": None,
            "attachments": [],
            "tracking_number": None,
            "lines": [],
        }
        self.rows.append(r)
        return r

    def debit(self, usd: float, counterparty: str, tx_type: str, d: date, *, card_key: str | None, memo: str | None,
              person: Person | None = None) -> dict:
        if tx_type == "card_debit":
            return self.row(account="card", amount_cents=-cents(usd), counterparty=counterparty, tx_type=tx_type,
                            initiated=self.stamp(d), settle_days=self.rng.choice((1, 1, 2)),
                            card=self.virtual_cards[card_key] if card_key else None, person=person, memo=memo)
        return self.row(account="checking", amount_cents=-cents(usd), counterparty=counterparty, tx_type=tx_type,
                        initiated=self.stamp(d, 6, 11), person=person, memo=memo)

    def invoice_no(self, key: str, y: int, m: int) -> str:
        self.invoice_seq[key] = self.invoice_seq.get(key, 0) + 1
        return f"{USAGE_INVOICE_PREFIX.get(key, key.upper()[:4])}-{y}-{m:02d}-{self.invoice_seq[key]:03d}"

    # ---- payroll ----------------------------------------------------------------------------

    def payroll(self) -> None:
        for y, m in month_iter(PERIOD_START, PERIOD_END):
            per_head = PAYROLL_PER_HEAD_2025 if y == 2025 else PAYROLL_PER_HEAD_2026
            halves = [(date(y, m, 1), date(y, m, 15)), (date(y, m, 16), month_end(y, m))]
            for start, end in halves:
                days = (end - start).days + 1
                fte = float(HEADCOUNT_BASE)
                for p in self.people:
                    if p.start is None or p.start > end:
                        continue
                    worked = (end - max(start, p.start)).days + 1
                    fte += worked / days
                gross = per_head / 2 * fte * self.noise(0.01)
                net = round(gross * NET_PAY_SHARE, 2)
                taxes = round(gross - net, 2)
                mm = self.uuid()
                label = end.strftime("%m/%d/%Y")
                self.row(account="checking", amount_cents=-cents(net), counterparty="GUSTO PAYROLL", tx_type="ach_debit",
                         initiated=self.stamp(end, 6, 9), memo=f"Gusto payroll {label} net pay", money_movement_id=mm)
                self.row(account="checking", amount_cents=-cents(taxes), counterparty="GUSTO", tx_type="ach_debit",
                         initiated=self.stamp(end, 6, 9), memo=f"Gusto payroll {label} taxes", money_movement_id=mm)
            fee_day = date(y, m, 3)
            fee = 40 + 6 * self.headcount_on(fee_day)
            self.debit(fee, "GUSTO FEE", "ach_debit", fee_day, card_key=None,
                       memo=f"Gusto Plus subscription {calendar.month_abbr[m]} {y}")

    # ---- vendors ----------------------------------------------------------------------------

    def usage_vendors(self) -> None:
        aug = month_index(2026, 8)
        for key, anchor, growth, day, types, descriptors, first, card_key in USAGE_VENDORS:
            prev_amount: float | None = None
            months = list(month_iter(date(*first, 1), PERIOD_END))
            for i, (y, m) in enumerate(months):
                block = len(months) // len(descriptors) + 1
                descriptor = descriptors[min(i // block, len(descriptors) - 1)]
                tx_type = types[min(i // (len(months) // len(types) + 1), len(types) - 1)]
                trend = anchor * growth ** (month_index(y, m) - aug)
                if key == "anthropic" and (y, m) == (2026, 9):
                    amount = round(prev_amount * ANTHROPIC_SEP_MULTIPLIER, 2)
                else:
                    width = USAGE_NOISE_INJECT if (y, m) == (2026, 9) else USAGE_NOISE_HISTORY
                    amount = round(trend * self.noise(width), 2)
                prev_amount = amount
                py, pm = (y - 1, 12) if m == 1 else (y, m - 1)
                memo = f"Invoice {self.invoice_no(key, y, m)} usage {calendar.month_abbr[pm]} {py}"
                self.debit(amount, descriptor, tx_type, date(y, m, day), card_key=card_key, memo=memo)

    def fixed_vendors(self) -> None:
        for descriptors, usd, day, tx_type, card_key, label in FIXED_VENDORS:
            for i, (y, m) in enumerate(month_iter(PERIOD_START, PERIOD_END)):
                descriptor = descriptors[(i // 5) % len(descriptors)]
                self.debit(usd, descriptor, tx_type, date(y, m, day), card_key=card_key,
                           memo=f"{label} {calendar.month_abbr[m]} {y}")
        for descriptor, usd, day, card_key, first in UNKNOWN_FIXED:
            for y, m in month_iter(date(*first, 1), PERIOD_END):
                self.debit(usd, descriptor, "card_debit", date(y, m, day), card_key=card_key, memo=None)
        # Figma: same seats, new per-seat price from the September invoice.
        for i, (y, m) in enumerate(month_iter(PERIOD_START, PERIOD_END)):
            price = FIGMA_PRICE_NEW if date(y, m, 1) >= FIGMA_PRICE_CHANGE_FROM else FIGMA_PRICE_OLD
            descriptor = ["FIGMA", "FIGMA INC", "FIGMA MONTHLY RENEWAL"][(i // 5) % 3]
            self.debit(FIGMA_SEATS * price, descriptor, "card_debit", date(y, m, 1), card_key="ops",
                       memo=f"Figma Professional {FIGMA_SEATS} seats {calendar.month_abbr[m]} {y}")
        # Loom: stops after its July 2026 charge.
        for y, m in month_iter(PERIOD_START, LOOM_LAST_CHARGE):
            descriptor = "LOOM INC" if y == 2025 else "ATLASSIAN LOOM"
            self.debit(LOOM_USD, descriptor, "card_debit", date(y, m, 6), card_key="ops",
                       memo=f"Loom Business {calendar.month_abbr[m]} {y}")

    def seat_vendors(self) -> None:
        for descriptors, price, day, tx_type, card_key, basis in SEAT_VENDORS:
            for i, (y, m) in enumerate(month_iter(PERIOD_START, PERIOD_END)):
                d = date(y, m, day)
                if basis == "all":
                    seats = self.headcount_on(d)
                elif basis == "eng":
                    seats = self.team_count(d, ("Eng",))
                else:
                    seats = self.team_count(d, ("Eng", "Ops"))
                descriptor = descriptors[(i // 4) % len(descriptors)]
                self.debit(seats * price, descriptor, tx_type, d, card_key=card_key,
                           memo=f"{seats} seats {calendar.month_abbr[m]} {y}")
        # Notion: seats grow faster than headcount from July.
        for i, (y, m) in enumerate(month_iter(PERIOD_START, PERIOD_END)):
            seats = NOTION_SEATS.get((y, m), NOTION_SEATS_BASE)
            descriptor = ["NOTION LABS INC", "NOTION LABS", "NOTION"][(i // 5) % 3]
            self.debit(seats * NOTION_PRICE, descriptor, "card_debit", date(y, m, 2), card_key="ops",
                       memo=f"Notion Plus {seats} members {calendar.month_abbr[m]} {y}")

    def annual_vendors(self) -> None:
        d, usd = VANTA
        self.debit(usd, "VANTA INC", "ach_debit", d, card_key=None, memo="Vanta annual subscription Oct 2025 – Oct 2026")
        d, usd = CARTA
        self.debit(usd, "ESHARES INC DBA CARTA", "ach_debit", d, card_key=None, memo="Carta Launch annual Feb 2026 – Feb 2027")
        d, usd = VOUCH
        self.debit(usd, "VOUCH INSURANCE", "ach_debit", d, card_key=None, memo="D&O + GL annual premium 2026")

    def legal(self) -> None:
        for d, usd in [(date(2025, 10, 28), 9_850.00), (date(2026, 1, 27), 14_320.00),
                       (date(2026, 4, 29), 8_460.00), (date(2026, 7, 28), 11_740.00)]:
            mm = self.uuid()
            initiated = self.stamp(d, 9, 16)
            self.row(account="checking", amount_cents=-cents(usd), counterparty="COOLEY LLP", tx_type="wire_out",
                     initiated=initiated, person=self.finance, memo=f"Legal fees through {d.strftime('%b %Y')}",
                     money_movement_id=mm)
            self.row(account="checking", amount_cents=-2500, counterparty="COOLEY LLP", tx_type="wire_fee",
                     initiated=initiated + timedelta(seconds=2), memo="Outgoing wire fee", money_movement_id=mm)

    def pinecone(self) -> None:
        for d, usd in zip(PINECONE_DATES, (PINECONE_AUG_USD, PINECONE_SEP_USD)):
            self.debit(usd, "PINECONE SYSTEMS INC", "card_debit", d, card_key="eng", memo=None)

    # ---- employee card spend ----------------------------------------------------------------

    def pick_merchant(self, team: str) -> tuple[str, float, float]:
        pool = COMMON_MERCHANTS + TEAM_MERCHANTS[team]
        desc, lo, hi, _ = self.rng.choices(pool, weights=[w for *_, w in pool])[0]
        return desc, lo, hi

    def employee_swipes(self) -> None:
        for y, m in month_iter(PERIOD_START, PERIOD_END):
            m_start, m_end = date(y, m, 1), month_end(y, m)
            for p in self.people:
                first = max(p.swipes_from(), m_start)
                if first > m_end:
                    continue
                window = (m_end - first).days
                for k in range(self.rng.randint(1, 8)):
                    # A new hire's first swipe lands on the day their card goes live.
                    offset = 0 if (k == 0 and first == p.swipes_from() and p.start is not None) else self.rng.randint(0, window)
                    d = first + timedelta(days=offset)
                    desc, lo, hi = self.pick_merchant(p.team)
                    usd = round(self.rng.uniform(lo, hi), 2)
                    self.debit(usd, desc, "card_debit", d, card_key=None, memo=None, person=p)

    def offsite(self) -> None:
        d0, _ = OFFSITE_DAYS
        self.debit(9_800.00, "AIRBNB * HMXYZ", "card_debit", d0, card_key=None, memo=None, person=self.finance)
        for i, usd in enumerate((2_140.00, 2_260.00, 2_080.00, 1_920.00)):
            self.debit(usd, "UNITED 0162345678901", "card_debit", d0, card_key=None, memo=None, person=self.finance)
        for day, desc, usd in [(0, "TARTINE MANUFACTORY", 2_610.00), (1, "ZUNI CAFE", 3_120.00),
                               (2, "STATE BIRD PROVISIONS", 2_390.00), (3, "SOUVLA", 1_680.00)]:
            self.debit(usd, desc, "card_debit", d0 + timedelta(days=day), card_key=None, memo=None, person=self.finance)

    def refunds_and_declines(self) -> None:
        by_name = {p.name: p for p in self.people}
        for d, desc, usd, who in [(date(2026, 4, 22), "UNITED 0162345678901", 420.00, "Nathan Cole"),
                                  (date(2026, 1, 9), "AMZN MKTP US", 89.40, "Emily Tran"),
                                  (date(2026, 6, 3), "DOORDASH*ORDER", 34.10, "Sofia Reyes")]:
            self.row(account="card", amount_cents=cents(usd), counterparty=desc, tx_type="card_refund",
                     initiated=self.stamp(d), settle_days=1, person=by_name[who], memo=None)
        for d, desc, usd, who in [(date(2025, 12, 4), "MARRIOTT", 1_940.00, "Grace Kim"),
                                  (date(2026, 5, 19), "APPLE.COM/US", 2_499.00, "Tomasz Nowak"),
                                  (date(2026, 9, 18), "AMZN MKTP US", 312.50, "David Osei")]:
            self.row(account="card", amount_cents=-cents(usd), counterparty=desc, tx_type="card_debit",
                     initiated=self.stamp(d), status="failed", person=by_name[who], memo=None)

    def pending_tail(self) -> None:
        """A few card swipes in the last two days of each stage that have not posted yet."""
        for stage, (start, end) in STAGES.items():
            n = 4 if stage != "inject-1" else 3
            people = [p for p in self.people if p.swipes_from() <= end]
            for i in range(n):
                p = people[(i * 7 + len(stage)) % len(people)]
                d = end - timedelta(days=i % 2)
                desc, lo, hi = self.pick_merchant(p.team)
                self.row(account="card", amount_cents=-cents(round(self.rng.uniform(lo, hi), 2)), counterparty=desc,
                         tx_type="card_debit", initiated=self.stamp(d), status="pending", person=p, memo=None)

    # ---- money movement the pipeline must exclude -------------------------------------------

    def money_movement(self) -> None:
        card_id = self.accounts["card"]["id"]
        for y, m in month_iter(PERIOD_START, PERIOD_END):
            prev_y, prev_m = (y - 1, 12) if m == 1 else (y, m - 1)
            if (prev_y, prev_m) < (PERIOD_START.year, PERIOD_START.month):
                continue
            prefix = f"{prev_y}-{prev_m:02d}"
            balance = -sum(r["amount"]["amount"] for r in self.rows
                           if r["account_id"] == card_id and r["status"] == "settled"
                           and r["transaction_type"] in ("card_debit", "card_refund")
                           and r["initiated_at"].startswith(prefix))
            mm = self.uuid()
            initiated = self.stamp(date(y, m, 5), 7, 9)
            self.row(account="card", amount_cents=balance, counterparty="RHO CARD PAYMENT", tx_type="credit_repayment",
                     initiated=initiated, memo=f"Statement balance {calendar.month_abbr[prev_m]} {prev_y}",
                     money_movement_id=mm)
            self.row(account="checking", amount_cents=-balance, counterparty="RHO CARD PAYMENT",
                     tx_type="internal_transfer", initiated=initiated, memo="Rho Card autopay", money_movement_id=mm)
            rewards = int(round(balance * 0.0125))
            self.row(account="card", amount_cents=rewards, counterparty="RHO REWARDS", tx_type="rewards_accrual",
                     initiated=self.stamp(month_end(prev_y, prev_m), 22, 23), memo="Cashback accrual")
        for d, usd in [(date(2025, 10, 20), 1_500_000.00), (date(2026, 4, 2), 750_000.00)]:
            self.row(account="checking", amount_cents=-cents(usd), counterparty="RHO TREASURY", tx_type="treasury_deposit",
                     initiated=self.stamp(d, 9, 15), person=self.finance, memo="Sweep to Treasury")
        for d, desc, usd, tx_type in [(date(2025, 12, 18), "ACME CORP", 120_000.00, "wire_in"),
                                      (date(2026, 3, 27), "NORTHWIND HEALTH", 45_000.00, "ach_credit"),
                                      (date(2026, 7, 15), "GLOBEX INDUSTRIES", 200_000.00, "wire_in")]:
            self.row(account="checking", amount_cents=cents(usd), counterparty=desc, tx_type=tx_type,
                     initiated=self.stamp(d, 9, 16), memo="Customer payment")

    # ---- driver -----------------------------------------------------------------------------

    def run(self) -> dict[str, list[dict]]:
        self.payroll()
        self.usage_vendors()
        self.fixed_vendors()
        self.seat_vendors()
        self.annual_vendors()
        self.legal()
        self.pinecone()
        self.employee_swipes()
        self.offsite()
        self.refunds_and_declines()
        self.pending_tail()
        self.money_movement()  # last: repayments sum the card rows above
        self.rows.sort(key=lambda r: (r["initiated_at"], r["id"]))
        out: dict[str, list[dict]] = {stage: [] for stage in STAGES}
        for r in self.rows:
            d = date.fromisoformat(r["initiated_at"][:10])
            for stage, (start, end) in STAGES.items():
                if start <= d <= end:
                    out[stage].append(r)
                    break
        return out


def generate(seed: int = SEED) -> dict[str, list[dict]]:
    return Generator(seed).run()


def render(rows: list[dict]) -> bytes:
    return (json.dumps({"transactions": rows}, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def write(out_dir: Path = OUT_DIR, seed: int = SEED) -> dict[str, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    counts = {}
    for stage, rows in generate(seed).items():
        (out_dir / f"{stage}.json").write_bytes(render(rows))
        counts[stage] = len(rows)
    return counts


if __name__ == "__main__":
    for stage, n in write().items():
        print(f"{stage}.json: {n} rows")
