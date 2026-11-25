// RFC 8414: how an AI client signs a person in (utils/oauthDocuments.ts).
export default defineEventHandler((event) => relayOAuthDocument(event, '/oauth/metadata'))
