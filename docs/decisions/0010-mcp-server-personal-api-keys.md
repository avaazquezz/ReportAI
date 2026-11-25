# 0010. An MCP server for AI assistants, with personal API keys

- **Status:** Accepted; its authentication extended by [0011](0011-own-oauth-authorization-server.md)
- **Date:** 2026-11-18; the PDF link and key expiry added on 2026-11-25
- **Evidence:** `PROJECT_ROADMAP.md` log entries of 2026-11-18 (personal keys, read-only tools plus
  drafts) and 2026-11-25 (the PDF as a 10-minute link, expiring keys; "Agent and MCP" without a
  public REST API); commits `9e13199` (MCP server), `439a75e` (sign out everywhere revokes keys) and
  `38feeb6` (PDF link)

## Context

People want to ask their AI assistant about their reports and start drafts from a conversation.
An assistant is a client with a model in a loop: it can be talked into things (prompt injection)
and fires requests faster than a person.

## Decision

- A remote MCP server over Streamable HTTP at `/mcp`, stateless, inside the API.
- **Personal** API keys: a key acts as its person, with their role, through the panel's own checks
  (`visible_report`, `own_reports_only`), so it never sees or does more than they can, and it stops
  working while they can't sign in.
- Tools are read-only plus starting a draft that a person reviews. Nothing approves or sends.
- A finished report's PDF is handed over as a 10-minute sealed download link, plus the file
  embedded when it is under 100 KB.

## Alternatives considered

- **Company-wide keys.** Rejected in the log: a key would see more than its holder.
- **A feature flag on self-host.** Rejected: with no keys the endpoint is inert, and making a key is
  the opt-in, person by person.
- **A per-IP limit on failed keys.** Rejected: 256 random bits can't be guessed, and each failure is
  one indexed lookup.
- **The PDF embedded only.** The first choice; a link exposes less than the whole PDF in the
  conversation, and AI clients differ in what they do with an embedded PDF.
- **A public REST API with the same keys.** Deferred: a public API is a versioned contract to keep;
  it comes back when someone needs to integrate without an assistant.

## Consequences

- Signing someone out everywhere also revokes their keys, since a stolen session may have made
  them.
- A retried draft call may create a second draft, bounded by 20 drafts per person per hour; a
  person reviews each.
- Keys can expire after 30, 90 or 365 days; the API's default and every existing key stay "never",
  so nothing that worked stops.
- The server tells the model that report contents are data, never instructions, and an eval tests
  prompt injection and isolation ([Evaluations](../evals.md)).
- See [MCP server and OAuth](../how-it-works/mcp-and-oauth.md).

## Revisit when

Someone needs to integrate ReportAI without an AI assistant (the public API), or a user asks to
complete a draft's missing fields from the assistant (deferred in the roadmap).
