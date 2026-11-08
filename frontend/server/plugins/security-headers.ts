import { randomBytes } from 'node:crypto'

// Every response gets the security headers; every rendered page (server-rendered or the service
// worker's shell) gets a Content-Security-Policy with a nonce of its own (utils/securityHeaders.ts).
export default defineNitroPlugin((nitroApp) => {
  // For builds only. Vite's development server writes inline scripts of its own and evaluates code,
  // and Nuxt DevTools shows its panel in a same-origin iframe, which X-Frame-Options: DENY blocks.
  if (import.meta.dev) return

  nitroApp.hooks.hook('request', (event) => {
    setResponseHeaders(event, SECURITY_HEADERS)
    // Behind Traefik or Caddy the request arrives as HTTP: the proxy says what the browser used.
    // A forged value only gets this header sent over plain HTTP, where browsers ignore it.
    if (getRequestProtocol(event, { xForwardedProto: true }) === 'https') {
      setResponseHeader(event, 'Strict-Transport-Security', STRICT_TRANSPORT_SECURITY)
    }
  })

  nitroApp.hooks.hook('render:html', (html, { event }) => {
    const nonce = randomBytes(16).toString('base64')
    // Only what Nuxt writes itself: the head and the closing tags (payload, entry). Never the app's
    // HTML (body, and bodyPrepend, which carries what is teleported to <body>): a script that slipped
    // into a rendered value must stay unsigned, so the browser refuses it.
    html.head = html.head.map((chunk) => signScripts(chunk, nonce))
    html.bodyAppend = html.bodyAppend.map((chunk) => signScripts(chunk, nonce))
    setResponseHeader(event, 'Content-Security-Policy', contentSecurityPolicy(nonce, useRuntimeConfig(event).public.apiBase))
  })

  // Which framework serves the panel is nobody's business.
  nitroApp.hooks.hook('render:response', (response) => {
    if (response.headers) delete response.headers['x-powered-by']
  })
})
