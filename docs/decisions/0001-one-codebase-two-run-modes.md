# 0001. One codebase for the hosted service and self-host

- **Status:** Accepted
- **Date:** 2026-10-01 (single-tenant mode and the installer); the rule "self-host must not change"
  restated on 2026-11-06
- **Evidence:** `PROJECT_ROADMAP.md` §3 ("One codebase for the hosted service and self-host;
  self-host must not change") and the 2026-11-06 log entry; commits `5356d1f` (installer) and
  `c08e5e8` (settings in the panel, `SINGLE_TENANT`)

## Context

ReportAI runs two ways: as a hosted service where several companies share one installation, and
on a company's own server, where its data never leaves its infrastructure. Both need the same
pipeline, panel and field app.

## Decision

One codebase and one set of images. `SINGLE_TENANT` (`backend/app/core/config.py`) switches the
few behaviours that differ:

| Concern | `SINGLE_TENANT=false` (hosted) | `SINGLE_TENANT=true` (self-host) |
|---|---|---|
| Who creates companies | The super admin | The setup wizard, once, behind a one-time code |
| Who runs the installation's settings | `super_admin` | The company's `tenant_admin` (`require_instance_admin`) |
| AI keys | Each company's own, from a closed list ([0009](0009-company-ai-keys-closed-provider-list.md)) | The installation's, with a free base URL |
| Plans, quotas, spend caps | Applied | None (`backend/app/services/plans.py`) |
| Company deletion from the panel | Available | 404: the company is deleted by uninstalling |

Every change keeps a self-hosted server's behaviour: new flags default to off, new columns get
neutral defaults so existing rows stay valid.

## Alternatives considered

- **Two products**, a hosted service and a separate self-host edition. Rejected in the roadmap:
  "two products would double the maintenance".

## Consequences

- Hosted-only features ship behind flags that are off on a company's server: `MCP_OAUTH_ENABLED`,
  `SIGNUP_ENABLED`, `PUBLIC_DEMO_ENABLED`, and `AUDIO_RETENTION_DAYS` (0 = keep).
- Some combinations are refused at boot (signup or the live demo with `SINGLE_TENANT=true`).
- A self-hosted server updates only when its maintainer runs `reportai update`, so every migration
  must work from any earlier release.

## Revisit when

The two modes need behaviour that can't be expressed as a default-off flag.
