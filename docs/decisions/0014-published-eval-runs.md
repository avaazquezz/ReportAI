# 0014. Paid eval runs are published, and the site may quote only them

- **Status:** Accepted
- **Date:** 2026-11-25 (published runs); the golden-set gate dates from 2026-10-01
- **Evidence:** `PROJECT_ROADMAP.md` §3 ("Golden-set eval suite + structured cost/latency logging
  from the first commit") and the third log entry of 2026-11-25; commits `0fbcf67` (the published
  runs) and `8bd8988` (a test that fails when the case study's figures drift);
  `backend/tests/test_case_study_figures.py`; `.github/workflows/eval.yml`

## Context

Extraction quality is the product. Its figures appear on the landing and in the case study, and a
number nobody can trace is a claim, not evidence. The evals call real AI providers and cost money.

## Decision

- Two evals grade the system against real providers: the golden set (extraction, gate: at least
  90 % of fields right and no field invented) and an assistant using the MCP server.
- They run by hand (`make eval`, or the manual *Eval* workflow), never on a push.
- Every published run is kept in `docs/evals/` exactly as the harness writes it: commit, model,
  every verdict, tokens and cost.
- The landing and the case study may quote only those files: `test_case_study_figures.py` fails
  when a page and the latest published run disagree.

## Alternatives considered

- (Reconstructed.) **Running the evals in CI on every push.** Every push would spend money and
  depend on an outside service.
- (Reconstructed.) **Figures typed into the pages by hand.** They drift from what was measured.

## Consequences

- Changing a figure on the site means publishing a run first.
- One run per provider is published; the [Evaluations](../evals.md) page says how much runs vary.

## Revisit when

Real (anonymised) field notes exist to add to the set.
