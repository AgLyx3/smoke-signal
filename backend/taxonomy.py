"""Vendor master list shared by the data generator and the pipeline.

`resolve()` maps a raw Rho `counterparty_name` to a canonical vendor by exact match on the
normalised name or one of its aliases. Anything it cannot resolve is an unknown vendor and goes
to the LLM classifier (or a user override)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

CostType = Literal["usage", "fixed", "headcount", "annual", "payroll"]
Cadence = Literal["semi-monthly", "monthly", "annual", "irregular"]

CATEGORIES = (
    "AI & inference",
    "Cloud & infra",
    "Data & tooling",
    "Software",
    "People & payroll",
    "Sales & marketing",
    "Office & travel",
    "Professional services",
    "Fees & other",
)


@dataclass(frozen=True)
class Vendor:
    name: str
    aliases: tuple[str, ...]
    category: str
    cost_type: CostType
    cadence: Cadence


VENDORS: list[Vendor] = [
    # AI & inference
    Vendor("Anthropic", ("ANTHROPIC* API", "Anthropic PBC", "ANTHROPIC PBC SAN FRANCISCO CA"), "AI & inference", "usage", "monthly"),
    Vendor("OpenAI", ("OPENAI", "OPENAI *API", "OpenAI, LLC"), "AI & inference", "usage", "monthly"),
    Vendor("Fireworks AI", ("FIREWORKS AI", "FIREWORKS.AI"), "AI & inference", "usage", "monthly"),
    Vendor("Modal", ("MODAL LABS", "MODAL LABS INC", "MODAL LABS SAN FRANCISCO CA"), "AI & inference", "usage", "monthly"),
    # Cloud & infra
    Vendor("AWS", ("AMAZON WEB SERVICES", "AWS EMEA", "Amazon Web Services, Inc."), "Cloud & infra", "usage", "monthly"),
    Vendor("Vercel", ("VERCEL INC", "VERCEL*"), "Cloud & infra", "usage", "monthly"),
    Vendor("Twilio", ("TWILIO", "TWILIO INC"), "Cloud & infra", "usage", "monthly"),
    Vendor("Cloudflare", ("CLOUDFLARE", "CLOUDFLARE INC"), "Cloud & infra", "fixed", "monthly"),
    Vendor("Supabase", ("SUPABASE", "SUPABASE INC"), "Cloud & infra", "fixed", "monthly"),
    # Data & tooling
    Vendor("Datadog", ("DATADOG", "DATADOG INC"), "Data & tooling", "usage", "monthly"),
    Vendor("GitHub", ("GITHUB", "GITHUB INC", "GITHUB, INC."), "Data & tooling", "headcount", "monthly"),
    Vendor("Linear", ("LINEAR", "LINEAR ORBIT INC"), "Data & tooling", "headcount", "monthly"),
    Vendor("Sentry", ("SENTRY", "FUNCTIONAL SOFTWARE INC"), "Data & tooling", "fixed", "monthly"),
    Vendor("PostHog", ("POSTHOG", "POSTHOG INC"), "Data & tooling", "usage", "monthly"),
    Vendor("Vanta", ("VANTA", "VANTA INC"), "Data & tooling", "annual", "annual"),
    # Software
    Vendor("Figma", ("FIGMA", "FIGMA INC", "FIGMA MONTHLY RENEWAL"), "Software", "fixed", "monthly"),
    Vendor("Notion", ("NOTION", "NOTION LABS", "NOTION LABS INC"), "Software", "headcount", "monthly"),
    Vendor("Slack", ("SLACK", "SLACK TECHNOLOGIES", "SALESFORCE SLACK"), "Software", "headcount", "monthly"),
    Vendor("Google Workspace", ("GOOGLE *WORKSPACE", "GOOGLE WORKSPACE"), "Software", "headcount", "monthly"),
    Vendor("1Password", ("1PASSWORD", "AGILEBITS INC"), "Software", "headcount", "monthly"),
    Vendor("Zoom", ("ZOOM.US", "ZOOM.US 888-799-9666", "ZOOM VIDEO COMMUNICATIONS"), "Software", "fixed", "monthly"),
    Vendor("Loom", ("LOOM", "LOOM INC", "ATLASSIAN LOOM"), "Software", "fixed", "monthly"),
    Vendor("Webflow", ("WEBFLOW", "WEBFLOW INC"), "Software", "fixed", "monthly"),
    Vendor("Ashby", ("ASHBY", "ASHBYHQ"), "Software", "fixed", "monthly"),
    Vendor("Carta", ("CARTA", "ESHARES INC DBA CARTA"), "Software", "annual", "annual"),
    # People & payroll
    Vendor("Gusto Payroll", ("GUSTO PAYROLL", "GUSTO", "GUSTO PAY"), "People & payroll", "payroll", "semi-monthly"),
    Vendor("Gusto (fee)", ("GUSTO FEE", "GUSTO SOFTWARE FEE"), "People & payroll", "headcount", "monthly"),
    Vendor("Deel", ("DEEL", "DEEL INC"), "People & payroll", "fixed", "monthly"),
    # Sales & marketing
    Vendor("HubSpot", ("HUBSPOT", "HUBSPOT INC"), "Sales & marketing", "fixed", "monthly"),
    Vendor("Apollo.io", ("APOLLO.IO", "APOLLO IO"), "Sales & marketing", "fixed", "monthly"),
    Vendor("LinkedIn", ("LINKEDIN", "LINKEDIN*SALES NAV", "LINKEDIN SALES NAV"), "Sales & marketing", "fixed", "monthly"),
    Vendor("Google Ads", ("GOOGLE *ADS", "GOOGLE ADS"), "Sales & marketing", "usage", "monthly"),
    # Office & travel
    Vendor("WeWork", ("WEWORK", "WEWORK COMMONS LLC"), "Office & travel", "fixed", "monthly"),
    Vendor("Uber", ("UBER *TRIP", "UBER TRIP", "UBER"), "Office & travel", "usage", "irregular"),
    Vendor("Lyft", ("LYFT *RIDE", "LYFT"), "Office & travel", "usage", "irregular"),
    Vendor("DoorDash", ("DOORDASH*ORDER", "DOORDASH"), "Office & travel", "usage", "irregular"),
    Vendor("Airbnb", ("AIRBNB", "AIRBNB * HMXYZ"), "Office & travel", "usage", "irregular"),
    Vendor("United Airlines", ("UNITED AIRLINES", "UNITED 0162345678901"), "Office & travel", "usage", "irregular"),
    Vendor("Delta Air Lines", ("DELTA AIR LINES", "DELTA AIR 0062345678901"), "Office & travel", "usage", "irregular"),
    # Professional services
    Vendor("Pilot.com", ("PILOT.COM", "PILOT BOOKKEEPING"), "Professional services", "fixed", "monthly"),
    Vendor("Cooley LLP", ("COOLEY LLP", "COOLEY"), "Professional services", "usage", "irregular"),
    Vendor("Vouch Insurance", ("VOUCH INSURANCE", "VOUCH INSURANCE SERVICES LLC"), "Professional services", "annual", "annual"),
]

# Deliberately absent from VENDORS so the LLM classifier has real work. Pinecone is the
# new-vendor alert; the others are small recurring tools that must stay below materiality.
KNOWN_UNKNOWN: list[str] = [
    "Pinecone",
    "Cursor",
    "Grammarly",
    "Calendly",
    "Canva",
]

_LEGAL_SUFFIXES = frozenset(
    {"inc", "llc", "ltd", "pbc", "co", "corp", "corporation", "incorporated", "limited", "plc", "gmbh", "sa", "bv"}
)
_US_STATES = frozenset(
    "al ak az ar ca co ct de fl ga hi id il in ia ks ky la me md ma mi mn ms mo mt ne nv nh nj nm ny nc nd oh ok or pa "
    "ri sc sd tn tx ut vt va wa wv wi wy dc".split()
)
_CITIES = (
    ("san", "francisco"),
    ("new", "york"),
    ("los", "angeles"),
    ("palo", "alto"),
    ("mountain", "view"),
    ("menlo", "park"),
    ("seattle",),
    ("austin",),
    ("oakland",),
    ("denver",),
    ("chicago",),
    ("boston",),
    ("london",),
    ("dublin",),
)
_NUMERIC = re.compile(r"^[\d\-#]+$")


def normalize(counterparty_name: str) -> str:
    """Lowercase; `*` and punctuation become spaces (dots inside tokens survive, so
    `zoom.us` stays one token); drop trailing store/phone numbers, a trailing
    "<city> <STATE>" fragment, and trailing legal suffixes; collapse whitespace."""
    s = counterparty_name.lower().replace("*", " ")
    s = re.sub(r"[^\w\s.&]", " ", s)
    tokens = [t.strip(".") for t in s.split()]
    tokens = [t for t in tokens if t]

    def drop_numeric_tail() -> None:
        while len(tokens) > 1 and _NUMERIC.match(tokens[-1]):
            tokens.pop()

    drop_numeric_tail()
    if len(tokens) >= 3 and tokens[-1] in _US_STATES:
        tokens.pop()
    for city in _CITIES:
        n = len(city)
        if len(tokens) > n and tuple(tokens[-n:]) == city:
            del tokens[-n:]
            break
    while len(tokens) > 1 and tokens[-1] in _LEGAL_SUFFIXES:
        tokens.pop()
    drop_numeric_tail()
    return " ".join(tokens)


def _build_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for vendor in VENDORS:
        for raw in (vendor.name, *vendor.aliases):
            key = normalize(raw)
            if key in index and index[key] != vendor.name:
                raise ValueError(f"alias collision: {raw!r} maps to both {index[key]!r} and {vendor.name!r}")
            index[key] = vendor.name
    return index


_INDEX = _build_index()
_BY_NAME = {v.name: v for v in VENDORS}


def resolve(counterparty_name: str) -> str | None:
    """Canonical vendor name for a raw descriptor, or None when unknown."""
    return _INDEX.get(normalize(counterparty_name))


def vendor(name: str) -> Vendor:
    return _BY_NAME[name]
