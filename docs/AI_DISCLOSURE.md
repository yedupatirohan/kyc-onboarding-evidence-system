# AI Disclosure

## Summary

This project was built with the help of an AI assistant (Claude, made by Anthropic) used through chat.
The assistant wrote most of the source code, tests and documentation in this repository. The project
owner defined the task, supplied the requirements and decisions, ran every command on their own
machine, reported the real results back, and decided what to commit.

## What the AI did

* Proposed the architecture and the 14-table schema, and wrote the SQLAlchemy models.
* Wrote the deterministic data generator, the anomaly injection, the detection rules, the validation
  checks, the evaluation code and the reproducibility check.
* Wrote the FastAPI endpoints and the pytest suite.
* Wrote the React and Vite dashboard (10 screens) and its smoke-test script.
* Wrote the documentation (README, design and rules document, this disclosure).

## What the AI could not do

* The assistant had no way to run this project's code in its own environment during most of the work.
  Code delivered as bundles was only compile-checked by the assistant. It was **the owner who ran the
  tests and the generator** and reported the real outcomes, including failures that were then fixed
  (for example, a guard test that failed in Phase 5c and was fixed by moving label-joining code into
  `app/evidence.py`).
* The assistant cannot see the owner's screen. Whether the dashboard looks and behaves correctly in a
  browser has to be confirmed by running it.
* The assistant does not have access to real customer data, real regulations or a real sanctions list.
  The risk points and country list are illustrative assumptions, stated as such in the code and docs.

## How the output was checked

* Automated tests: the pytest suite (265 passing at the last recorded run) covers rules, generator,
  models, API endpoints, evaluation maths and the no-leakage guard.
* Twelve data-quality checks run against the generated database; the clean baseline has zero violations.
* A reproducibility run executes the full pipeline twice and compares checksums.
* A frontend smoke script calls every endpoint the screens use and checks the response shape.

## Known limits of the AI-assisted result

* Precision and recall of 1.0 measure agreement between the rules and the injected labels. They do not
  prove performance on real data (see `docs/DESIGN_AND_RULES.md`, section 9).
* AI-written code can contain mistakes that tests do not cover. The rules should be reviewed by a
  compliance specialist before any real use.

## Prompt record

`PROMPT_HISTORY.md` contains the prompts sent to the AI tool, copied verbatim by the owner with a
logging script (`scripts/log_prompt.ps1`). Responses are not included. Entries record when each prompt
was logged, which can be later than when it was sent.
