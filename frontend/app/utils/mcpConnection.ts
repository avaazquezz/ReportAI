// How an AI assistant reaches ReportAI's MCP server (backend/app/mcp_server), for the panel's
// /admin/api-keys page (tests/mcpConnection.test.ts).

/**
 * The MCP server's full address. `apiBase` is the panel's runtime `public.apiBase`: absolute on a
 * self-host or in dev (`http://localhost:8000`), relative in production (`/api`), in which case it
 * is resolved against `origin`, the page's own (`window.location.origin`).
 */
export function mcpUrl(apiBase: string, origin: string): string {
  return new URL(`${apiBase.replace(/\/+$/, '')}/mcp`, origin).href
}

/** The one command that adds ReportAI to Claude Code, sending `key` on every request. */
export function claudeCodeCommand(url: string, key: string): string {
  return `claude mcp add --transport http reportai ${url} --header "Authorization: Bearer ${key}"`
}
