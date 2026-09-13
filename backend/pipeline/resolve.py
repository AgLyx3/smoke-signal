"""Canonical vendor per row. `taxonomy` is any object exposing `resolve`, `normalize`, `VENDORS`
(backend/taxonomy.py, written in parallel); `EmptyTaxonomy` keeps the pipeline working without it."""

import re
from dataclasses import dataclass
from typing import Protocol

import pandas as pd

from pipeline.filter import FEE_CATEGORY

DEFAULT_CATEGORY = "Software"
DEFAULT_COST_TYPE = "fixed"
FEE_VENDOR = "Rho fees"
UNKNOWN_VENDOR = "Unknown counterparty"

_LEGAL_SUFFIXES = {"INC", "LLC", "LTD", "CORP", "CO", "PBC", "GMBH", "PLC", "SA", "AG", "LIMITED", "INCORPORATED"}


class Taxonomy(Protocol):
    VENDORS: list

    def normalize(self, counterparty_name: str) -> str: ...

    def resolve(self, counterparty_name: str) -> str | None: ...


def normalize_fallback(counterparty_name: str) -> str:
    """Case, `*` descriptors, punctuation, legal suffixes. Replaced by taxonomy.normalize when present."""
    s = str(counterparty_name or "").upper().replace("*", " ")
    s = re.sub(r"[^A-Z0-9&' ]+", " ", s)
    words = [w for w in s.split() if w not in _LEGAL_SUFFIXES]
    return " ".join(words).title() or UNKNOWN_VENDOR


class EmptyTaxonomy:
    VENDORS: list = []

    def normalize(self, counterparty_name: str) -> str:
        return normalize_fallback(counterparty_name)

    def resolve(self, counterparty_name: str) -> str | None:
        return None


@dataclass(frozen=True)
class Resolution:
    vendor: str
    category: str
    cost_type: str
    cost_type_source: str
    known: bool


def _vendor_table(taxonomy) -> dict[str, object]:
    return {v.name: v for v in getattr(taxonomy, "VENDORS", []) or []}


def resolve_name(counterparty_name: object, taxonomy, table: dict[str, object] | None = None) -> Resolution:
    table = _vendor_table(taxonomy) if table is None else table
    raw = str(counterparty_name or "").strip()
    if not raw:
        return Resolution(UNKNOWN_VENDOR, DEFAULT_CATEGORY, DEFAULT_COST_TYPE, "default", False)
    canonical = taxonomy.resolve(raw)
    if canonical:
        entry = table.get(canonical)
        category = getattr(entry, "category", DEFAULT_CATEGORY) if entry else DEFAULT_CATEGORY
        cost_type = getattr(entry, "cost_type", DEFAULT_COST_TYPE) if entry else DEFAULT_COST_TYPE
        return Resolution(canonical, category, cost_type, "taxonomy", True)
    key = taxonomy.normalize(raw) or normalize_fallback(raw)
    return Resolution(key, DEFAULT_CATEGORY, DEFAULT_COST_TYPE, "default", False)


def resolve_vendors(df: pd.DataFrame, taxonomy=None) -> pd.DataFrame:
    """Adds vendor, category, cost_type, cost_type_source, known. Fees resolve to a rule-based
    vendor in FEE_CATEGORY (context only, never a finding)."""
    taxonomy = taxonomy or EmptyTaxonomy()
    table = _vendor_table(taxonomy)
    out = df.copy()
    if len(out) == 0:
        for col, dtype in (("vendor", object), ("category", object), ("cost_type", object),
                           ("cost_type_source", object), ("known", bool)):
            out[col] = pd.Series(dtype=dtype)
        return out

    cache: dict[str, Resolution] = {}
    for name in out.loc[~out["is_fee"], "counterparty_name"].fillna("").unique():
        cache[name] = resolve_name(name, taxonomy, table)

    def fee_resolution(name: object) -> Resolution:
        raw = str(name or "").strip()
        vendor = normalize_fallback(raw) if raw else FEE_VENDOR
        return Resolution(vendor, FEE_CATEGORY, DEFAULT_COST_TYPE, "taxonomy", True)

    resolutions = [
        fee_resolution(n) if fee else cache[n if isinstance(n, str) else ""]
        for n, fee in zip(out["counterparty_name"].fillna(""), out["is_fee"])
    ]
    out["vendor"] = [r.vendor for r in resolutions]
    out["category"] = [r.category for r in resolutions]
    out["cost_type"] = [r.cost_type for r in resolutions]
    out["cost_type_source"] = [r.cost_type_source for r in resolutions]
    out["known"] = [r.known for r in resolutions]
    return out
