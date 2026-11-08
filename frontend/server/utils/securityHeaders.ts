// The security headers the panel's server sends (plugins/security-headers.ts). The same in the
// hosted service and on a company's own server, since both are this server. Plain values, so
// tests/securityHeaders.test.ts checks them on their own.

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
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'"
  ].join('; ')
}

/** Adds the nonce to every <script> tag in a piece of HTML the renderer wrote itself. */
export function signScripts(html: string, nonce: string): string {
  return html.replace(/<script\b(?![^>]*\snonce=)/gi, `<script nonce="${nonce}"`)
}
