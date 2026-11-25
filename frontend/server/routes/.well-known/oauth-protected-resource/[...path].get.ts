// RFC 9728 §3.1: the MCP server's document, at /.well-known/oauth-protected-resource/api/mcp, which
// its 401 points to (utils/oauthDocuments.ts). There is one protected resource: any other path
// names none, and is a 404.
export default defineEventHandler((event) => {
  if (!isMcpResourcePath(getRouterParam(event, 'path') ?? '', useRuntimeConfig(event).public.apiBase)) {
    throw createError({ statusCode: 404, statusMessage: 'No such protected resource' })
  }
  return relayOAuthDocument(event, '/oauth/protected-resource')
})
