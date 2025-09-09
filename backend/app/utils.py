from __future__ import annotations

from typing import Dict, List

from .constants import REQUIRED_COLUMNS, SYNONYMS


def normalize(name: str) -> str:
    return name.strip().lower()


def map_headers(columns: List[str]) -> Dict[str, str]:
    lower = {c: normalize(c) for c in columns}
    mapping: Dict[str, str] = {}
    for req in REQUIRED_COLUMNS:
        req_l = normalize(req)
        # exact match
        for c, lc in lower.items():
            if lc == req_l:
                mapping[req] = c
                break
        else:
            syn = SYNONYMS.get(req_l)
            if syn:
                for c, lc in lower.items():
                    if lc in syn:
                        mapping[req] = c
                        break
    return mapping


def canonical_rename(df):
    """Rename known synonyms to their canonical names in-place when found."""
    reverse = {}
    for canon, syns in SYNONYMS.items():
        for s in syns:
            reverse[s] = canon
    rename_map = {}
    for c in df.columns:
        lc = normalize(str(c))
        if lc in reverse:
            # map to Title Case matching our REQUIRED_COLUMNS entry if exists
            # Keep as original casings for display but use canonical keys via additional columns
            canon_lower = reverse[lc]
            # map to human label: attempt to find exact required label with same lower
            for req in REQUIRED_COLUMNS:
                if normalize(req) == canon_lower:
                    rename_map[c] = req
                    break
    if rename_map:
        df.rename(columns=rename_map, inplace=True)
    return df
