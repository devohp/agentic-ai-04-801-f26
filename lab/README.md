# Lab Script: Agentic AI, Foundations and Applications (04-801)

Fall 2026, Mini-2, Carnegie Mellon University Africa. Instructor: Prof. Dr. BO.

This folder is the book to the labs: one chapter per week, released on the Monday of its week. The code it explains lives one folder up, in the repository root.

| Chapter | File | Available from |
|---|---|---|
| Week 0: Environment setup | [week0.md](week0.md) | Mon, 19 Oct |
| Week 1: Your first tool-using agent | [week1.md](week1.md) | Mon, 19 Oct |
| Week 2: The reasoning core (ReAct) | [week2.md](week2.md) | Mon, 26 Oct |
| Week 3: Real tools, real failures, and a framework | `week3.md` | Mon, 2 Nov |
| Week 4: Multi-agent orchestration | `week4.md` | Mon, 9 Nov |
| Week 5: The evaluation harness | `week5.md` | Mon, 16 Nov |

## How to work with it

- **Read first, then run.** Every script is printed in full in its chapter, together with the design rationale and the autopsies of real failures. Read the printed version, then run the repository version. The printed code is identical to the repository files.
- **Experiment on copies.** Many exercises ask you to delete or comment out lines. Copy the script first (`copy first_agent.py my_agent.py`) and keep the original intact for the weeks that build on it.
- **Get new chapters with `git pull`** in your repository folder each Monday.

## What you can rely on

- **Real outputs.** Every example output is a real run on the instructor's machine, dated. Where a later run superseded an earlier one, the earlier output stays in place with its date: evidence is dated, not edited.
- **Validated platform.** Windows 11, PowerShell, Python 3.14, with the package versions pinned in `requirements.txt`. Short boxes give the macOS and Linux equivalents; those boxes have not been run by the instructor, so if a step behaves differently on your machine, tell the TAs.

## Getting help

Bring setup problems to the Environment Clinic in Session 1B, or write to the TAs. Office hours are listed in the syllabus.

## Changes since release

Corrections to a chapter that is already out are listed here, newest first.

| Date | Chapter | Change |
|---|---|---|
| 21 Oct | Week 0 | Troubleshooting: the `401` row now names its three possible causes, followed by a one-line key check and the fix for each. Module 0.1 now says explicitly to replace the placeholder in the `Set-Content` line. |
