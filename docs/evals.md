# Evaluations

ReportAI is graded by two paid evals that call real AI providers. They are run by hand
(`make eval`, never in CI) and every published run is kept here as the JSON the harness wrote,
with the commit it graded, the model, every verdict and what it cost.

## Results

| Run | What | Model | Result | Invented | Cost |
|---|---|---|---|---|---|
| [2026-11-25 golden set](evals/2026-11-25-golden-anthropic.json) | Extraction, 83 cases / 646 fields | `claude-sonnet-5` (Anthropic) | **99.7 %** fields right (2 wrong) | **0** | $0.79 |
| [2026-11-25 golden set](evals/2026-11-25-golden-openai.json) | Extraction, 83 cases / 646 fields | `gpt-6.1-terra` (OpenAI) | **97.5 %** fields right (12 wrong, 4 missed) | **0** | $0.14 |
| [2026-11-25 MCP agent](evals/2026-11-25-mcp-agent.json) | An assistant using the MCP server, 7 cases | `claude-opus-5-5` | **7 / 7** cases passed | — | $0.32 |

All three graded commit `8fcc1f3`. Both providers clear the gate (≥ 90 % of fields right, no field
invented), which is what lets a company pick either on the hosted service
(`backend/app/services/ai_providers.py`). OpenAI's weak spot is table rows (`list[object]`: 44 of 55
right against 55 of 55 for Claude); the per-type and per-field tables are in each JSON.

## Golden set: extraction

`backend/tests/eval/test_golden_set.py`, cases from `backend/tests/eval/golden.py`.

- **Generated, not hand-written.** Every message is assembled from the values it must yield, so the
  ground truth is known by construction: 35 site visits, 20 meetings, 20 incidents and 8 older
  hand-written cases (the incidents in English, the rest in Spanish), with relative dates ("ayer", "next Tuesday") anchored
  to a fixed moment. Synthetic data only.
- **Fields left out on purpose.** Each case omits some fields. A value where the message said nothing
  is graded **invented** — the failure a formal document can't afford — and the gate allows none.
- **Graded field by field:** correct, wrong, missed (said but not extracted) or invented. Names
  and short phrases match give or take an article or a typo; a sentence matches when 75 % of its
  key terms are there (`_text_matches` in `golden.py`).
- **The production path.** Each case runs the graph's own extract → validate loop, with the same
  retry limit; a provider error is retried as the job queue would and shown in the report.

## MCP agent: an assistant using ReportAI

`backend/tests/eval/test_mcp_agent.py`: a real Claude model, the real MCP server over HTTP, two
companies' reports in a test database. Each case has a deterministic check (no model grades another):

- **Tool choice:** it finds what was asked with the read tools and answers from them.
- **The document:** asked for a report's PDF, it fetches it and hands over the download link.
- **The one write:** asked for a draft, exactly one draft of the right type, none otherwise.
- **Prompt injection:** a report whose transcript orders the assistant around changes nothing.
- **Isolation:** another company's reports, and a technician's colleague's, never reach a tool
  result or the answer (a canary string is searched for in both).

## Reproducing a run

From `backend/`, with the compose `postgres` up and a provider key in `.env`:

```bash
export POSTGRES_HOST=localhost UV_ENV_FILE=../.env
# Golden set with the installation's model (EXTRACTION_* or the panel's settings):
EVAL_REPORT=../docs/evals/<date>-golden-anthropic.json uv run --extra dev pytest -m eval -s tests/eval/test_golden_set.py
# The same set against a provider of the hosted service's list, called as a company's own key would be:
EVAL_COMPANY_PROVIDER=openai EVAL_COMPANY_API_KEY=... EVAL_REPORT=../docs/evals/<date>-golden-openai.json \
  uv run --extra dev pytest -m eval -s tests/eval/test_golden_set.py
# The assistant eval (ANTHROPIC_API_KEY; EVAL_AGENT_MODEL picks the model):
EVAL_REPORT=../docs/evals/<date>-mcp-agent.json uv run --extra dev pytest -m eval -s tests/eval/test_mcp_agent.py
```

`EVAL_REPORT` records the checkout's commit, so run from a clean checkout of the commit you mean to
publish. If a run on a desktop crashes inside OpenSSL with several requests in flight, set
`EVAL_CONCURRENCY=1`.

## Reading the numbers

- One run per provider: a model's answers vary between runs. Earlier runs, before results were
  kept here, landed within about a point of these (OpenAI: 98.3 / 98.0 / 98.1 % on 2026-11-17).
- Synthetic messages, not real field notes: the set measures extraction against known answers, not
  how real technicians talk. That gap closes with real (anonymised) notes, when there are users.
- The landing and the case study quote these files; `backend/tests/test_case_study_figures.py`
  fails if a page and the latest published run disagree.
