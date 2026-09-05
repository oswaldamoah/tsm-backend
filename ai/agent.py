"""
The agent loop.

Flow: the model gets the question plus the read-only data tools from tools.py.
It calls whatever it needs, we run those against the DB and feed the JSON back,
and it answers. Charts and presentations are themselves tools - the model calls
create_chart / create_presentation to attach an artifact, which keeps the
structured output on the function-calling path instead of asking a free model to
hand-write JSON inside prose (which it gets wrong often enough to matter).
"""

from datetime import datetime, timezone
from typing import Any, Optional
import json
import logging
import os
import time

from sqlalchemy.orm import Session

from .provider import LLMError, LLMProvider, get_provider
from .tools import DATA_TOOLS, DATA_TOOLS_BY_NAME

logger = logging.getLogger(__name__)


# The model gets this many chances to call tools before we demand a final answer.
MAX_TOOL_ITERATIONS = 8
# Wall-clock budget for one question, across every provider round-trip. Once it
# is spent the model is asked to answer from what it already has, instead of
# calling more tools. This must stay comfortably under the web server's request
# timeout (see --timeout in the Procfile), otherwise a slow free-tier model gets
# the worker killed mid-request and the user sees a 502 instead of an answer.
TOTAL_BUDGET_SECONDS = float(os.environ.get("AI_TOTAL_BUDGET", "90"))
# Client-supplied history is trimmed to this many turns to bound prompt size.
MAX_HISTORY_MESSAGES = 12
MAX_CHART_POINTS = 40
MAX_SLIDES = 15


CHART_TYPES = ["bar", "stacked_bar", "line", "area", "pie", "doughnut"]


# ========== OUTPUT TOOLS ==========

OUTPUT_TOOLS: list[dict] = [
    {
        "name": "create_chart",
        "description": (
            "Attach a chart to your answer, rendered in the app. Call this whenever the user asks "
            "for a chart, graph, breakdown or visual, or when a comparison is clearly easier to read "
            "as a picture. Use ONLY numbers you got from a data tool in this conversation - never "
            "estimate or invent values. Every series must have exactly one value per category."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Chart title."},
                "chart_type": {"type": "string", "enum": CHART_TYPES},
                "categories": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "X-axis labels (or slice labels for pie/doughnut).",
                },
                "series": {
                    "type": "array",
                    "description": "One entry per plotted measure. Pie/doughnut charts use exactly one.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Series label, e.g. 'Labor cost'."},
                            "values": {"type": "array", "items": {"type": "number"}},
                        },
                        "required": ["name", "values"],
                    },
                },
                "x_label": {"type": "string"},
                "y_label": {"type": "string", "description": "Include the unit, e.g. 'Cost (GHS)'."},
            },
            "required": ["title", "chart_type", "categories", "series"],
        },
    },
    {
        "name": "create_presentation",
        "description": (
            "Attach a slide deck to your answer. The user can view it in the app or download it as "
            "PowerPoint. Call this when asked for a presentation, deck, slides, or a report to show "
            "others. Create the charts you want to include FIRST, then reference them by chart_index "
            "(0 for the first chart you created this turn). Keep bullets short and factual."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "subtitle": {"type": "string"},
                "slides": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "bullets": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "3-6 short bullets. Include real figures.",
                            },
                            "chart_index": {
                                "type": "integer",
                                "description": "Index of a chart created this turn to place on this slide.",
                            },
                            "notes": {"type": "string", "description": "Optional speaker notes."},
                        },
                        "required": ["title"],
                    },
                },
            },
            "required": ["title", "slides"],
        },
    },
]

OUTPUT_TOOL_NAMES = {tool["name"] for tool in OUTPUT_TOOLS}


def _coerce_chart(args: dict) -> dict:
    """Validate a model-proposed chart and normalise it for the renderer."""
    categories = [str(c) for c in (args.get("categories") or [])][:MAX_CHART_POINTS]
    if not categories:
        raise ValueError("chart needs at least one category")

    chart_type = (args.get("chart_type") or "bar").lower()
    if chart_type not in CHART_TYPES:
        chart_type = "bar"

    series = []
    for raw in args.get("series") or []:
        values = raw.get("values") or []
        numbers: list[float] = []
        for value in values[: len(categories)]:
            try:
                numbers.append(round(float(value), 2))
            except (TypeError, ValueError):
                numbers.append(0.0)
        # Pad so a short series doesn't silently shift against its categories.
        numbers += [0.0] * (len(categories) - len(numbers))
        series.append({"name": str(raw.get("name") or "Value"), "values": numbers})

    if not series:
        raise ValueError("chart needs at least one series")

    if chart_type in ("pie", "doughnut"):
        series = series[:1]

    return {
        "title": str(args.get("title") or "Chart"),
        "type": chart_type,
        "categories": categories,
        "series": series,
        "xLabel": str(args.get("x_label") or ""),
        "yLabel": str(args.get("y_label") or ""),
    }


def _coerce_presentation(args: dict, chart_count: int) -> dict:
    slides = []
    for raw in (args.get("slides") or [])[:MAX_SLIDES]:
        if not isinstance(raw, dict):
            continue
        chart_index = raw.get("chart_index")
        if not isinstance(chart_index, int) or not (0 <= chart_index < chart_count):
            chart_index = None
        slides.append({
            "title": str(raw.get("title") or "Slide"),
            "bullets": [str(b) for b in (raw.get("bullets") or [])][:8],
            "chartIndex": chart_index,
            "notes": str(raw.get("notes") or ""),
        })

    if not slides:
        raise ValueError("presentation needs at least one slide")

    return {
        "title": str(args.get("title") or "Presentation"),
        "subtitle": str(args.get("subtitle") or ""),
        "slides": slides,
    }


# ========== SYSTEM PROMPT ==========

SYSTEM_PROMPT = """You are the data assistant inside {company}, a telecom site management app.
You answer questions about the company's sites, activities, materials and costs.

Today is {today}. All money is in Ghanaian Cedi (GHS).

HOW TO WORK
- Always get your numbers by calling the data tools. You have no memory of this database
  and no numbers of your own. If you have not read a figure from a tool result in this
  conversation, you do not know it.
- Call get_data_dictionary first if you are unsure what regions, site types or fields exist.
- Prefer aggregate_costs for any grouped/comparative cost question; it does the arithmetic for you.
- You may call several tools before answering. Stop calling tools once you can answer.
- If a tool returns an error or no rows, say so plainly instead of guessing.
- Archived sites and activities are excluded by default. Mention it if the user's question
  probably meant to include them.

HOW TO ANSWER
- Be direct and short. Lead with the answer, then the supporting figures.
- Format money as GHS 1,234.56. Use markdown lists and tables where they help.
- Never invent site names, dates or amounts. If the data cannot answer the question, say what
  is missing.
- You are read-only: you cannot create, edit, archive or delete anything. If asked to change
  data, explain that the user has to do it in the app.

CHARTS AND DECKS
- Call create_chart when a visual genuinely helps, and always when one is asked for.
- Call create_presentation when the user wants slides, a deck, or a report to present. Build the
  charts first, then reference them by chart_index.
- After attaching a chart or deck, write a brief sentence describing it. Do not restate the whole
  dataset in prose."""


def build_system_prompt(company_name: Optional[str], user_role: Optional[str]) -> str:
    prompt = SYSTEM_PROMPT.format(
        company=company_name or "your company",
        today=datetime.now(timezone.utc).strftime("%A, %d %B %Y"),
    )
    if user_role:
        prompt += f"\n\nThe person asking is signed in as a {user_role}."
    return prompt


# ========== THE LOOP ==========

def _normalise_history(history: Optional[list]) -> list[dict]:
    """Keep only clean user/assistant text turns from the client-supplied history."""
    messages: list[dict] = []
    for entry in history or []:
        if not isinstance(entry, dict):
            continue
        role = entry.get("role")
        content = entry.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            messages.append({"role": role, "content": content.strip()[:4000]})
    return messages[-MAX_HISTORY_MESSAGES:]


def _run_data_tool(db: Session, name: str, arguments: dict) -> Any:
    tool = DATA_TOOLS_BY_NAME.get(name)
    if not tool:
        return {"error": f"Unknown tool '{name}'."}
    try:
        return tool["handler"](db, **(arguments or {}))
    except TypeError as exc:
        # Model passed an argument the handler doesn't take - tell it, don't crash.
        return {"error": f"Invalid arguments for {name}: {exc}"}
    except Exception as exc:
        logger.exception("AI tool %s failed", name)
        return {"error": f"{name} failed: {exc}"}


def answer_question(
    db: Session,
    question: str,
    history: Optional[list] = None,
    company_name: Optional[str] = None,
    user_role: Optional[str] = None,
    provider: Optional[LLMProvider] = None,
) -> dict:
    """Answer one question, optionally attaching charts and a presentation."""
    provider = provider or get_provider()
    system = build_system_prompt(company_name, user_role)

    messages = _normalise_history(history)
    messages.append({"role": "user", "content": question.strip()[:4000]})

    all_tools = [
        {"name": t["name"], "description": t["description"], "parameters": t["parameters"]}
        for t in DATA_TOOLS
    ] + OUTPUT_TOOLS

    charts: list[dict] = []
    presentation: Optional[dict] = None
    tools_used: list[str] = []
    answer: Optional[str] = None

    deadline = time.monotonic() + TOTAL_BUDGET_SECONDS

    for iteration in range(MAX_TOOL_ITERATIONS):
        # Withhold the tools on the last pass, or once the time budget is spent,
        # so the model has no option but to answer from what it already has.
        out_of_time = time.monotonic() >= deadline
        if out_of_time:
            logger.warning("AI time budget spent after %s tool calls; forcing an answer", len(tools_used))
        offered_tools = [] if (out_of_time or iteration == MAX_TOOL_ITERATIONS - 1) else all_tools
        response = provider.generate(system, messages, offered_tools)

        if not response.tool_calls:
            answer = response.text
            break

        messages.append({
            "role": "assistant",
            "content": response.text,
            "tool_calls": response.tool_calls,
        })

        for call in response.tool_calls:
            tools_used.append(call.name)

            if call.name == "create_chart":
                try:
                    charts.append(_coerce_chart(call.arguments))
                    result: Any = {"status": "chart attached", "chart_index": len(charts) - 1}
                except Exception as exc:
                    result = {"error": f"Chart rejected: {exc}"}
            elif call.name == "create_presentation":
                try:
                    presentation = _coerce_presentation(call.arguments, len(charts))
                    result = {"status": "presentation attached", "slides": len(presentation["slides"])}
                except Exception as exc:
                    result = {"error": f"Presentation rejected: {exc}"}
            else:
                result = _run_data_tool(db, call.name, call.arguments)

            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "name": call.name,
                "content": json.dumps(result, default=str),
            })

    if not answer:
        if charts or presentation:
            answer = "Here's what I found." if charts else "I've put the deck together."
        else:
            raise LLMError("The model did not produce an answer. Try rephrasing the question.")

    return {
        "answer": answer,
        "charts": charts,
        "presentation": presentation,
        "toolsUsed": tools_used,
        "provider": provider.name,
        "model": provider.model,
    }
