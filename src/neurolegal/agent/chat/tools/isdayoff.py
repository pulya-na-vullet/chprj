"""RF production calendar via isdayoff.ru (year-keyed in-process cache)."""

from datetime import date

import httpx

from neurolegal.core.http import make_http_retry

# A published year-mask is immutable, so both successes and permanent misses are
# cached for the process lifetime. Caching the miss (as None) prevents
# add_working_days — which calls is_working_day once per candidate day — from
# re-running the full retry schedule on every step when isdayoff.ru is down.
_cache: dict[int, str | None] = {}


async def _year_mask(year: int) -> str | None:
    if year in _cache:
        return _cache[year]
    try:
        async for attempt in make_http_retry():
            with attempt:
                async with httpx.AsyncClient(timeout=10.0) as c:
                    r = await c.get(f"https://isdayoff.ru/api/getdata?year={year}")
                    r.raise_for_status()
                    mask = r.text.strip()
        _cache[year] = mask
        return mask
    except (httpx.HTTPError, ValueError):
        _cache[year] = None
        return None


async def is_working_day(d: date) -> tuple[bool, bool]:
    """Return (is_working, fallback).

    fallback=True when the calendar was unavailable and we fell back to a
    Mon-Fri weekday heuristic.
    """
    mask = await _year_mask(d.year)
    if mask is None:
        return (d.weekday() < 5, True)
    idx = d.timetuple().tm_yday - 1
    if idx >= len(mask):
        return (d.weekday() < 5, True)
    return (mask[idx] == "0", False)
