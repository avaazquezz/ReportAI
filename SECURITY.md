# Security

## Reporting a vulnerability

Report it privately through GitHub: **Security → Report a vulnerability** on this repository.
Please don't open a public issue. You'll get an answer within 72 hours.

## How fixes reach installations

ReportAI runs on each company's own server, so a fix only protects a company once **its
installation is updated**. Keeping an installation updated is the job of whoever installed and
maintains it (see [docs/maintenance.md](docs/maintenance.md)):

1. A fix is released as a new version (a GitHub release, `vX.Y.Z`).
2. The advisory is published as a GitHub Security Advisory, and listed in
   [`security/advisories.json`](security/advisories.json) with the versions it affects and the
   version that fixes it.
3. Every installation checks that file and the latest release (at most every 6 hours), and the
   panel shows its administrator a red notice when an advisory affects the version it runs.
4. The maintainer runs `reportai update` on the server.

## `security/advisories.json`

```json
{
  "advisories": [
    {
      "id": "RAI-2026-001",
      "title": "One line saying what is affected",
      "severity": "low | medium | high | critical",
      "introduced": "0.2.0",
      "fixed_in": "0.3.1",
      "url": "https://github.com/avaazquezz/ReportAI/security/advisories/GHSA-xxxx-xxxx-xxxx"
    }
  ]
}
```

An installation running a version `v` is affected when `introduced ≤ v < fixed_in`
(`introduced` defaults to every version before `fixed_in`).
