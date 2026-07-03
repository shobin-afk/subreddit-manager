"""Score discovery candidates 0..100 for shortlisting."""
from __future__ import annotations

import math
from datetime import date

WEIGHTS = {
    "engagement": 0.35,
    "freshness": 0.20,
    "relevance": 0.30,
    "hook": 0.15,
}

# log10(1 + engagement) / _ENGAGEMENT_LOG_REF, clamped to [0,1].
# _ENGAGEMENT_LOG_REF = 6 means ~1,000,000 engagements maps to ~1.0.
_ENGAGEMENT_LOG_REF = 6.0


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _engagement_norm(raw: float) -> float:
    if raw <= 0:
        return 0.0
    return _clamp01(math.log10(1.0 + raw) / _ENGAGEMENT_LOG_REF)


def _coerce_engagement(value) -> float:
    """Best-effort float coercion for the ``engagement`` field. Upstream
    discovery (e.g. the last30days skill) may emit a dict of engagement
    breakdowns or a formatted string like "1.2M" instead of a plain number.
    Anything that can't be converted is treated as 0.0 rather than crashing
    the batch."""
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _freshness(cand_date: str, today: date, days: int) -> float:
    try:
        d = date.fromisoformat(cand_date)
    except (ValueError, TypeError):
        return 0.0
    age = (today - d).days
    if age < 0:
        age = 0
    return _clamp01(1.0 - age / days)


def score_candidate(cand: dict, *, today: date, days: int) -> float:
    """Return a 0..100 weighted score for a single candidate."""
    eng = _engagement_norm(_coerce_engagement(cand.get("engagement", 0)))
    fresh = _freshness(str(cand.get("date", "")), today, days)
    rel = _clamp01(float(cand.get("relevance", 0.0) or 0.0))
    hook = _clamp01(float(cand.get("hook", 0.0) or 0.0))
    total = (
        WEIGHTS["engagement"] * eng
        + WEIGHTS["freshness"] * fresh
        + WEIGHTS["relevance"] * rel
        + WEIGHTS["hook"] * hook
    )
    return round(total * 100.0, 4)


def score_all(cands: list[dict], *, today: date, days: int) -> list[dict]:
    """Return candidates with a ``score`` key, sorted highest first."""
    out = []
    for c in cands:
        cc = dict(c)
        cc["score"] = score_candidate(c, today=today, days=days)
        out.append(cc)
    out.sort(key=lambda c: c["score"], reverse=True)
    return out
