// RFC 9728, at the bare address some clients try first (utils/oauthDocuments.ts).
export default defineEventHandler((event) => relayOAuthDocument(event, '/oauth/protected-resource'))
