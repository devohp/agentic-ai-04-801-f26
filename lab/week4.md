# Week 4 Lab: Multi-Agent Orchestration, the Agent Skeleton

**Goal:** Role specialization. Your Week 3 agent was a generalist: one model, all tools, all responsibility. Now we decompose it into the canonical pattern **Data -> Analysis -> Report**, as a plain sequential pipeline. The conceptual core: **separation of concerns is enforced by capabilities, not requested by prompt.** The Analysis agent *cannot* fetch data; it does not have the tools. That is the difference between "I told the agent to only analyse" and actual architecture.

**Before you start:** run `git pull` in your repository folder. Nothing in this chapter needs a new installation; everything came with `requirements.txt` in Week 0. The iSDAsoil lines from Week 3 must still be in your `.env`.

**Scope discipline, stated up front:** two to three agents, no swarm. The simplest orchestration that carries the task wins. Router and critic patterns exist (Exercise 3 asks when they pay off), but a pipeline you can debug beats a swarm you cannot.

**A discovery worth knowing:** `langgraph` is already installed, and `requirements.txt` pins it, because `create_agent` builds on LangGraph internally. You have been using an orchestration framework since Week 3 without noticing. For your capstone, LangGraph and CrewAI are legitimate options if your design needs them. AutoGen is not: the package is in maintenance mode and receives no new features, and its maintainers point new users to its successor, Microsoft Agent Framework. The AutoGen paper (Wu et al., 2023) stays on the reading list, because the conversation patterns it describes outlive the package. The pipeline below deliberately uses no framework beyond what `create_agent` already provides, because plain function composition is the most debuggable orchestration there is.

## Module 4.1: The Data -> Analysis -> Report Pipeline

One import note first: we import from `soil_tool` (safe: it has an `if __name__ == "__main__":` guard) but define the `@tool` wrappers fresh instead of importing from `langchain_agent.py`. Exercise 4 asks you to find out why. In the course repo, shared tools live in a `tools.py` module for exactly this reason.

```python
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
```

Note: the two `IMPORTANT`/`COPIED VERBATIM` prompt clauses above were **not** in the first version of this script. They are fixes for the two failures documented below, which occurred in the instructor's validation run of the unfixed version. Read the autopsies; they are the actual content of this module.

### What the real run showed

The pipeline worked end to end on 11 Aug 2026: a fact sheet with the familiar reference values (pH 6.7 with CI, daily temperatures around 19 to 20 deg C, daily rainfall lines), numbered findings with a correct agronomic verdict (rainfall of 0.9 mm, the value of that day, far below planting needs), and a five-sentence report advising to delay sowing. The `calc` tool was demonstrably used (visible in the instructor's OpenRouter log as `tool_calls` finish reasons mid-analysis), settling the Week 2 debt. And the MISSING DATA protocol fired *smarter than designed*: the Analysis agent flagged soil moisture as missing, a quantity nobody had removed; it was simply never collected. Proactive gap detection instead of guessing.

Here is what the same pipeline printed on 27 Sep 2026 (run 6 of 8, after the clauses described below), with every fact and every finding carrying its source label, and the report naming its sources by name:

```
========================= STAGE 1: DATA =========================
Topsoil pH: 6.7 (0-20 cm) [50% CI 6.5-6.9, 68% CI 6.4-7.0, 90% CI 6.2-7.2] [iSDAsoil]  
2026-07-01 temperature: 21.2°C, rainfall: 3.0 mm [NASA POWER, MERRA2]  
2026-07-02 temperature: 20.99°C, rainfall: 2.92 mm [NASA POWER, MERRA2]  
2026-07-03 temperature: 21.51°C, rainfall: 0.18 mm [NASA POWER, MERRA2]  
2026-07-04 temperature: 21.97°C, rainfall: 0.2 mm [NASA POWER, MERRA2]  
2026-07-05 temperature: 20.55°C, rainfall: 0.53 mm [NASA POWER, MERRA2]  
2026-07-06 temperature: 19.9°C, rainfall: 0.16 mm [NASA POWER, MERRA2]  
2026-07-07 temperature: 20.12°C, rainfall: 0.04 mm [NASA POWER, MERRA2]
========================= STAGE 2: ANALYSIS =====================
The final findings are as follows:

FINDINGS:
1. Topsoil pH 6.7 (90% CI 6.2-7.2) is within the optimal range of 5.8-7.0 for maize [iSDAsoil] [standard agronomic knowledge].
2. MISSING DATA: soil moisture content needed to assess planting conditions.
3. Average temperature over 7 days is 20.89°C, within maize germination range of 18-32°C [NASA POWER, MERRA2] [standard agronomic knowledge].
4. Total rainfall over 7 days is 7.03 mm, insufficient for maize planting without supplemental irrigation (<25mm/week threshold) [NASA POWER, MERRA2] [standard agronomic knowledge].
========================= STAGE 3: REPORT =======================
The topsoil pH of 6.7 is suitable for maize growth. Soil moisture data is unavailable to assess planting conditions. The average temperature of 20.89°C supports maize germination. Rainfall of 7.03 mm over seven days is too low for planting without irrigation. Sources: [iSDAsoil], [standard agronomic knowledge], [NASA POWER], [MERRA2]. Uncertainty: pH range 6.2-7.2, rainfall and temperature estimates may vary by dataset.
```

But the transcript contained two failures that matter more than the success.

> **Autopsy 3: the pipeline silently lost content.** The printed Stage 2 output began with "3." Findings 1 and 2 (temperature, pH) were missing, although the summary line referenced them. The instructor's OpenRouter log explained it: mid-analysis, one generation with finish reason `tool_calls` carried 896 output tokens, and findings 1 and 2 lived there, interwoven with the calc calls. The agent's *final* message (89 output tokens) contained only the tail: findings 3, 4, summary. Our `run()` helper extracts `messages[-1].content`, so only the tail was handed to Stage 3, and the final report consequently never mentioned pH or temperature at all.
>
> This is the twin of Autopsy 1 (Week 3). There, interim content was wrongly *displayed*; here, final content was wrongly *assumed complete*. The lesson: **handoff extraction is design, not an afterthought.** The clean fix is the prompt clause now in the script ("your final message must restate ALL findings in full"). The tempting alternative, concatenating all AI messages, is wrong: it would reintroduce fabricated interim content (see Autopsy 1).

> **Autopsy 4: the fact sheet mislabeled uncertainty.** The Data agent wrote "pH 6.7 +/- 0.5 (68% confidence interval)". The tool had delivered: 68% CI = 6.4 to 7.0 (that is +/- 0.3); **+/- 0.5 is the 90% CI**. The "facts only" agent reformatted the intervals and relabeled one in passing. Facts were transformed, and transformation is where errors seep in.
>
> The lesson, directly relevant to the capstone rubric's uncertainty requirement: **relay is an error source too.** Whoever reports confidence intervals must pass them through unchanged; hence the "COPIED VERBATIM" clause now in the Data prompt. When your capstone report states an interval, be able to trace it, unaltered, to the tool output. For the same failure one level up, see Autopsy 11 in Week 3: there the final answer rewrote *which* measurement had failed, not just how an interval was written.

> **Residual risk, observed in the wild (confirmation run, 12 Aug 2026):** with both fix clauses active, the pipeline ran clean end to end, the 90% CI was relayed with its correct label, and the final Analysis message restated all findings in full. And yet the fact sheet read "pH 6.7 +/- 0.2 (90% CI: 6.2-7.2)". Where does +/- 0.2 come from? It is the **50% CI** (6.5 to 6.9), the first interval in the tool's list, converted to plus-minus notation and stripped of its label in one move. The VERBATIM clause prevented the coarse relabeling of Autopsy 4, but the subtler variant, conversion plus label loss, slipped through: a reader of the final report would naturally assume +/- 0.2 *is* the 90% CI. The general lesson, and the bridge to Week 5: **prompt guards lower the error rate; they do not eliminate the error class.** Only evals that check values against the tool output catch the residue.

> **Residual risk, measured (eight runs, 27 Sep 2026).** The August fixes held; the September series found three things behind them, each with a base rate.
>
> **Provenance died in the middle hop.** Stage 1 carried the source label 4 times out of 4; Stage 2 dropped it 4 of 4; Stage 3 wrote "soil sampling" and "weather stations" where the labels said iSDAsoil and NASA POWER. The cause was not a bug but an omission: the Analysis prompt demanded uncertainty notes and never mentioned sources. One clause per hop later (every finding ends with the labels it rests on; the report lists every label word for word), the label survived 3 of 3. Those clauses are in the script above. Your exercise 5 removes one and measures.
>
> **The verdict came 2 times out of 4** after every fix. Read the Analysis prompt and the question side by side: the prompt says "no recommendations beyond the findings", the question asks whether conditions support planting. The model chooses either way. That is a design question, not a patch: is a verdict a finding? Decide before you write the prompt, and write the decision in `DECISIONS.md`.
>
> **"Standard agronomic knowledge" is not standardized.** Three runs gave three germination thresholds for maize, 18 to 32, above 10, and 18 to 24 degrees, all under the same label. A label proves origin, not correctness. In the capstone, thresholds go in a file with a citation (FAO or Ecocrop, for example), never in the model's memory. The label then says which file.
>
> One more, from run 5: the Data agent called its tools and then returned an empty final message. The later stages did not invent anything (they wrote "MISSING DATA: entire fact sheet"), which is the Autopsy 3 discipline holding. But an empty result is a failed stage, not an input, and the code decides that: `run()` now retries once and then raises. An honest stop beats an empty handoff.

**Cost reference for your capstone budget:** on 11 Aug one pipeline run produced 6 generations, in total about USD 0.0032, with the largest single input at 2,239 tokens; on 27 Sep a run cost about USD 0.003. That input number shows *why* orchestration multiplies cost: each stage re-reads accumulated context. At that price, the USD 10 on a team key buys roughly three thousand pipeline runs, which sounds generous until a loop retries, a fourth agent joins, or a harness runs every scenario three times. Multiply by your team's iteration count before you architect a five-agent system.

### Exercises

**Work on a copy.** Exercises 1, 2 and 5 change the pipeline. Copy it first and edit only the copy, so `multi_agent.py` stays as shipped:

```powershell
copy multi_agent.py my_pipeline.py
python my_pipeline.py
git status          # my_pipeline.py is the only new file; multi_agent.py is unchanged
```

> **macOS or Linux:** `cp multi_agent.py my_pipeline.py`, then `python3 my_pipeline.py`.

If you edited the original by accident, `git restore multi_agent.py` brings it back.

1. Delete the pH line from `facts` before Stage 2 (hardcode the edit). Does the Analysis agent emit `MISSING DATA: pH`, or does it guess?
2. Ask the Report writer, via an extra instruction, for a number that is not in the findings. Does it comply, refuse, or invent?
3. In one sentence: for which task shape would a router beat this pipeline? (This is the one-sentence pattern statement from Session 4A.)
4. Try `import langchain_agent` in a Python shell and watch what happens. Explain why, and fix it with a `__main__` guard (`react_verdict.py` and `soil_tool.py` show the pattern). Do the fix on a copy as well.
5. Remove the source-label sentence from the Analysis prompt ("Every finding ends with the source label(s) ...") and run the pipeline four times. Count how often the report still names iSDAsoil and NASA POWER. Restore the clause. Prompt clauses are measured, not trusted: every clause in this file has a base rate behind it.

---

## Checkpoint 4 (team)

Your team has an agent skeleton: two or three agents with separate responsibilities, assembled from your members' Week 2 and Week 3 components and running end to end on `main`, even if the analysis is still thin. "Skeleton" means four things you can point to:

1. each agent has a stated responsibility and only the tools that responsibility needs;
2. every handoff passes text or a structure that the next stage can check, and an empty stage output stops the pipeline instead of feeding the next stage;
3. the source labels from your tools survive to the last stage;
4. one command runs it.

Record the topology as one signed entry in your team's `DECISIONS.md`: which pattern (pipeline, router, critic), why, and the trade-off you accepted (*What*, *Why*, *Trade-off*). The briefing, section 13, shows the entry format. Exercise 3 and the pattern statement from Session 4A are a good first draft of the *Why*.

**Reading for this week:** Wu, Q., Bansal, G., Zhang, J., Wu, Y., Li, B., Zhu, E., Jiang, L., Zhang, X., Zhang, S., Liu, J., Awadallah, A. H., White, R. W., Burger, D., & Wang, C. (2023). *AutoGen: Enabling next-gen LLM applications via multi-agent conversation* (arXiv:2308.08155). arXiv. https://doi.org/10.48550/arXiv.2308.08155. Skim it for the patterns, not the package.
