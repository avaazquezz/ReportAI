# 0009. Companies bring their own AI keys, from a closed provider list

- **Status:** Accepted
- **Date:** 2026-11-17
- **Evidence:** `PROJECT_ROADMAP.md` log entry of 2026-11-17 ("Hosted service: each company brings
  its own AI provider key …"); commits `253dc5f` (company AI keys) and `937aba3` (the panel for it);
  the docstrings of `backend/app/services/ai_providers.py` and `backend/app/services/company_ai.py`

## Context

On the hosted service the platform paid for every company's AI, so one trial account could exhaust
the daily spend breaker for everyone. Letting companies enter their own provider raises a second
risk: the worker would call whatever address a company typed, with the company's key.

## Decision

- On the hosted service, each company enters its own provider, model and key. The providers come
  from a **closed list with fixed base URLs** (`EXTRACTION_PROVIDERS`, `TRANSCRIPTION_PROVIDERS`);
  a provider joins it once it passes the golden set.
- The platform's key serves only companies the super admin marks `platform_ai` (the live demo).
  There is no fallback: a company without its own key can't start reports.
- The spend breaker and the plans' daily caps count only calls the platform paid for
  (`execution_logs.platform_key`).
- A self-hosted server keeps its installation-wide settings with a free base URL, unchanged.

## Alternatives considered

- **A free base URL for every company.** Rejected in the log: it would let any company point the
  worker at internal addresses (SSRF).
- **The platform's key as a fallback.** Rejected: the platform would keep paying for other
  companies' AI.

## Consequences

- The settings are read on every use, never cached, because the API and the worker are separate
  processes and a changed key must reach the very next report.
- The *test* button for a key is rate-limited per company, so it can't check stolen keys in bulk.
- The privacy policy names the company's chosen provider as a processor of its data (commit
  `c5bf228`).
- See [AI providers](../how-it-works/ai-providers.md).

## Revisit when

A company needs a provider that isn't on the list: add it after it passes the golden set.
