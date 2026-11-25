// The OAuth discovery documents an AI client reads at the site's root (RFC 8414, RFC 9728), relayed
// from the API, which writes them (backend/app/api/oauth.py): the issuer is the panel's origin, and
// the API lives under /api, so the root /.well-known/ addresses are the panel's to answer. Relaying
// them here works the same behind Traefik, Caddy, in the e2e stack and in development, with no proxy
// rule to keep in step. With OAuth off the API answers 404, and so does the panel.
import type { H3Event } from 'h3'

export type OAuthDocument = '/oauth/metadata' | '/oauth/protected-resource'

/** Where the panel's server asks the API for `document`: the internal base inside Docker
 * (`apiBaseServer`), else the public one, which is absolute in development. A relative public base
 * (/api) with no internal one can't be reached from here: null, a misconfiguration. */
export function oauthDocumentUrl(apiBaseServer: string, apiBase: string, document: OAuthDocument): string | null {
  const base = apiBaseServer || apiBase
  if (!URL.canParse(base)) return null
  return `${base.replace(/\/+$/, '')}${document}`
}

export async function relayOAuthDocument(event: H3Event, document: OAuthDocument): Promise<string> {
  const config = useRuntimeConfig(event)
  const url = oauthDocumentUrl(config.apiBaseServer, config.public.apiBase, document)
  if (!url) {
    throw createError({ statusCode: 500, statusMessage: 'Set NUXT_API_BASE_SERVER: the panel can not reach the API to relay its OAuth documents' })
  }
  const response = await fetch(url, { headers: { Accept: 'application/json' } })
  setResponseStatus(event, response.status)
  setResponseHeaders(event, {
    'Content-Type': 'application/json',
    'Cache-Control': response.headers.get('cache-control') ?? 'no-store',
    // Public documents: a client running in a browser (the MCP Inspector) reads them too.
    'Access-Control-Allow-Origin': '*'
  })
  return await response.text()
}
