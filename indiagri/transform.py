"""Pure transformations used by the collectors (no network, no disk).

Keeping these free of I/O lets the quirks of the two portals be unit-tested offline:
Agmarknet arrival rows carry no ``cmdt_id`` so rows are keyed on the commodity *name*, and
the FCI report mixes year rows with "% Change" summary rows.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

Row = Dict[str, Any]
StateMonthKey = Tuple[str, str, str]  # (YYYY-MM, commodity name, state name)

# Dashboard pseudo ids: 0 is "All"; >= 9000 are dashboard groups (e.g. 9999 = MSP).
PSEUDO_ID_FLOOR = 9000


def months(start: str, end: str) -> Iterator[Tuple[int, int]]:
    """Yield (year, month) from ``start`` to ``end`` inclusive; both are ``'YYYY-MM'`` strings."""
    y, m = map(int, start.split("-"))
    y2, m2 = map(int, end.split("-"))
    while (y, m) <= (y2, m2):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def chunked(items: Sequence[Any], size: int) -> List[Sequence[Any]]:
    """Split ``items`` into consecutive batches of at most ``size``."""
    return [items[i:i + size] for i in range(0, len(items), size)]


def real_commodity_ids(rows: Iterable[Row]) -> List[int]:
    """Sorted unique numeric commodity ids from dashboard-commodity rows, pseudo ids dropped."""
    ids = set()
    for r in rows:
        raw = r.get("cmdt_id") or r.get("id")
        if str(raw or "").isdigit():
            ids.add(int(raw))
    return [i for i in sorted(ids) if 0 < i < PSEUDO_ID_FLOOR]


def merge_state_monthly(out: Dict[StateMonthKey, Row], year: int, month: int, kind: str,
                        records: Iterable[Row]) -> None:
    """Fold one batch of ``statewise_price_arrival`` records into ``out`` (mutated in place).

    ``kind`` is ``'price'`` (Rs/qtl) or ``'arrival'`` (tonnes). Price records carry ``cmdt_id`` and
    arrival records do not, so both are keyed on the stripped commodity name and merge into one row.
    """
    ym = f"{year}-{month:02d}"
    column = "price_rs_qtl" if kind == "price" else "arrivals_t"
    for r in records:
        name = (r.get("cmdt_name") or "").strip()
        state = r["state_name"].strip()
        row = out.setdefault((ym, name, state), {
            "month": ym, "commodity_id": None, "commodity": name,
            "group": r.get("cmdt_grp_name"), "state": state})
        if r.get("cmdt_id") is not None:
            row["commodity_id"] = r["cmdt_id"]
        row[column] = r.get("as_on")


def sorted_state_monthly(out: Dict[StateMonthKey, Row]) -> List[Row]:
    """Rows ordered by commodity, state, month (the on-disk order of state_monthly.csv.gz)."""
    return sorted(out.values(), key=lambda r: (r["commodity"], r["state"], r["month"]))


def market_sample_row(date: str, rec: Row) -> Row:
    """Map one Agmarknet ``market_details_sp`` record to a market_daily_sample row."""
    return {"date": date, "commodity": rec.get("cmdt_name"), "state": rec.get("state_name"),
            "district": rec.get("district_name"), "market": rec.get("mkt_name"), "mkt_id": rec.get("mkt_id"),
            "arrival_t": rec.get("arrival_qty"), "modal_price_rs_qtl": rec.get("modal_price_wt")}


def reported_markets(records: Iterable[Row]) -> List[Row]:
    """Keep only markets that reported on the day (``status == 'Reported Markets'``)."""
    return [x for x in records if x.get("status") == "Reported Markets"]


def flatten_districts(states: Iterable[Row]) -> List[Row]:
    """One row per district with its parent state's id and name (either key spelling accepted)."""
    return [{"state_id": s.get("state_id") or s.get("id"), "state_name": s.get("state_name") or s.get("name"), **d}
            for s in states for d in (s.get("districts") or [])]


def first_list_value(rows: Any) -> Any:
    """If a master came back as a dict, use its first list value (or wrap the dict); else unchanged."""
    if isinstance(rows, dict):
        return next((v for v in rows.values() if isinstance(v, list)), [rows])
    return rows


def dedupe_fci(rows: Iterable[Row]) -> List[Row]:
    """Keep year rows only, one per (state, crop, year).

    The FCI report also returns "% Change in ..." summary rows, and consecutive calls overlap by
    two years, so duplicates are expected.
    """
    seen = set()
    keep: List[Row] = []
    for x in rows:
        key: Optional[Tuple[Any, Any, Any]] = (x.get("statename"), x.get("cropname"), x.get("years"))
        if str(x.get("years", "")).startswith("%") or key in seen:
            continue
        seen.add(key)
        keep.append(x)
    return keep
