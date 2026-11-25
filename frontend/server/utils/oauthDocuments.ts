// The OAuth discovery documents an AI client reads at the site's root (RFC 8414, RFC 9728), relayed
// from the API, which writes them (backend/app/api/oauth.py): the issuer is the panel's origin, and
// the API lives under /api, so the root /.well-known/ addresses are the panel's to answer. Relaying
// them here works the same behind Traefik, Caddy, in the e2e stack and in development, with no proxy
// rule to keep in step. With OAuth off the API answers 404, and so does the panel.
import type { H3Event } from 'h3'

export type OAuthDocument = '/oauth/metadata' | '/oauth/protected-resource'

// An API that doesn't answer in this long is down for the client too: say so, don't hang with it.
export const RELAY_TIMEOUT_MS = 5000

/** Where the panel's server asks the API for `document`: the internal base inside Docker
 * (`apiBaseServer`), else the public one, which is absolute in development. A relative public base
 * (/api) with no internal one can't be reached from here: null, a misconfiguration. */
export function oauthDocumentUrl(apiBaseServer: string, apiBase: string, document: OAuthDocument): string | null {
  const base = apiBaseServer || apiBase
  if (!URL.canParse(base)) return null
  return `${base.replace(/\/+$/, '')}${document}`
}

/** Whether `path` (what follows /.well-known/oauth-protected-resource/) names this site's MCP
 * server, as the API's 401 points to it: /api/mcp behind the proxy, /mcp in development, where the
 * public base is the API's own address (utils/mcpConnection.ts builds the same URL). */
export function isMcpResourcePath(path: string, apiBase: string): boolean {
  const mcp = new URL(`${apiBase.replace(/\/+$/, '')}/mcp`, 'https://panel.invalid').pathname
  return `/${path.replace(/^\/+|\/+$/g, '')}` === mcp
}

/** A relay that can't be made: the status the panel answers with, and why (also logged). */
export class RelayFailure extends Error {
  constructor(
    readonly statusCode: 500 | 502,
    message: string
  ) {
    super(message)
  }
}

export interface RelayedDocument {
  status: number
  contentType: string | null
  cacheControl: string | null
  body: string
}

/** The API's answer for `document`, whatever its status; RelayFailure (500) when there is no
 * address to ask, (502) when the API doesn't answer in time or at all. */
export async function fetchOAuthDocument(
  apiBaseServer: string,
  apiBase: string,
  document: OAuthDocument,
  timeoutMs = RELAY_TIMEOUT_MS
): Promise<RelayedDocument> {
  const url = oauthDocumentUrl(apiBaseServer, apiBase, document)
  if (!url) {
    console.error(`OAuth documents: no address to reach the API from the panel's server (public base "${apiBase}"): set NUXT_API_BASE_SERVER`)
    throw new RelayFailure(500, 'Set NUXT_API_BASE_SERVER: the panel can not reach the API to relay its OAuth documents')
  }
  try {
    // One deadline for the answer and its body: the signal also cuts a body that stalls.
    const response = await fetch(url, { headers: { Accept: 'application/json' }, signal: AbortSignal.timeout(timeoutMs) })
    return {
      status: response.status,
      contentType: response.headers.get('content-type'),
      cacheControl: response.headers.get('cache-control'),
      body: await response.text()
    }
  } catch (cause) {
    console.error(`OAuth documents: the API at ${url} did not answer`, cause)
    throw new RelayFailure(502, 'The API did not answer')
  }
}

export async function relayOAuthDocument(event: H3Event, document: OAuthDocument): Promise<string> {
  const config = useRuntimeConfig(event)
  let relayed: RelayedDocument
  try {
    relayed = await fetchOAuthDocument(config.apiBaseServer, config.public.apiBase, document)
  } catch (error) {
    if (error instanceof RelayFailure) throw createError({ statusCode: error.statusCode, statusMessage: error.message })
    throw error
  }
  setResponseStatus(event, relayed.status)
  setResponseHeaders(event, {
    // The API's own type: its JSON documents, or the error it answered with.
    'Content-Type': relayed.contentType ?? 'application/octet-stream',
    'Cache-Control': relayed.cacheControl ?? 'no-store',
    // Public documents: a client running in a browser (the MCP Inspector) reads them too.
    'Access-Control-Allow-Origin': '*'
  })
  return relayed.body
}
