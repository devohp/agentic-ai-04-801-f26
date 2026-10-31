# Trap Bank

A shared set of evaluation scenarios built from failure modes that agricultural advisory systems
show in the field, and from failures we measured in this course. Every team uses at least one
scenario that fits its challenge (briefing, section 5.5).

## What is in this folder

| File | Content |
|---|---|
| `trap_bank.json` | Eight scenarios: input, reference behaviour, must and must-not lists, suggested machine checks |
| `product_reference.csv` | The product list that scenario checks run against. **All brand names are fictional.** CAN, DAP, Urea, NPK and agricultural lime are generic product classes. |
| `fixtures/autopsy10_provider_ignores_stop.txt` | A model reply that ignores the stop sequence (input for TB-03). Its numbers are false on purpose. |

## How to use a scenario

1. Pick a scenario whose `fits` list contains your challenge.
2. Turn the `input` into a test case in your harness. Fields named `gloss_for_instructors_only_not_for_the_model`
   are translations for humans; do not pass them to your system.
3. Encode the `reference_behaviour` as checks. `machine_checks` are suggestions, not a complete test:
   most scenarios also need a human or LLM-as-judge look at the `must` and `must_not` lists.
4. Run with `EVAL_OFFLINE=1`. Golden values come from files shipped in this repository
   (`weather_snapshot.json`, `soil_snapshot.json`, `data/`), never from a live call.
5. Log every answer and verdict to `eval_log.json`.

## The scenarios

| ID | Title | Category | Fits |
|---|---|---|---|
| TB-01 | The word the glossary does not know: amiwomu | local names, code-switching and phonetic spellings | B, A |
| TB-02 | The tool argument that does not exist (Autopsy 9) | tool use: invented argument | A, B, C |
| TB-03 | The provider that ignores stop (Autopsy 10) | parsing: fabricated observations and copied source labels | A, B, C |
| TB-04 | Instructions hidden in a retrieved document | indirect prompt injection | B, A, C |
| TB-05 | The product that is not an option | unavailable or inappropriate product | B, C |
| TB-06 | Advice on too little information | insufficient information | B, C |
| TB-07 | Look-alike causes the evidence cannot separate | look-alike diagnoses | A, B |
| TB-08 | A drought note in a week of heavy rain | contradiction inside one record | A, B, C |

## Ground rules

- The reference behaviours are golden data. If you believe one is wrong, tell the TAs; do not edit it quietly.
- Products are checked against `product_reference.csv`, never against the model's memory. A product that is
  not in the list does not exist for your system.
- Nothing in this folder is advice for real farms. The product list is fictional by design.
