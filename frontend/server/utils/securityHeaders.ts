// The security headers the panel's server sends (plugins/security-headers.ts), in the hosted
// service and on a company's own server alike. On the latter, Caddy (infra/install/Caddyfile) sets
// X-Content-Type-Options, X-Frame-Options and Referrer-Policy for the whole site too, overwriting
// these: keep the three equal there. Plain values, so tests/securityHeaders.test.ts checks them.

/** Sent with every response: pages, the build's files, the service worker. */
export const SECURITY_HEADERS: Record<string, string> = {
  // Never guess a type: a file served as an image is never run as a script.
  'X-Content-Type-Options': 'nosniff',
  // frame-ancestors (in the CSP) is the current form; this one covers browsers that predate it.
  'X-Frame-Options': 'DENY',
  'Referrer-Policy': 'strict-origin-when-cross-origin',
  // A page the panel opens can't reach back into it through window.opener.
  'Cross-Origin-Opener-Policy': 'same-origin',
  // The app records with the microphone (camera kept for photos); nothing else a page could ask for.
  'Permissions-Policy': 'camera=(self), microphone=(self), geolocation=(), payment=(), usb=()'
}

// Over HTTPS only (browsers ignore it over plain HTTP). One year, this host alone: a company's other
// subdomains are none of this installation's business.
export const STRICT_TRANSPORT_SECURITY = 'max-age=31536000'

/** The Content-Security-Policy of a page whose own scripts carry `nonce`. `apiBase` is the public
 * API base: a relative one (/api, as deployed) is this same origin; an absolute one (local
 * development, a separate API host) adds its origin to what the page may call. */
export function contentSecurityPolicy(nonce: string, apiBase: string): string {
  const api = URL.canParse(apiBase) ? ` ${new URL(apiBase).origin}` : ''
  return [
    "default-src 'self'",
    // Script files from this origin only, and inline scripts only if this very response wrote
    // them: one slipped into a rendered value doesn't carry the nonce, so it never runs.
    `script-src 'self' 'nonce-${nonce}'`,
    // Vuetify's theme and component styles, GSAP's animations. Inline style can't run code.
    "style-src 'self' 'unsafe-inline'",
    // Photos and recordings are shown through blob: URLs, after fetching them from the API.
    "img-src 'self' data: blob:",
    "media-src 'self' blob:",
    // PDF previews: a blob: URL in an iframe.
    'frame-src blob:',
    `connect-src 'self'${api}`,
    "worker-src 'self'",
    // No plugins, but for that same PDF preview: Safari draws a framed PDF as a plugin document,
    // which this governs [unverified: no Safari to test on]. Only this app's own code makes blob: URLs.
    'object-src blob:',
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'"
  ].join('; ')
}

// Elements whose content is text, not markup: a "<script" inside them is never a tag.
const RAW_TEXT = new Set(['script', 'style', 'noscript', 'title', 'textarea'])

/** Adds the nonce to every <script> tag in a piece of HTML the renderer wrote itself. It reads the
 * HTML as tags, not as text: "<script" inside an attribute value (unhead leaves < and > in them), a
 * comment or another element's text is not a tag, and signing it would turn harmless text into a
 * script the browser runs. */
export function signScripts(html: string, nonce: string): string {
  let out = ''
  let at = 0
  for (;;) {
    const open = html.indexOf('<', at)
    if (open === -1) break
    out += html.slice(at, open)
    if (html.startsWith('<!--', open)) {
      const close = html.indexOf('-->', open + 4)
      at = close === -1 ? html.length : close + 3
      out += html.slice(open, at)
      continue
    }
    const name = /^<([a-z][\w-]*)/i.exec(html.slice(open, open + 32))?.[1]?.toLowerCase()
    if (!name) {
      out += '<'
      at = open + 1
      continue
    }
    at = startTagEnd(html, open)
    const tag = html.slice(open, at)
    out += name === 'script' && !hasNonce(tag) ? `<script nonce="${nonce}"${tag.slice('<script'.length)}` : tag
    if (RAW_TEXT.has(name)) {
      const close = new RegExp(`</${name}`, 'ig')
      close.lastIndex = at
      const end = close.exec(html)?.index ?? html.length
      out += html.slice(at, end)
      at = end
    }
  }
  return out + html.slice(at)
}

// Just past the ">" that ends the start tag at `open`, skipping quoted attribute values.
function startTagEnd(html: string, open: number): number {
  let i = open + 1
  while (i < html.length && html[i] !== '>') {
    const quote = html[i]
    if (quote === '"' || quote === "'") {
      const close = html.indexOf(quote, i + 1)
      if (close === -1) return html.length
      i = close + 1
    } else {
      i++
    }
  }
  return Math.min(i + 1, html.length)
}

// A nonce attribute of the tag itself, not "nonce" written inside some attribute's value.
function hasNonce(tag: string): boolean {
  return /\snonce\b/i.test(tag.replace(/"[^"]*"|'[^']*'/g, '""'))
}
