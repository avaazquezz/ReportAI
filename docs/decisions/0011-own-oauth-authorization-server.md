# 0011. ReportAI is its own OAuth 2.1 authorization server

- **Status:** Accepted; supersedes "its own bearer-key auth, not the SDK's OAuth" (2026-11-18)
- **Date:** 2026-11-25
- **Evidence:** `PROJECT_ROADMAP.md`, last log entry of 2026-11-25; commits `e5fe342` ("sign AI
  assistants in with OAuth 2.1 behind MCP_OAUTH_ENABLED"), `9151ce6` (discovery documents and
  consent in the panel) and `d4c4f7a` (on in the hosted service)

## Context

claude.ai and ChatGPT connect to remote MCP servers through OAuth; their option to send a custom
header (an API key) is a beta not every organisation has. On 2026-11-18 there was no authorization
server to discover, so the MCP server took API keys only.

## Decision

The API hosts an OAuth 2.1 authorization server behind `MCP_OAUTH_ENABLED` (off by default; on in
the hosted service), built on the MCP SDK's handlers:

- registration by Client ID Metadata Documents (the specification's recommended way; fetched with
  SSRF guards and cached) and by dynamic registration (deprecated, kept for compatibility);
- consent in the panel, PKCE S256, single-use codes;
- opaque tokens stored as hashes and bound to this server (RFC 8707);
- rotating refresh tokens whose reuse revokes the grant;
- at most 10 connected apps per person.

The discovery documents are served by the panel relaying the API, instead of new proxy rules.

## Alternatives considered

- **An external identity provider.** Rejected in the log: one more data processor, and a
  self-hosted server can't depend on it.
- **Proxy rules for `/.well-known/`.** Rejected: the panel's relay works the same behind Traefik,
  Caddy, in the end-to-end stack and in development.

## Consequences

- API keys keep working exactly as before, with or without OAuth: `/mcp` tells the credentials
  apart by prefix.
- The issuer is `FRONTEND_ORIGIN`, which must then be HTTPS; the settings refuse anything else
  outside localhost.
- The server fetches documents from addresses strangers choose, the one place it does: the fetch is
  fenced, rate-limited and made with no transaction open
  ([SSRF guards](../how-it-works/mcp-and-oauth.md#ssrf-guards-on-the-metadata-fetch)).
- Deliberate ceilings are labelled in the code (`ponytail:`): a reused authorization code doesn't
  revoke its tokens; DNS is resolved twice; fetch slots are per process; a stale document is served
  for at most 7 days.

## Revisit when

A self-hosted company asks for OAuth sign-in, or the MCP specification changes its registration
recommendation.
