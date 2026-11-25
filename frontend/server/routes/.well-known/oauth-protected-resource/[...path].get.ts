// RFC 9728 §3.1: the MCP server's document, at /.well-known/oauth-protected-resource/api/mcp, which
// its 401 points to (utils/oauthDocuments.ts). There is one protected resource, whatever the path.
export default defineEventHandler((event) => relayOAuthDocument(event, '/oauth/protected-resource'))
