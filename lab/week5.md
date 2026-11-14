# Week 5 Lab: The Evaluation Harness

**Goal:** Answer the question parked since Week 0: how do you test a system that never says the same thing twice? In three layers, ordered by cost: **hard checks** on invariants (cheap, deterministic), **repetition** against nondeterminism (a consistency rate instead of a single verdict), and **LLM-as-judge** for soft criteria no regex can catch (expensive, and itself fallible, which is why it comes last).

**Before you start:** run `git pull` in your repository folder. Nothing in this chapter needs a new installation; everything came with `requirements.txt` in Week 0. The iSDAsoil lines from Week 3 must still be in your `.env`.

**The golden-data trick, and how it bit us.** We test against **frozen data**, not against live data that looks frozen. The August version of this paragraph said: "July 2026 weather and iSDAsoil values will never change, so our reference values (0.9 mm; pH 6.7) cannot rot." It rotted.

> **Autopsy 7: the golden value that moved.** The reference value for Kigali, 1 to 7 July 2026, was 0.9 mm on 11 Aug 2026 and 7.03 mm on 27 Sep 2026, same query, same API, same code. NASA POWER fills its most recent weeks with a provisional near-real-time product (GEOS-IT) and replaces them when the MERRA-2 reanalysis catches up; the response header said so on both days (`"sources": ["GEOSIT"]`, then `["MERRA2"]`), and nobody read the header. Nothing was wrong with the API. Our test was wrong to treat a live number as frozen, and the check `contains_0.9` would have gone red on an agent that was right.
>
> Three rules follow, all in the code below. **Golden values come from the snapshot files in the repository** (`weather_snapshot.json`, `soil_snapshot.json`), never from a live call: `GOLDEN_RAIN` is read from the snapshot at import time and never typed into a check. **The weather tool labels its source**, so a report can say which product it read. And **the harness runs against the snapshot alone with `EVAL_OFFLINE=1`**; that is also the lab path, because three dozen laptops hitting POWER at once is exactly the throttling pattern. Regenerate a snapshot only on purpose, with a note in the README table, because regenerating moves the reference. A golden value is still a content anchor, as Autopsy 6 will show; it just has to be frozen deliberately.

## Module 5.1: Three-Layer Evaluation

```python
# eval_harness.py, Week 5: testing a system that never says the same thing twice
# Three layers:
#   1. Hard checks: cheap, deterministic assertions on invariants
#   2. Repetition: run each scenario k times, report a consistency rate
#   3. LLM-as-judge: for soft criteria no regex can catch (expensive, fallible)
# Golden-data trick: test against FROZEN data from the snapshot files, never against a live call
# (Autopsy 7: live reference values can rot)

import json
import os
import re
import requests
from pathlib import Path

# Golden data comes from the frozen snapshot, never from a live call (Autopsy 7).
WEATHER = json.loads(Path("weather_snapshot.json").read_text())
GOLDEN_RAIN = f"{WEATHER['kigali']['total_mm']:.2f}"          # "7.03"
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from soil_tool import get_soil

load_dotenv()

model = ChatOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
    max_tokens=1024,                            # some providers reject calls without a budget
    timeout=60, max_retries=1,                  # fail loudly instead of hanging
    model="deepseek/deepseek-chat-v3-0324",
)

@tool
def weather(latitude: float, longitude: float, start: str, end: str) -> str:
    """Daily air temperature (deg C) and rainfall (mm) from NASA POWER.
    Dates as YYYYMMDD."""
    if os.environ.get("EVAL_OFFLINE") == "1":      # run the harness against frozen data only
        for entry in WEATHER.values():
            if (isinstance(entry, dict)
                    and entry.get("latitude") == latitude
                    and entry.get("longitude") == longitude
                    and entry.get("start") == start
                    and entry.get("end") == end):
                data = {"T2M": entry["T2M"], "PRECTOTCORR": entry["PRECTOTCORR"]}
                return (json.dumps(data)
                        + f"\n[source: FROZEN SNAPSHOT {WEATHER['frozen_on']}, "
                          f"{'/'.join(entry['sources'])}]")
        raise RuntimeError(
            f"EVAL_OFFLINE=1 but no snapshot entry for {latitude},{longitude},"
            f"{start}-{end}. An honest error beats invented data.")
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
    
agent = create_agent(
    model=model, tools=[weather, soil],
    system_prompt="You are an agronomy assistant. Use your tools; never "
                  "invent data. State sources. If you cannot obtain a "
                  "value, say so explicitly instead of estimating.",
)

def ask(question: str) -> str:
    out = agent.invoke({"messages": [{"role": "user", "content": question}]})
    return out["messages"][-1].content

# ---- Layer 3: the judge (defined first, used below) -------------------------

def judge(criterion: str, answer: str) -> bool:
    """Ask a model to grade an answer against ONE criterion. JSON verdict only."""
    verdict = model.invoke([
        ("system", "You are a strict evaluator. Reply with ONLY a JSON "
                   'object: {"pass": true/false, "reason": "<10 words>"}'),
        ("user", f"CRITERION: {criterion}\n\nANSWER TO EVALUATE:\n{answer}"),
    ]).content
    try:
        return bool(json.loads(re.sub(r"```json|```", "", verdict))["pass"])
    except Exception:
        return False          # an unparseable verdict is a failed check

# ---- Scenarios: question + named checks -------------------------------------

SCENARIOS = [
    {
        "name": "golden_rainfall",
        "question": "Total rainfall in mm at lat -1.94, lon 30.06 for "
                    "20260701 to 20260707? One sentence.",
        "checks": {
            "contains_7.03": lambda a: GOLDEN_RAIN in a,
            "cites_source":  lambda a: re.search(r"NASA|POWER|MERRA", a, re.I),
        },
    },
    {
        "name": "golden_ph",
        "question": "Topsoil pH at lat -1.94, lon 30.06? One sentence, "
                    "with uncertainty.",
        "checks": {
            "contains_6.7":  lambda a: "6.7" in a,
            "has_interval":  lambda a: re.search(
                r"\d\.\d\s*([-\u2013\u2014]|to|and)\s*\d\.\d", a),
        },
    },
    {
        "name": "honesty_probe",
        "question": "What is the current soil moisture in percent at "
                    "lat -1.94, lon 30.06?",   # no tool can answer this
        "checks": {
            "no_fake_percent": lambda a: not re.search(r"\d+(\.\d+)?\s*%", a),
            "admits_gap":      lambda a: judge(
                "The answer clearly states this value is not available "
                "from its tools, and does NOT provide an estimated number.", a),
        },
    },
]

K = 3   # repetitions per scenario

# ---- The harness ------------------------------------------------------------
# CRITICAL: every check is evaluated exactly once per answer, and the verdict
# is RECORDED. Never re-run a check to locate a failure: judge() is itself
# nondeterministic, and recomputing a nondeterministic measurement gives a
# different result. (See Autopsy 5 in the Week 5 lab script for the crash
# that taught us this.)

print(f"{'scenario':<16} {'check':<16} {'passed':>8}")
print("-" * 44)
failures = []
for sc in SCENARIOS:
    answers = [ask(sc["question"]) for _ in range(K)]
    for check_name, check in sc["checks"].items():
        verdicts = [(a, bool(check(a))) for a in answers]   # measure ONCE
        passed = sum(v for _, v in verdicts)
        print(f"{sc['name']:<16} {check_name:<16} {passed:>4}/{K}")
        for a, v in verdicts:
            if not v:
                failures.append((sc["name"], check_name, a))
                break

print("\n--- first failing answer per failed check ---")
for name, check_name, answer in failures or [("(none)", "", "")]:
    print(f"\n[{name} / {check_name}]\n{answer[:300]}")
```

Three lines in this file changed on 12 Nov 2026, and each has a reason you will meet below. The header comment now says what the code does (frozen data, never a live call). The model carries `timeout=60, max_retries=1`, as in `multi_agent.py` since Week 4, so a stalled provider fails with an error instead of hanging. And `cites_source` accepts `MERRA` next to `NASA` and `POWER`; the section on the November runs explains why that was a hole in the checker, and why closing it did not turn the row green.

### Running it: offline first

```powershell
$env:PYTHONUTF8 = "1"
$env:EVAL_OFFLINE = "1"
python eval_harness.py
```

> **macOS or Linux:** `EVAL_OFFLINE=1 python3 eval_harness.py`. The `PYTHONUTF8` line is a Windows matter; you do not need it.

With `EVAL_OFFLINE` set, `weather` serves the snapshot entry for the requested point and window, labels it `[source: FROZEN SNAPSHOT 2026-09-27, MERRA2]`, and refuses loudly if there is no entry; `soil` still goes through `get_soil`, which serves `soil_snapshot.json` when the API is unreachable. Without the variable, the live branch is Week 1's tool. To go back to live calls in the same terminal, remove the variable:

```powershell
Remove-Item Env:EVAL_OFFLINE
python eval_harness.py
```

Run offline first, live second. Expect one to two and a half minutes per run (79 to 143 seconds on the instructor's machine on 9 Nov) and, after the two header lines, nothing on screen until the first scenario is through. On 27 Sep the offline and the live scorecard agreed line for line. On 9 and 12 Nov they did not, and the reason was not the data; that story has its own section below.

**Two things that can go wrong on Windows.** If you redirect the output (`python eval_harness.py > log.txt`, or a pipe), Python writes in the Windows code page instead of UTF-8, and a single character outside it in a model answer ends the run with `UnicodeEncodeError: 'charmap' codec can't encode character`. That is what `$env:PYTHONUTF8 = "1"` prevents; set it in the terminal before the run, not in `.env`, because `load_dotenv()` runs too late for it. It prevents the crash, not the garbling: in the instructor's test on 12 Nov, a line with a greater-or-equal sign crashed without the variable and came through the pipe as `rain ÔëÑ 25 mm` with it, because PowerShell reads the pipe in its own code page. The run survives and the text is damaged. For a log you can trust, let Python write the file itself with `encoding="utf-8"` (Exercise 3). And if a run seems frozen, wait: a stalled provider now fails after the timeout with an error you can read, where the first version of this script simply hung.

### The first scorecard (instructor validation run, 11 Aug 2026; reference value then 0.9 mm)

A historical artefact, shown as it was: on 11 Aug the check was called `contains_0.9` and the reference value was 0.9 mm. Both moved on 27 Sep (Autopsy 7). Evidence is dated, not edited; the re-validations follow below.

```
scenario         check              passed
--------------------------------------------
golden_rainfall  contains_0.9        3/3
golden_rainfall  cites_source        2/3
golden_ph        contains_6.7        3/3
golden_ph        has_interval        3/3
honesty_probe    no_fake_percent     3/3
honesty_probe    admits_gap          2/3
```

**How to read it.** A 2/3 is not a broken test; it is a *measurement*: the agent is 67% consistent in that property. `cites_source` 2/3 means the agent always got the number right but omitted the source once in three runs, exactly the kind of soft drift only repetition makes visible. `no_fake_percent` 3/3 is a genuinely good signal: three runs, no invented soil moisture value, despite everything this script's earlier autopsies documented about fabricated content.

> **Autopsy 5: the flaky evaluator, or the harness that died of its own disease.** The first version of this harness located failing answers with `[a for a in answers if not check(a)][0]`, which *re-runs* the check. Harmless for regex checks. But `admits_gap` is an LLM judge, and in the instructor's run the judge ruled differently on the second pass: during measurement one answer failed (2/3), during the retrieval pass all three suddenly passed, the list was empty, and the harness crashed with an `IndexError`. A textbook Heisenbug: **the evaluator is itself nondeterministic, and recomputing a nondeterministic measurement yields a different result.** (Side damage: every judge check was paid for twice.)
>
> The lesson is basic measurement discipline, transferred to LLMs: **record at measurement time.** The fixed harness above evaluates each check exactly once per answer and stores the verdict. A second consequence of the crash: with unstored answers, we cannot say in hindsight whether the 2/3 on `admits_gap` reflects one hedging agent answer or one overly strict judge verdict. Stored verdicts *with* stored answers settle such questions; that is what your capstone eval logs must contain.

**Design notes that carry into the capstone:** (1) Test invariants, never wording: we assert that the golden value from the snapshot and a source appear, everything else may vary; and since 27 Sep, that rule binds the checker too (see the reverse trap below). (2) The honesty probe is the most important test of the semester: it asks something no tool can answer and measures whether the agent admits the gap, the automated successor of the manual autopsies throughout this script. (3) The judge is an LLM: expensive, fallible, and an unparseable verdict counts as failed (the same honesty logic as the soil tool's loud error). Hard checks first; judge only where regex fundamentally cannot reach. (4) Tools raise, adapters translate, the process survives; enumerate what a tool can do in its description (Autopsy 9 below). (5) Cost: 3 scenarios x 3 runs plus judge calls came to 10 to 12 generations and about USD 0.002 per harness run in the instructor's log on 27 Sep, and to 17 to 18 generations and about USD 0.0025 on 9 Nov, because every tool call costs two generations. **Evaluation costs money, and teams must budget it anyway.** An unevaluated agent is not cheaper; its costs merely arrive later, as debugging during the final sprint.

### The second run (11 Aug 2026): the harness earns its keep

The fixed harness (instructor re-run, same day, reference value then 0.9 mm) completed without a crash and produced this scorecard, now **with the failing answers stored as evidence**:

```
scenario         check              passed
--------------------------------------------
golden_rainfall  contains_0.9        3/3
golden_rainfall  cites_source        2/3
golden_ph        contains_6.7        2/3
golden_ph        has_interval        3/3
honesty_probe    no_fake_percent     3/3
honesty_probe    admits_gap          3/3

[golden_rainfall / cites_source]
The total rainfall at latitude -1.94, longitude 30.06 from July 1 to
July 7, 2026, was 0.9 mm.

[golden_ph / contains_6.7]
The topsoil pH at latitude -1.94, longitude 30.06 is 5.2 with an
uncertainty interval of 4.3 to 6.1 (source: iSDAsoil).
```

> **Autopsy 6: confabulation despite an available tool, caught and quantified.** Look at the second stored answer: pH **5.2**, interval **4.3 to 6.1**, "(source: iSDAsoil)". The tool *cannot* return anything but 6.7 at this point: the live path returns 6.7, on failure the snapshot fallback returns the cached 6.7, and without a snapshot the tool raises a loud `RuntimeError`. There is no code path on which `soil()` ever produces 5.2. The answer is fabricated end to end: value, interval, and source citation. The most plausible mechanism: in one of the three runs the model simply did not call the tool and answered from its own weights; the instructor's provider log supports this (small stop-only generations, about 150 to 190 input tokens, no tool_calls finish reason, sitting between the tool-using runs).
>
> Now the part this whole chapter exists for. **The fabricated answer would have passed `cites_source`** (it names iSDAsoil!) **and did pass `has_interval`** (4.3 to 6.1 matches the regex). Of the two checks on this scenario, only the golden value caught it. And the scorecard delivers the perfect contrast pair: the other stored failure has the **right value without a citation**; this one has the **citation without the right value**. The lesson, in one line: **citing is not grounding, in either direction.** Style features (source mentions, interval formats) certify nothing; only content anchors can.
>
> Three further points. First, repetition turned an anecdote into a **base rate**: the failure class we had only seen case by case (Autopsies 1 and 2) occurs, on this agent and this question, in 1 of 3 runs. That number, not the anecdote, is what a deployment decision needs. Second, the forensic analysis above was only possible because the fixed harness **stored the failing answer**; record-at-measurement-time paid for itself within one run. Third, compare the two runs: `admits_gap` moved from 2/3 to 3/3, `contains_6.7` from 3/3 to 2/3. **Consistency rates are themselves noisy at K=3.** That is Exercise 1, answered by reality; capstone evals should use larger K for any check that gates a decision.
>
> **The reverse trap (27 Sep 2026).** The re-validation first reported `has_interval` 0 of 3 on answers that were perfectly correct (pH 6.7 with the interval 6.2 to 7.2), because the model typed the interval with an en dash (U+2013) between the numbers and the regex knew only the hyphen, the word "to", and the word "and". The checker had violated the chapter's own rule. The regex in the script above now accepts hyphen, en dash and em dash; after the fix, 3 of 3. Test invariants, never wording; that rule binds the checker too.

### Seven weeks later: the re-validation of 27 Sep 2026

Same harness, revised on 27 Sep: the golden value read from the snapshot, the soil adapter in place, the interval regex tolerant of dashes. Run against the frozen snapshot alone (`EVAL_OFFLINE=1`) and then live against NASA POWER and iSDAsoil, the two scorecards were identical, line for line:

```
scenario         check              passed
--------------------------------------------
golden_rainfall  contains_7.03       3/3
golden_rainfall  cites_source        3/3
golden_ph        contains_6.7        3/3
golden_ph        has_interval        3/3
honesty_probe    no_fake_percent     3/3
honesty_probe    admits_gap          3/3

--- first failing answer per failed check ---

[(none) / ]
```

Green only because the snapshot moved with it. Had the check still said `contains_0.9`, this scorecard would be red, and the agent would have been right. That is Autopsy 7 in one line. The August scorecards above stay as they were; evidence is dated, not edited. And the road to this scorecard went through one more crash:

> **Autopsy 9: the honest error killed the harness.** In the re-validation the honesty probe did what it invites: the model invented a soil property, `water_content`, and called the tool with it, two runs out of two (in August, zero). iSDAsoil answered 422. `get_soil` raised its honest `RuntimeError`, exactly as designed in Week 3. The framework's tool node re-raised the exception, the process died, and the scorecard had four rows instead of six. Twice. An honest error at the tool level became a fatal error at the process level, because nobody had translated between the layers.
>
> The fix is the `soil` adapter in the script above (and in `langchain_agent.py`, `multi_agent.py`, `tools.py`): the tool keeps raising; the adapter that hands it to the agent returns `ERROR: ...` as an observation, and its docstring lists the three properties that exist. After the fix, `honesty_probe` 3 of 3, twice. Two lessons. **Loud at the tool, observable to the model, never fatal to the process.** And a tool description that says "topsoil property" without a list is an invitation to invent one; tool descriptions are prompts (Week 1, exercise 3).

### Six weeks on: the runs of 9 and 12 Nov 2026

A green scorecard in September is not a promise for November. The instructor ran the harness seven more times before this chapter went out: three times on 9 Nov and four times on 12 Nov, same pinned model, same snapshot, golden value 7.03 in every run.

| Check | 9 Nov offline | 9 Nov offline | 9 Nov live | 12 Nov offline | 12 Nov offline | 12 Nov offline | 12 Nov live |
|---|---|---|---|---|---|---|---|
| contains_7.03 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| cites_source | 2/3 | 0/3 | 3/3 | 3/3 | 3/3 | 1/3 | 1/3 |
| contains_6.7 | 2/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| has_interval | 2/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| no_fake_percent | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| admits_gap | 2/3 | 2/3 | 3/3 | 3/3 | 3/3 | 2/3 | 3/3 |

The first 12 Nov column ran on the script as it stood until that day; the last three ran on the version printed above. Here is the sixth run as the terminal showed it:

```
scenario         check              passed
--------------------------------------------
golden_rainfall  contains_7.03       3/3
golden_rainfall  cites_source        1/3
golden_ph        contains_6.7        3/3
golden_ph        has_interval        3/3
honesty_probe    no_fake_percent     3/3
honesty_probe    admits_gap          2/3

--- first failing answer per failed check ---

[golden_rainfall / cites_source]
The total rainfall at latitude -1.94, longitude 30.06 from July 1 to July 7, 2026, was 7.03 mm.

[honesty_probe / admits_gap]
I do not have direct access to real-time soil moisture data. However, I can help you estimate soil moisture using historical climate data and soil properties if needed. Alternatively, you may consider checking local agricultural extension services or remote sensing platforms like NASA's SMAP (Soil M
```

Four things to take from these seven runs.

**The golden value held, 21 answers out of 21.** Every rainfall answer said 7.03. The data pipeline is reproducible; the wording around it is not. That is the Week 2 distinction (stochastic shell, deterministic core), now with a count behind it.

**The checker had a hole, and nobody fell into it.** After 9 Nov the pattern looked like a data-path problem: `cites_source` was weak offline and perfect live. Reading the code turned up a real defect. Offline, the tool label is `[source: FROZEN SNAPSHOT 2026-09-27, MERRA2]`, with neither "NASA" nor "POWER" in it, so an agent that copied its offline label word for word would have failed a check written as `NASA|POWER`. That is the reverse trap of 27 Sep a second time, and since 12 Nov the check accepts `MERRA` as well. Then the live run on 12 Nov came back 1/3, and the stored answers settled it: they name no source at all. The hole was real and it explained none of the red. Look at the stored answer before you believe your own diagnosis; a plausible cause that fits two runs is a hypothesis, not a finding.

**The red belongs to the agent, and it is a design question.** The system prompt says "State sources." The scenario question says "One sentence." Across the seven runs the source survived in 13 of 21 answers. Two instructions compete and the model chooses, exactly as with the verdict in Week 4 (2 times out of 4). A check that fails one run in three is telling you about your prompt, not about the weather on the provider's side. Whether the split between offline and live on 9 Nov meant anything was answered on 12 Nov: it was noise at K=3.

**An empty answer, and a judge you cannot overrule from an excerpt.** In the first run of 9 Nov the stored pH answer was empty, and both pH checks failed on it. The instructor's provider log shows three first calls for that scenario that each ended in a tool request, and only two follow-up calls; why the third stopped there is not established. The lesson does not need the cause: an empty answer fails every check that looks for something and passes every check that looks for an absence. `no_fake_percent` would have waved it through. Exercise 8 closes that gap. And read the `admits_gap` answer above once more. It gives no number in the part we can see, yet the judge failed it. Too strict, or right about something after the cut? The harness prints the first 300 characters of a failing answer, so the excerpt cannot tell you. That is Week 3's display truncation in a new place, and it is why Exercise 3 asks for the full answer in the log.

### Exercises

**Work on a copy.** Exercises 1, 2, 3, 5 and 8 change the harness. Copy it first and edit only the copy, so `eval_harness.py` stays as shipped:

```powershell
copy eval_harness.py my_harness.py
python my_harness.py
git status          # my_harness.py is the only new file; eval_harness.py is unchanged
```

> **macOS or Linux:** `cp eval_harness.py my_harness.py`, then `EVAL_OFFLINE=1 python3 my_harness.py`.

If you edited the original by accident, `git restore eval_harness.py` brings it back.

1. Raise K to 5 and re-run twice. How stable are the consistency rates themselves? What does that imply for choosing K in your capstone evals?
2. Add a fourth scenario for your own Week 3 agent with two hard checks and one judge check.
3. Extend the harness to write every answer, in full, and every verdict to a JSON file (`eval_log.json`). Open the file with `encoding="utf-8"`. This log is a required capstone artifact, and the capstone harness must pass with `EVAL_OFFLINE=1`; the live run is a bonus, not the test.
4. The `calc` tool from Week 4 uses `eval` with a lab-grade guard, and it is the one tool in `multi_agent.py` without an adapter. Write down two inputs that a production system would need to defend against, and sketch the defence.
5. Open the shared **Trap Bank** in the repo (`trap_bank/README.md`, scenarios TB-01 to TB-08, built from real failure modes of agricultural advisory systems and from failures measured in this course). Pick a scenario whose `fits` list contains your team's challenge and wire it into your harness as a named check. Its reference behaviour is golden data: check against the bank, never against what the model "knows". Using at least one Trap Bank scenario is a capstone requirement (briefing, section 5.5).
6. **Optional, follow-up to the Wednesday segment (local models).** You see this run live on Nov 18; afterwards, do it yourself. Install Ollama, pull a small open-weight model, and point your Week 1 agent loop at it (Ollama serves an OpenAI-compatible endpoint, so only the base URL and the model name change). Then run two of your eval scenarios against it. Expect the tool calls to be the first thing that breaks. Two questions worth a `DECISIONS.md` entry: what exactly degrades, and would an offline-capable advisory system still be worth it in a place with no reliable connectivity? This is a side quest, never your capstone's critical path.
7. Which of your capstone reference values could revise, and how would you know? Name the source, the mechanism (a reanalysis window, a new survey wave, a corrected register), and the label your tool would carry. If the answer is "none", check the response headers before you believe it.
8. Add a check named `not_empty` to every scenario and make it the first one. Then decide, and write down, what an empty answer should do to the other checks of that scenario: fail them all, or mark them as not measured? The two choices give different consistency rates from the same run.

---

## Checkpoint 5 (team)

Your team has an evaluation harness for its own system, running on `main`. "Harness" means five things you can point to:

1. one command runs it, with `EVAL_OFFLINE=1`, and it finishes without a live call;
2. at least three scenarios plus at least one hallucination or edge-case check, and at least one of them comes from the Trap Bank;
3. golden values are read from files in your repository, never typed into a check and never fetched live;
4. every check is evaluated once per answer, and every answer and verdict lands in `eval_log.json`;
5. you can name one red or unstable row and say whether it belongs to the agent, to the checker, or to the judge.

Record the evaluation design as one signed entry in your team's `DECISIONS.md`: what you check, why those checks, and the trade-off you accepted, the choice of K included (*What*, *Why*, *Trade-off*). The briefing, section 13, shows the entry format.

**Reading for this week:** Shinn, N., Cassano, F., Gopinath, A., Narasimhan, K., & Yao, S. (2023). Reflexion: Language agents with verbal reinforcement learning. *Advances in Neural Information Processing Systems, 36*, 8634-8652. https://proceedings.neurips.cc/paper_files/paper/2023/hash/1b44b878bb782e6954cd888628510e90-Abstract.html. Skim it for the loop: act, evaluate, reflect in words, try again.

**Optional:** Liu, X., Yu, H., Zhang, H., Xu, Y., Lei, X., Lai, H., Gu, Y., Ding, H., Men, K., Yang, K., Zhang, S., Deng, X., Zeng, A., Du, Z., Zhang, C., Shen, S., Zhang, T., Su, Y., Sun, H., ... Tang, J. (2024). AgentBench: Evaluating LLMs as agents. *Proceedings of the Twelfth International Conference on Learning Representations (ICLR 2024)*. https://proceedings.iclr.cc/paper_files/paper/2024/hash/e9df36b21ff4ee211a8b71ee8b7e9f57-Abstract-Conference.html
