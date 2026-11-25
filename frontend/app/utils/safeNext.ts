// Where the login page sends someone once they are signed in, when a page sent them to sign in first
// (the OAuth consent page, any panel page): `?next=` (tests/safeNext.test.ts). It arrives in a URL
// anyone can make, so only a path of this same site is taken: "//evil.example" or "/\evil.example"
// would be read by the browser as another site, and an absolute URL would leave the site outright.

/** `next` if it is a path of this site ("/oauth/consent?request=…"), else null. */
export function safeNext(next: unknown): string | null {
  if (typeof next !== 'string' || !next.startsWith('/') || next.startsWith('//')) return null
  // Backslashes are slashes to a browser; control characters (tab, newline) are dropped by it, so
  // "/\t/evil.example" would become "//evil.example".
  // eslint-disable-next-line no-control-regex
  if (/[\\\u0000-\u001f\u007f]/.test(next)) return null
  // Whatever slipped past the rules above must still resolve to this same origin.
  const base = 'https://panel.invalid'
  return new URL(next, base).origin === base ? next : null
}
