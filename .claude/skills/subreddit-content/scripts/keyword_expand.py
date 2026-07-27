"""Merge Claude seed terms + DataForSEO rows into one ranked query set."""
from __future__ import annotations

import re

_WS = re.compile(r"\s+")


def normalize_term(term: str) -> str:
    """Lowercase, strip, collapse internal whitespace."""
    return _WS.sub(" ", str(term).strip().lower())


def merge_and_rank(
    seeds: list[str],
    dataforseo_rows: list[dict],
    *,
    max_queries: int = 40,
    platform_max_words: int = 4,
) -> dict:
    """Return {expanded, query_set, platform_queries, broad_queries}.

    Seeds rank first (source='seed'); DataForSEO rows follow, higher volume
    first then shorter term. Deduped by normalized term (seed wins). Capped
    at max_queries."""
    rows: list[dict] = []
    seen: set[str] = set()

    for s in seeds:
        t = normalize_term(s)
        if t and t not in seen:
            seen.add(t)
            rows.append({"term": t, "volume": 0, "source": "seed"})

    dfs: list[dict] = []
    for r in dataforseo_rows:
        t = normalize_term(r.get("keyword", ""))
        if not t or t in seen:
            continue
        seen.add(t)
        vol = r.get("search_volume") or 0
        dfs.append({"term": t, "volume": int(vol), "source": "dataforseo"})

    # DataForSEO ordering: volume desc, then shorter term
    dfs.sort(key=lambda r: (-r["volume"], len(r["term"])))

    expanded = (rows + dfs)[:max_queries]
    query_set = [r["term"] for r in expanded]
    platform_queries = [t for t in query_set if len(t.split()) <= platform_max_words]
    return {
        "expanded": expanded,
        "query_set": query_set,
        "platform_queries": platform_queries,
        "broad_queries": list(query_set),
    }


if __name__ == "__main__":
    import json
    import sys
    seeds = sys.argv[1].split(",") if len(sys.argv) > 1 else []
    print(json.dumps(merge_and_rank([s for s in seeds], []), indent=2))
