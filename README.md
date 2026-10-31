<p align="center"><img src="assets/logo.svg" alt="Agentic AI: Foundations and Applications" width="640"></p>

# Agentic AI: Foundations and Applications (04-801)

Course repository for the Fall 2026 Mini-2 at Carnegie Mellon University Africa, Kigali. Instructor: Prof. Dr. BO.

This repo contains the reference implementations for every lab from Week 0 through Week 5, plus the consolidated tool kit your capstone team will build on. Every script here has been run end to end against the live APIs. The example outputs in the lab script are real runs, not staged ones, including the failures. Especially the failures.

## Quick start (Windows, PowerShell)

The course is validated on Windows 11 with Python 3.14. The full walkthrough, including short macOS and Linux notes, is the Week 0 chapter of the lab script: [lab/week0.md](lab/week0.md). The short version:

```powershell
git clone https://github.com/devohp/agentic-ai-04-801-f26.git
cd agentic-ai-04-801-f26
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# Now put your course-issued key into .env (see lab/week0.md), then:
python hello_llm.py
python check_setup.py
```

If `hello_llm.py` prints a model response and `check_setup.py` prints PASS on every line, your stack works. If not, see the troubleshooting table in the Week 0 chapter before asking anyone. That table exists because we hit every one of those errors ourselves.

**Cursor and VS Code users, one critical check:** make sure the Python interpreter is set to `.venv`, not your global Python. A script that "happens to work" on the wrong interpreter is a time bomb. This is documented in the lab script for a reason: it happened to your instructor.

## Credentials

Two services, both free for you:

1. **OpenRouter** (LLM access): model access is funded by the course. Your personal key arrives by e-mail and carries a credit limit; do not create an account of your own. A single pipeline run costs a fraction of a cent.
2. **iSDAsoil** (soil data, from Week 3): register at `https://isda-africa.com/api/registration` and read the Terms of Use. Data is CC-BY 4.0. The API uses a Bearer token that expires after 60 minutes, which is not an inconvenience but a Week 3 learning objective.

Both go into `.env`, which is gitignored. Keys never appear in code, in commits, in screenshots, or in chat messages. The Week 0 lab includes a Leak Drill so that this reflex is trained, not just stated.

## Map of the repo

| Week | File(s) | What it teaches |
|---|---|---|
| 0 | `hello_llm.py` | Environment smoke test: venv, `.env`, OpenRouter |
| 0 | `check_setup.py` | Nine setup checks, one PASS or FAIL line each |
| 1 | `first_agent.py` | Your first tool-using agent, raw SDK loop, NASA POWER |
| 2 | `react_agent.py` | ReAct from scratch: stop tokens, parsing, budget guard |
| 2 | `react_verdict.py` | ReAct over two tools, ending in a validated JSON verdict |
| 3 | `soil_tool.py` | Anatomy of a robust tool: auth, timeouts, snapshot fallback |
| 3 | `langchain_agent.py` | Same tools, framework loop: what changes and what must not |
| 3 | `field_notes_tool.py` | Retrieval is just another tool (Chroma, in-memory) |
| 4 | `multi_agent.py` | Data, Analysis, Report: role separation enforced by tool access |
| 5 | `eval_harness.py` | Three-layer evals: hard checks, repetition, LLM-as-judge |
| Capstone | `tools.py` | The four course tools, consolidated: `weather`, `soil`, `calc`, `search_notes` |
| Data | `weather_snapshot.json` | Frozen weather reference values (see below) |
| Capstone | `data/` | The curated capstone dataset: fields, seasons, weather, NDVI, field notes, agronomy snippets. Start with [data/README.md](data/README.md) |
| Capstone | `trap_bank/` | Shared evaluation scenarios with reference behaviour, see [trap_bank/README.md](trap_bank/README.md) |
| Utility | `build_snapshot.py` | Instructor tool that pre-warms the offline soil snapshot |
| All | `lab/` | The lab script, one chapter per week |

The scripts are laid out flat, not in week folders, so that they match the lab script line by line and can import each other (`multi_agent.py` and `eval_harness.py` reuse `soil_tool.py`). The authoritative walkthrough for every file is the lab script in [lab/](lab/).

## The snapshot fallback

`soil_snapshot.json` is committed on purpose. It is the offline fallback for the soil tool: if the live iSDAsoil call fails (timeout, expired token, no WiFi), the tool serves cached data and says so, loudly and honestly, in its output label. If neither the live call nor the snapshot works, the tool raises a plain-language error instead of inventing data. That design decision is the architectural answer to a failure mode you will meet, dissected, in the Week 2 and Week 5 autopsies.

The snapshot contains only public CC-BY 4.0 soil data for the course reference points. It contains no credentials.

## First run notes

- Chroma downloads its embedding model (about 80 MB) on the first retrieval call and caches it locally. Do this once on a good connection, ideally in Week 0, not five minutes before a demo.
- The version pins in `requirements.txt` are the exact versions of the instructor validation run. Agent frameworks move fast; mid-course upgrades are a class decision, not an individual one.

## Reference values (frozen 27 Sep 2026)

The evaluation harness and the capstone rubric use golden values from the
snapshot files in this repository, never from a live call. One of the two
reasons was learned the hard way.

| Point | Window | Value | Source |
|---|---|---|---|
| Kigali (-1.94, 30.06) | 1 to 7 Jul 2026 | 7.03 mm rain over 7 days | NASA POWER, MERRA2 |
| Nairobi (-1.29, 36.82) | 1 to 7 Jul 2026 | 3.85 mm rain over 7 days | NASA POWER, MERRA2 |
| Kigali (-1.94, 30.06) | topsoil 0 to 20 cm | pH 6.7 (90% CI 6.2 to 7.2) | iSDAsoil |

The rainfall values were first pulled on 11 Aug 2026 and read 0.9 mm and
5.76 mm. NASA POWER fills its most recent weeks with a provisional
near-real-time product (GEOS-IT) and replaces them when the MERRA-2
reanalysis catches up. By 27 Sep 2026 the same query returned the values
above. Nothing was wrong with the API; our test was wrong to treat a live
number as frozen. Every weather tool in this repository now appends the
POWER source to its output, `weather_snapshot.json` is the only place a
golden value may come from, and `EVAL_OFFLINE=1 python eval_harness.py`
runs the harness against the snapshot alone. Regenerate the snapshot only
on purpose, with a note in this table.

## Model pin and provider variance

`deepseek/deepseek-chat` is a moving alias; the course pins
`deepseek/deepseek-chat-v3-0324` so that every laptop sees the same model.
If the pinned model is deprecated, change one string in seven files, then
re-run `eval_harness.py` before anything else.

The model is served by several providers behind the OpenRouter gateway,
and they behave differently. Measured on 27 Sep 2026: one provider
rejects a request that carries no `max_tokens`; another ignores the
`stop` sequence entirely (0 of 5 stops honoured), so the ReAct model
wrote invented Observations and a Final Answer in a single message. Both
are handled in code: every call sets `max_tokens=1024`, and the ReAct loop
parses the first Action and discards everything after it. Providers are
deliberately not pinned; the code has to survive all of them.

## Data sources and attribution

- **iSDAsoil**: Miller, M. A. E., Shepherd, K. D., Kisitu, B., & Collinson, J. (2021). iSDAsoil: The first continent-scale soil property map at 30 m resolution. *PLOS Biology*, 19(11), e3001441. https://doi.org/10.1371/journal.pbio.3001441. Data: CC-BY 4.0.
- **NASA POWER**: Prediction Of Worldwide Energy Resources, NASA Langley Research Center. https://power.larc.nasa.gov. Open access, no key required.
- **Capstone dataset** (`data/`): synthetic and calibrated; real NASA POWER weather and iSDAsoil topsoil, yields calibrated against EPAR summary statistics (BSD-3-Clause notice in [data/README.md](data/README.md)). Sources and licences per layer are listed there.
- Synthetic field notes in `field_notes_tool.py` and `tools.py` are course material, invented for teaching. Any resemblance to an actual armyworm is fully intended.

## Course use

Material for 04-801, Fall 2026, CMU-Africa. Data sources retain their own licenses (see above).
