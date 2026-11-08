# multi_agent.py, Week 4: role specialization as a sequential pipeline
# Pattern: Data -> Analysis -> Report. Three roles, three capability sets.
# Core idea: separation of concerns is ENFORCED by tool access, not requested
# by prompt. The Analysis agent cannot fetch data; it does not have the tools.

import json
import os
import requests
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from soil_tool import get_soil          # safe to import: it has a __main__ guard

load_dotenv()

model = ChatOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
    max_tokens=1024,                            # some providers reject calls without a budget
    timeout=60, max_retries=1,                  # fail loudly instead of hanging
    model="deepseek/deepseek-chat-v3-0324",
)

# ---- Shared tool definitions (course repo: these live in tools.py) ----------

@tool
def weather(latitude: float, longitude: float, start: str, end: str) -> str:
    """Daily air temperature (deg C) and rainfall (mm) for a location and
    date range from NASA POWER. Dates as YYYYMMDD."""
    url = "https://power.larc.nasa.gov/api/temporal/daily/point"
    params = {"parameters": "T2M,PRECTOTCORR", "community": "ag",
              "latitude": latitude, "longitude": longitude,
              "start": start, "end": end, "format": "JSON"}
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    label = f"\n[source: NASA POWER, {'/'.join(data['header']['sources'])}]"
    return json.dumps(data["properties"]["parameter"]) + label

SOIL_PROPS = ("ph", "carbon_organic", "nitrogen_total")   # what the snapshot covers

@tool
def soil(latitude: float, longitude: float, prop: str = "ph") -> str:
    """Topsoil property (0-20 cm) from iSDAsoil, with uncertainty intervals.
    prop must be one of: ph, carbon_organic, nitrogen_total. No other
    property exists in this tool; do not guess names."""
    if prop not in SOIL_PROPS:
        return (f"ERROR: unknown property '{prop}'. This tool offers only "
                f"{', '.join(SOIL_PROPS)}. Tell the user the value is not available.")
    try:
        return get_soil(latitude, longitude, prop)
    except RuntimeError as exc:
        return f"ERROR: {exc}"        # loud at the tool, observable to the model, never fatal

@tool
def calc(expression: str) -> str:
    """Evaluate a plain arithmetic expression, e.g. '0.4 + 0.31 + 0.05'.
    Use this for any sum or average instead of mental arithmetic."""
    # Lab-grade guard only: no builtins, no names. NEVER eval untrusted
    # input in production; we discuss proper sandboxing in Week 5.
    return str(eval(expression, {"__builtins__": {}}, {}))

# ---- Role 1: DATA agent (tools: weather, soil; forbidden: interpretation) ---

data_agent = create_agent(
    model=model,
    tools=[weather, soil],
    system_prompt=(
        "You are the DATA agent in a pipeline. Fetch what the task needs "
        "using your tools, then output a compact FACT SHEET: one line per "
        "fact, each with its source label and uncertainty COPIED VERBATIM "
        "from the tool output (do not relabel or convert intervals) "
        "including every source label in square brackets in full. "
        "Do NOT analyse, interpret, or recommend. Facts only."),
)

# ---- Role 2: ANALYSIS agent (tool: calc; cannot fetch anything) -------------

analysis_agent = create_agent(
    model=model,
    tools=[calc],
    system_prompt=(
        "You are the ANALYSIS agent in a pipeline. You receive a fact sheet. "
        "You cannot fetch data. If a needed fact is absent, write exactly "
        "'MISSING DATA: <what>' instead of guessing. Use the calc tool for "
        "all arithmetic. Output numbered FINDINGS with uncertainty notes. "
        "MISSING DATA refers to measurements that were not collected, "
        "not to agronomic reference values; use standard agronomic knowledge "
        "for thresholds and state it as such. "
        "Every finding ends with the source label(s) of the facts it rests "
        "on, copied verbatim from the fact sheet in square brackets; a "
        "threshold from your own knowledge is labelled [standard agronomic "
        "knowledge]. A finding without a source label is incomplete. "
        "IMPORTANT: your final message must restate ALL findings in full; "
        "partial output in earlier messages does not count. "
        "No prose report, no recommendations beyond the findings."),
)

# ---- Role 3: REPORT writer (no tools: an LLM call, not an agent) ------------

REPORT_SYSTEM = (
    "You write a short field report for an agricultural extension officer. "
    "Five sentences maximum, plain language. Use ONLY the findings you are "
    "given: never introduce numbers or claims that are not in them. State "
    "data sources and uncertainty in the final sentence."
    "The final sentence lists every source label that appears in the "
    "findings, word for word, and states the uncertainty.")

# ---- The pipeline: plain function composition -------------------------------

def run(agent, prompt: str, retries: int = 1) -> str:
    """Run one stage. An empty final message is a failed stage, not an input:
    retry once, then fail loudly (Autopsy 3 taught us never to concatenate)."""
    for attempt in range(retries + 1):
        result = agent.invoke({"messages": [{"role": "user", "content": prompt}]})
        content = result["messages"][-1].content
        if isinstance(content, str) and content.strip():
            return content
        print(f"[pipeline] stage returned an empty final message (attempt {attempt + 1})")
    raise RuntimeError("Stage produced no output after retry. An honest stop beats an empty handoff.")

TASK = ("Location: lat -1.94, lon 30.06 near Kigali. "
        "Period: 20260701 to 20260707. "
        "Needed: topsoil pH and daily temperature and rainfall.")

QUESTION = ("Based on the fact sheet, assess: do current conditions support "
            "planting maize at this location right now?")

print("=" * 25, "STAGE 1: DATA", "=" * 25)
facts = run(data_agent, TASK)
print(facts)

print("=" * 25, "STAGE 2: ANALYSIS", "=" * 21)
findings = run(analysis_agent, QUESTION + "\n\nFACT SHEET:\n" + facts)
print(findings)

print("=" * 25, "STAGE 3: REPORT", "=" * 23)
report = model.invoke([("system", REPORT_SYSTEM),
                       ("user", "FINDINGS:\n" + findings)]).content
print(report)
