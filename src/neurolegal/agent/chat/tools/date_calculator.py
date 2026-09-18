"""Tool: date_calculator — date arithmetic with RF working/holiday calendar."""

import json
from datetime import date, timedelta

from neurolegal.agent.chat.tools.base import ToolContext, ToolOutcome
from neurolegal.agent.chat.tools.isdayoff import is_working_day
from neurolegal.agent.llm.types import ToolSpec

DATE_CALC_TOOL = ToolSpec(
    name="date_calculator",
    description=(
        "Расчёт дат и сроков, включая рабочие/праздничные дни РФ. Операции: "
        "add_days, add_working_days, diff_days, weekday, is_working_day."
    ),
    parameters={
        "type": "object",
        "properties": {
            "op": {
                "type": "string",
                "enum": [
                    "add_days",
                    "add_working_days",
                    "diff_days",
                    "weekday",
                    "is_working_day",
                ],
            },
            "date": {"type": "string", "description": "Дата ISO YYYY-MM-DD."},
            "date2": {"type": "string", "description": "Вторая дата для diff_days."},
            "days": {"type": "integer", "description": "Число дней для add_*."},
        },
        "required": ["op", "date"],
    },
)


async def handle(arguments: dict[str, object], ctx: ToolContext) -> ToolOutcome:
    try:
        op = str(arguments["op"])
        d = date.fromisoformat(str(arguments["date"]))
    except (KeyError, ValueError):
        return ToolOutcome(json.dumps({"error": "invalid date/op"}, ensure_ascii=False))

    fallback = False
    res: dict[str, object]

    if op == "add_days":
        res = {"result": (d + timedelta(days=int(str(arguments.get("days", 0))))).isoformat()}

    elif op == "diff_days":
        try:
            d2 = date.fromisoformat(str(arguments["date2"]))
        except (KeyError, ValueError):
            return ToolOutcome(json.dumps({"error": "date2 required"}, ensure_ascii=False))
        res = {"result": (d2 - d).days}

    elif op == "weekday":
        res = {"result": d.isoweekday()}

    elif op == "is_working_day":
        wd, fallback = await is_working_day(d)
        res = {"result": wd}

    elif op == "add_working_days":
        n = int(str(arguments.get("days", 0)))
        step = 1 if n >= 0 else -1
        remaining = abs(n)
        cur = d
        while remaining > 0:
            cur += timedelta(days=step)
            wd, fb = await is_working_day(cur)
            fallback = fallback or fb
            if wd:
                remaining -= 1
        res = {"result": cur.isoformat()}

    else:
        return ToolOutcome(json.dumps({"error": "unknown op"}, ensure_ascii=False))

    if fallback:
        res["fallback"] = True
    return ToolOutcome(json.dumps(res, ensure_ascii=False))
